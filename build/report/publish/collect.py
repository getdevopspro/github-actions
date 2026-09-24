"""Collect uploaded test, lint, and coverage results for the shared renderer."""

import argparse
import dataclasses
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET

import render


REPORT_KEYS = ("suites", "system_suites", "lint_packages", "cov_packages")
METADATA_KEYS = ("outcome", "issues", "baselines", "comparisons")
REPORT_SECTIONS = ("unit", "system", "lint", "coverage")
REPORT_SCHEMA = json.loads(Path(__file__).with_name("report.schema.json").read_text())


def annotate(level, message):
    # Artifact names and parser errors may contain workflow-command delimiters.
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{level}::{escaped}")


def validate_report(value, schema=None, location="report"):
    """Enforce the keywords used by our bundled schema without runtime dependencies."""
    schema = REPORT_SCHEMA if schema is None else schema
    if "$ref" in schema:
        schema = REPORT_SCHEMA["$defs"][schema["$ref"].rsplit("/", 1)[-1]]
    types = {"object": (dict,), "array": (list,), "string": (str,), "integer": (int,), "number": (int, float)}
    kind = schema.get("type")
    if kind and type(value) not in types[kind]:
        raise ValueError(f"{location} must be {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{location} must be one of {schema['enum']}")
    if "pattern" in schema:
        pattern = schema["pattern"]
        match = re.fullmatch if pattern.startswith("^") else re.search
        if not match(pattern, value):
            raise ValueError(f"{location} has an invalid format")
    if kind in ("integer", "number"):
        if type(value) is float and not math.isfinite(value):
            raise ValueError(f"{location} must be finite")
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise ValueError(f"{location} is outside the allowed range")
    if "not" in schema:
        try:
            validate_report(value, schema["not"], location)
        except ValueError:
            pass
        else:
            raise ValueError(f"{location} contains a forbidden field combination")
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                validate_report(value, alternative, location)
                break
            except ValueError:
                pass
        else:
            raise ValueError(f"{location} does not match an allowed report shape")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{location}.{key} is required")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                validate_report(item, properties[key], f"{location}.{key}")
            elif schema.get("additionalProperties") is False:
                raise ValueError(f"{location}.{key} is not supported")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            validate_report(item, schema["items"], f"{location}[{index}]")


def artifact_names(value):
    names = list(dict.fromkeys(line.strip() for line in value.splitlines() if line.strip()))
    if not names:
        raise ValueError("At least one report artifact name is required")
    for name in names:
        if name in (".", "..") or any(c in name for c in "/\\\r\n"):
            raise ValueError("Report artifact names must be single directory names")
    return names


