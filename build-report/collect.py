"""Collect uploaded test, lint, and coverage results for the shared renderer."""

import argparse
from datetime import datetime
import html
import json
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
    root = Path(tempfile.mkdtemp(prefix="build-report-", dir=os.environ["RUNNER_TEMP"]))
    (root / "output").mkdir()
    (root / "artifacts.json").write_text(json.dumps(names))
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
    data = [[], [], [], []]
    issues = []
    count = 0
    if not directory.is_dir():
        return data, ["artifact is missing"], count
    try:
        unpack_reports(directory)
    except (OSError, tarfile.TarError, ValueError) as error:
        return data, [str(error)], count
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".xml", ".json"):
            continue
        try:
            parsed = [[], [], [], []]
            if path.suffix.lower() == ".json":
                value = json.loads(path.read_text())
                if isinstance(value, dict) and any(key in value for key in REPORT_KEYS):
                    if any(not isinstance(value.get(key, []), list) for key in REPORT_KEYS):
                        raise ValueError("report JSON sections must be lists")
                    parsed = render._load_report_data(path)
                elif isinstance(value, dict) and "generalDiagnostics" in value:
                    parsed[2] = render.parse_pyright_json_files([path])
                elif isinstance(value, list) and all(
                    isinstance(item, dict) and "filename" in item and "message" in item for item in value
                ):
                    parsed[2] = render.parse_ruff_json_files([path])
                else:
                    continue
            else:
                tag = ET.parse(path).getroot().tag
                if tag == "coverage":
                    parsed[3] = render.parse_coverage_xml_files([path])
                elif tag in ("testsuite", "testsuites"):
                    if path.name.endswith(".xunit.xml"):
                        parsed[2] = render.parse_lint_xml_files([path])
                    elif path.name == "system_tests.xml":
                        parsed[1] = render.parse_system_test_xml_files([path])
                    else:
                        parsed[0] = render.parse_test_xml_files([path])
                else:
                    continue
            for suite in parsed[0] + parsed[1]:
                suite.tests = max(suite.tests, len(suite.cases))
                suite.failures = max(suite.failures, sum(case.status == "failed" for case in suite.cases))
                suite.errors = max(suite.errors, sum(case.status == "error" for case in suite.cases))
                suite.skipped = max(suite.skipped, sum(case.status == "skipped" for case in suite.cases))
            for destination, values in zip(data, parsed):
                destination.extend(values)
            count += 1
        except (OSError, ValueError, TypeError, KeyError, AttributeError, ET.ParseError) as error:
            issues.append(f"{path.relative_to(directory)}: {error}")
    if not count:
        issues.append("artifact contains no supported report files")
    return data, issues, count


def generate(root):
    names = json.loads((root / "artifacts.json").read_text())
    data = [[], [], [], []]
    issues = []
    if os.environ.get("REPORT_DOWNLOAD_OUTCOME") == "failure":
        issues.append("Report artifact download failed; results may be incomplete")
    for name in names:
        parsed, errors, _ = read_reports(root / "input" / name)
        for destination, values in zip(data, parsed):
            destination.extend(values)
        issues.extend(f"{name}: {error}" for error in errors)
    if len(names) > 1 and any(not (root / "input" / name).is_dir() for name in names):
        # download-artifact flattens a single match, even for a multi-name pattern.
        # Keep its results visible while failing the incomplete artifact set.
        data, errors, _ = read_reports(root / "input")
        issues.extend(errors)
    (root / "issues.json").write_text(json.dumps(issues))
    output = root / "output"
    baseline_rate = None
    if (root / "baseline").exists():
        baseline, errors, count = read_reports(root / "baseline")
        if count and not errors:
            valid = sum(package.lines_valid for package in baseline[3])
            if valid:
                baseline_rate = sum(package.lines_covered for package in baseline[3]) / valid
        else:
            print("::warning::Coverage baseline is unavailable or invalid; comparison omitted")
    report = output / "build_report.html"
    markdown = output / "build_report.md"
    render._save_report_data(report.with_suffix(".json"), *data)
    report.write_text(
        render.render_html(
            *data,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            title="Build Report",
            output_path=report,
            report_errors=issues,
        ),
        encoding="utf-8",
    )
    markdown.write_text(
        render.render_markdown_summary(
            *data,
            title="Build Report",
            baseline_cov_rate=baseline_rate,
            report_errors=issues,
        ),
        encoding="utf-8",
    )
    if issues:
        details = "\n".join(f"- {issue}" for issue in issues)
        markdown.write_text("## Report input errors\n\n" + details + "\n\n" + markdown.read_text())
        banner = "<section><h2>Report input errors</h2><pre>" + html.escape(details) + "</pre></section>"
        report.write_text(report.read_text().replace("<body>", "<body>" + banner, 1))


def check(root):
    report = root / "output/build_report.json"
    if not report.is_file():
        print("::error::Build report was not generated; results could not be checked")
        return 1
    issues = json.loads((root / "issues.json").read_text())
    for issue in issues:
        print(f"::error::{issue}")
    suites, system_suites, lint, _ = render._load_report_data(report)
    failures = sum(suite.failures + suite.errors for suite in suites + system_suites)
    failures += sum(package.failures for package in lint)
    if failures:
        print(f"::error::{failures} test or lint failure(s); see the build report")
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
