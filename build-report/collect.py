"""Collect uploaded test, lint, and coverage results for the shared renderer."""

import argparse
import dataclasses
from datetime import datetime
import html
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
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                validate_report(value, alternative, location)
                break
            except ValueError:
                pass
        else:
            raise ValueError(f"{location} must contain a report section")
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


def read_reports(directory):
    data = [[] for _ in REPORT_KEYS]
    issues = []
    count = 0
    sections = set()
    warnings = []
    empty_test_warnings = []
    title = None
    if not directory.is_dir():
        return data, ["artifact is missing"], count, sections, warnings, title
    try:
        unpack_reports(directory)
    except (OSError, tarfile.TarError, ValueError) as error:
        return data, [str(error)], count, sections, warnings, title
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".xml", ".json"):
            continue
        try:
            parsed = [[] for _ in REPORT_KEYS]
            present = set()
            if path.suffix.lower() == ".json":
                value = json.loads(path.read_text())
                if isinstance(value, dict) and any(key in value for key in (*REPORT_KEYS, "report_sections")):
                    validate_report(value)
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
            label = str(path.relative_to(directory))
            if not present:
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
            sections.update(present)
            count += 1
        except (OSError, ValueError, TypeError, KeyError, AttributeError, ET.ParseError) as error:
            issues.append(f"{path.relative_to(directory)}: {error}")
    if not count:
        issues.append("artifact contains no supported report files")
    if not any(suite.tests for suite in data[0] + data[1]):
        warnings.extend(empty_test_warnings)
    return data, issues, count, sections, warnings, title


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
        data, errors, count, present, notices, title = read_reports(directory)
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
    (root / "issues.json").write_text(json.dumps(issues))
    output = root / "output"
    baseline_rate = None
    if os.environ.get("REPORT_BASELINE_REQUESTED") == "true" or (root / "baseline").exists():
        baseline, errors, count, _, _, _ = read_reports(root / "baseline")
        if count and not errors:
            valid = sum(package.lines_valid for package in baseline[3])
            if valid:
                baseline_rate = sum(package.lines_covered for package in baseline[3]) / valid
        if baseline_rate is None:
            warnings.append("Coverage baseline is unavailable, invalid, or has no executable lines; comparison omitted")
        elif sum("coverage" in section.kinds for section in sections) > 1:
            baseline_rate = None
            warnings.append("Coverage baseline cannot be attributed to multiple producer sections; comparison omitted")
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
            baseline_cov_rate=baseline_rate,
            report_errors=issues,
            report_warnings=warnings,
        ),
        encoding="utf-8",
    )
    for heading, messages in (("Report warnings", warnings), ("Report input errors", issues)):
        if messages:
            details = "\n".join(f"- {message}" for message in messages)
            markdown.write_text(f"## {heading}\n\n<pre>" + html.escape(details) + "</pre>\n\n" + markdown.read_text())
            banner = f'<section class="content"><h2>{heading}</h2><pre>' + html.escape(details) + "</pre></section>"
            report.write_text(report.read_text().replace("<body>", "<body>" + banner, 1))


def check(root):
    report = root / "output/build_report.json"
    if not report.is_file():
        annotate("error", "Build report was not generated; results could not be checked")
        return 1
    issues = json.loads((root / "issues.json").read_text())
    for issue in issues:
        annotate("error", issue)
    failures = sum(section.failures for section in render._load_report_sections(report))
    if failures:
        annotate("error", f"{failures} test or lint failure(s); see the build report")
    return int(bool(issues or failures))


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