def prepare():
    names = artifact_names(os.environ["REPORT_ARTIFACT_NAMES"])
    groups = json.loads(os.environ.get("REPORT_ARTIFACT_SECTIONS") or "{}")
    validate_report(groups, {"type": "object"}, "artifact-sections")
    titles = {}
    for name, group in groups.items():
        if name not in names:
            raise ValueError("artifact-sections must reference selected artifact names")
        validate_report(group, REPORT_SCHEMA["$defs"]["sectionMetadata"], f"artifact-sections.{name}")
        if group["id"] in titles and titles[group["id"]] != group["title"]:
            raise ValueError("A section ID must have one title")
        titles[group["id"]] = group["title"]
    root = Path(tempfile.mkdtemp(prefix="build-report-", dir=os.environ["RUNNER_TEMP"]))
    (root / "output").mkdir()
    (root / "artifacts.json").write_text(json.dumps(names))
    (root / "artifact-sections.json").write_text(json.dumps(groups))
    escaped = [re.sub(r"([*?\[\]{}(),!+@|])", r"\\\1", name) for name in names]
    values = {
        "root": str(root),
        "name": names[0] if len(names) == 1 else "",
        "pattern": "{" + ",".join(escaped) + "}" if len(names) > 1 else "",
        "download-path": str(root / "input" / names[0] if len(names) == 1 else root / "input"),
        "html": str(root / "output/build_report.html"),
        "markdown": str(root / "output/build_report.md"),
    }
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def unpack_reports(directory):
    for archive in sorted(directory.rglob("*.tar")):
        target = archive.with_suffix(".reports")
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                    raise ValueError("Report archive contains an unsafe path or link")
                if not member.isfile() or path.suffix.lower() not in (".xml", ".json"):
                    continue
                destination = target.joinpath(*path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as reader, destination.open("wb") as writer:
                    shutil.copyfileobj(reader, writer)


def merge_metadata(destination, source):
    """Combine producer results without allowing a later success to hide failure."""
    if source.get("outcome"):
        old = destination.get("outcome")
        new = source["outcome"]
        rank = {"skipped": 0, "passed": 1, "failed": 2, "error": 3}
        status = max((old or new)["status"], new["status"], key=rank.get)
        messages = dict.fromkeys(item["message"] for item in (old, new) if item and item.get("message"))
        destination["outcome"] = {"status": status, "message": "; ".join(messages)}
    for key in ("issues", "baselines", "comparisons"):
        destination.setdefault(key, [])
        for item in source.get(key, []):
            if item not in destination[key]:
                destination[key].append(item)


def report_metadata(value):
    """Resolve document/section-local baseline IDs into stable portable references."""
    result = {}

    def baseline_map(items):
        mapped = {}
        for item in items:
            if item["id"] in mapped:
                raise ValueError(f'duplicate baseline ID: {item["id"]}')
            fields = {key: field for key, field in item.items() if key != "id"}
            identity = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()[:16]
            normalized = {"id": "baseline-" + identity, **fields}
            mapped[item["id"]] = normalized
        return mapped

    shared = baseline_map(value.get("baselines", []))
    for source in [value, *value.get("report_sections", [])]:
        local = shared if source is value else baseline_map(source.get("baselines", []))
        references = {**shared, **local}
        comparisons = []
        for comparison in source.get("comparisons", []):
            comparison = dict(comparison)
            if "baseline_id" in comparison:
                baseline = references.get(comparison["baseline_id"])
                if baseline is None:
                    raise ValueError(f'unknown baseline_id: {comparison["baseline_id"]}')
                if comparison["status"] == "available" and baseline["status"] == "unavailable":
                    raise ValueError("available comparison requires an available baseline")
                comparison["baseline_id"] = baseline["id"]
            comparisons.append(comparison)
        merge_metadata(result, {"outcome": source.get("outcome"), "issues": source.get("issues", []),
                                "baselines": list(local.values()), "comparisons": comparisons})
    return result


def read_reports(directory):
    data = [[] for _ in REPORT_KEYS]
    issues = []
    count = 0
    sections = set()
    warnings = []
    empty_test_warnings = []
    title = None
    comparison = None
    metadata = {}
    if not directory.is_dir():
        return data, ["artifact is missing"], count, sections, warnings, title, comparison, metadata
    try:
        unpack_reports(directory)
    except (OSError, tarfile.TarError, ValueError) as error:
        return data, [str(error)], count, sections, warnings, title, comparison, metadata
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".xml", ".json"):
            continue
        try:
            parsed = [[] for _ in REPORT_KEYS]
            present = set()
            supplied_comparisons = []
            supplied_metadata = {}
            if path.suffix.lower() == ".json":
                value = json.loads(path.read_text())
                if isinstance(value, dict) and any(key in value for key in
                                                  (*REPORT_KEYS, *METADATA_KEYS, "report_sections", "schema_version")):
                    validate_report(value)
                    supplied_metadata = report_metadata(value)
                    supplied_comparisons = [item["coverage_comparison"] for item in
                                            [value, *value.get("report_sections", [])]
                                            if "coverage_comparison" in item]
                    if len(supplied_comparisons) > 1 or (supplied_comparisons and comparison is not None):
                        raise ValueError("multiple coverage comparisons in one producer are ambiguous")
                    parsed = render._load_report_data(path)
                    present.update(value.get("sections", []))
                    for section in value.get("report_sections", []):
                        present.update(section["kinds"])
                    supplied = [key for key in REPORT_KEYS if key in value]
                    for key, section in zip(REPORT_KEYS, REPORT_SECTIONS):
                        if value.get(key) or (len(supplied) == 1 and key in supplied):
                            present.add(section)
                elif isinstance(value, dict) and "generalDiagnostics" in value:
                    if not isinstance(value["generalDiagnostics"], list):
                        raise ValueError("generalDiagnostics must be an array")
                    parsed[2] = render.parse_pyright_json_files([path])
                    present.add("lint")
                elif isinstance(value, list) and all(
                    isinstance(item, dict) and "filename" in item and "message" in item for item in value
                ):
                    parsed[2] = render.parse_ruff_json_files([path])
                    present.add("lint")
                else:
                    continue
            else:
                tag = ET.parse(path).getroot().tag
                if tag == "coverage":
                    parsed[3] = render.parse_coverage_xml_files([path])
                    present.add("coverage")
                elif tag in ("testsuite", "testsuites"):
                    if path.name.endswith(".xunit.xml"):
                        parsed[2] = render.parse_lint_xml_files([path])
                        present.add("lint")
                    elif path.name == "system_tests.xml":
                        parsed[1] = render.parse_system_test_xml_files([path])
                        present.add("system")
                    else:
                        parsed[0] = render.parse_test_xml_files([path])
                        present.add("tests")
                else:
                    continue
            present.update(kind for values, kind in zip(parsed, REPORT_SECTIONS) if values)
            # Apply the same numeric/status checks to native formats before normalization.
            validate_report(
                {key: [dataclasses.asdict(item) for item in items] for key, items in zip(REPORT_KEYS, parsed)}
            )
            all_suites = parsed[0] + parsed[1]
            for suite in all_suites:
                suite.failures = max(suite.failures, sum(case.status == "failed" for case in suite.cases))
                suite.errors = max(suite.errors, sum(case.status == "error" for case in suite.cases))
                suite.skipped = max(suite.skipped, sum(case.status == "skipped" for case in suite.cases))
                suite.tests = max(suite.tests, len(suite.cases), suite.failures + suite.errors + suite.skipped)
            for package in parsed[3]:
                for coverage in [package, *package.files]:
                    if coverage.lines_covered > coverage.lines_valid:
                        raise ValueError("covered lines exceed executable lines")
            for package in parsed[2]:
                for tool in package.tools:
                    for file in tool.files:
                        if file.diagnostics and file.status != render._lint_diagnostic_status(file.diagnostics):
                            raise ValueError("lint status must match the highest diagnostic severity")
            if supplied_comparisons and "coverage" not in present:
                raise ValueError("coverage_comparison requires coverage results in the same JSON")
            label = str(path.relative_to(directory))
            if not present and not any(supplied_metadata.values()):
                warnings.append(
                    f"{label}: empty report has no identifiable sections; declare sections for checks with zero findings"
                )
            if present & {"unit", "system", "tests"} and not any(suite.tests for suite in all_suites):
                empty_test_warnings.append(f"{label}: no tests collected in reported test results")
            if "coverage" in present and not sum(package.lines_valid for package in parsed[3]):
                warnings.append(f"{label}: coverage contains no executable lines")
            if path.suffix.lower() == ".json" and isinstance(value, dict) and "section_title" in value:
                override = value["section_title"]
                validate_report(override, REPORT_SCHEMA["$defs"]["sectionTitle"], "section_title")
                if title is not None and title != override:
                    issues.append(f"{label}: conflicting section_title overrides")
                else:
                    title = override
            for destination, values in zip(data, parsed):
                destination.extend(values)
            if supplied_comparisons:
                comparison = supplied_comparisons[0]
            merge_metadata(metadata, supplied_metadata)
            sections.update(present)
            count += 1
        except (OSError, ValueError, TypeError, KeyError, AttributeError, ET.ParseError) as error:
            issues.append(f"{path.relative_to(directory)}: {error}")
    if not count:
        issues.append("artifact contains no supported report files")
    if not any(suite.tests for suite in data[0] + data[1]):
        warnings.extend(empty_test_warnings)
    return data, issues, count, sections, warnings, title, comparison, metadata


def generate(root):
    names = json.loads((root / "artifacts.json").read_text())
    metadata = root / "artifact-sections.json"
    defaults = json.loads(metadata.read_text()) if metadata.exists() else {}
    sections = {}
    overrides = {}
    issues = []
    warnings = []
    if os.environ.get("REPORT_DOWNLOAD_OUTCOME") == "failure":
        issues.append("Report artifact download failed; results may be incomplete")

    def collect_section(directory, name, default):
        data, errors, count, present, notices, title, comparison, metadata = read_reports(directory)
        issues.extend(f"{name}: {error}" for error in errors)
        warnings.extend(f"{name}: {notice}" for notice in notices)
        if not count:
            return
        section_id = default["id"]
        if section_id not in sections:
            sections[section_id] = render.ReportSection(**default)
        section = sections[section_id]
        if title is not None:
            if section_id in overrides and overrides[section_id] != title:
                issues.append(f"{name}: conflicting section_title overrides for {section_id}")
            else:
                overrides[section_id] = title
                section.title = title
        section.suites.extend(data[0] + data[1])
        section.lint_packages.extend(data[2])
        section.cov_packages.extend(data[3])
        combined = {key: getattr(section, key) for key in METADATA_KEYS}
        merge_metadata(combined, metadata)
        for key, value in combined.items():
            setattr(section, key, value)
        if comparison is not None:
            if section.coverage_comparison is not None:
                issues.append(f"{name}: multiple coverage comparisons for {section_id}")
            else:
                section.coverage_comparison = comparison
                if comparison["status"] == "unavailable":
                    warnings.append(f'{name}: coverage comparison unavailable: {comparison["reason"]}')
                elif comparison["status"] == "approximate":
                    relation = (
                        "the parent of the requested baseline"
                        if comparison["baseline"].get("distance") == 1 else "an earlier ancestor"
                    )
                    annotate("notice", f"{name}: coverage comparison uses {relation}")
        kinds = {"tests" if kind in ("unit", "system") else kind for kind in present}
        section.kinds = sorted(set(section.kinds) | kinds)

    for name in names:
        default = defaults.get(
            name, {"id": "artifact-" + hashlib.sha256(name.encode()).hexdigest()[:16], "title": name}
        )
        collect_section(root / "input" / name, name, default)
    if len(names) > 1 and not any((root / "input" / name).is_dir() for name in names):
        # download-artifact flattens a single match, even for a multi-name pattern.
        # Its producer is unknown; preserve available results and fail missing inputs.
        collect_section(root / "input", "Unattributed results", {"id": "unattributed", "title": "Unattributed results"})
    sections = list(sections.values())
    for section in sections:
        files = [file for package in section.lint_packages for tool in package.tools for file in tool.files]
        if any(file.count("warning") for file in files):
            annotate("warning", f"{section.title}: lint {render._lint_summary(files)}")
        elif any(file.count("information") for file in files):
            annotate("notice", f"{section.title}: lint {render._lint_summary(files)}")
        for issue in section.issues:
            if issue["severity"] != "error":
                annotate("notice" if issue["severity"] == "information" else "warning",
                         f'{section.title}: {issue["message"]}')
        for baseline in section.baselines:
            if baseline["status"] == "approximate":
                annotate("notice", f"{section.title}: approximate baseline supplied by producer")
            elif baseline["status"] == "unavailable":
                warnings.append(f'{section.title}: baseline unavailable: {baseline["reason"]}')
        for comparison in section.comparisons:
            if comparison["status"] == "unavailable":
                warnings.append(f'{section.title}: {comparison["name"]} comparison unavailable: {comparison["reason"]}')
    (root / "issues.json").write_text(json.dumps(issues))
    output = root / "output"
    for warning in warnings:
        annotate("warning", warning)
    report = output / "build_report.html"
    markdown = output / "build_report.md"
    render._save_report_data(report.with_suffix(".json"), sections)
    report.write_text(
        render.render_html(
            sections,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            title="Build Report",
            output_path=report,
            report_errors=issues,
            report_warnings=warnings,
        ),
        encoding="utf-8",
    )
    markdown.write_text(
        render.render_markdown_summary(
            sections,
            title="Build Report",
            report_errors=issues,
            report_warnings=warnings,
        ),
        encoding="utf-8",
    )


def check(root):
    report = root / "output/build_report.json"
    if not report.is_file():
        annotate("error", "Build report was not generated; results could not be checked")
        return 1
    issues = json.loads((root / "issues.json").read_text())
    for issue in issues:
        annotate("error", issue)
    blocking = [section for section in render._load_report_sections(report) if section.blocking]
    for section in blocking:
        annotate("error", f"{section.title}: reported check, tool, or policy failure; see the build report")
    return int(bool(issues or blocking))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "generate", "check"))
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare()
    elif args.operation == "generate":
        generate(args.root)
    else:
        return check(args.root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
