"""Parse build results and render standalone HTML and Markdown reports."""

import dataclasses
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

DEFAULT_REPORT_PATH = Path("build/build_report.html")
REPO_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path.cwd()))


# ---------------------------------------------------------------------------
# Data models — unit tests
# ---------------------------------------------------------------------------


@dataclass
class TestCase:
    name: str
    classname: str
    time: float
    status: str  # "passed", "failed", "error", "skipped"
    message: str = ""
    details: str = ""


@dataclass
class TestSuite:
    name: str
    package: str
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    time: float = 0.0
    cases: list[TestCase] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Data models — lint
# ---------------------------------------------------------------------------


@dataclass
class LintFile:
    name: str  # file path as reported in testcase name
    status: str  # "passed" or "failed"
    message: str = ""
    details: str = ""


@dataclass
class LintTool:
    name: str  # "flake8", "pep257", "xmllint", "lint_cmake"
    files: list[LintFile] = field(default_factory=list)

    @property
    def failures(self) -> int:
        return sum(1 for f in self.files if f.status == "failed")

    @property
    def passed(self) -> int:
        return sum(1 for f in self.files if f.status == "passed")


@dataclass
class LintPackage:
    package: str
    tools: list[LintTool] = field(default_factory=list)

    @property
    def failures(self) -> int:
        return sum(t.failures for t in self.tools)

    @property
    def total_files(self) -> int:
        return sum(len(t.files) for t in self.tools)


# ---------------------------------------------------------------------------
# Data models — coverage
# ---------------------------------------------------------------------------


@dataclass
class CoverageFile:
    name: str  # relative filename as reported in coverage.xml
    line_rate: float
    lines_covered: int
    lines_valid: int
    html_path: str = ""  # relative path to per-file HTML report, if found


@dataclass
class CoveragePackage:
    package: str  # directory containing the coverage report
    line_rate: float
    lines_covered: int
    lines_valid: int
    files: list[CoverageFile] = field(default_factory=list)
    html_dir: str = ""  # relative path to coverage.html/ dir for this package


@dataclass
class ReportSection:
    id: str
    title: str
    suites: list[TestSuite] = field(default_factory=list)
    lint_packages: list[LintPackage] = field(default_factory=list)
    cov_packages: list[CoveragePackage] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    coverage_comparison: dict | None = None

    @property
    def failures(self) -> int:
        return sum(s.failures + s.errors for s in self.suites) + sum(p.failures for p in self.lint_packages)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def parse_test_xml_files(xml_files: list[Path], verbose: bool = False) -> list[TestSuite]:
    suites = []
    for xml_file in xml_files:
        if verbose:
            print(f"  unit: {xml_file}")
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
        except ET.ParseError as e:
            print(f"Warning: could not parse {xml_file}: {e}", file=sys.stderr)
            continue

        suite_elements = root.findall("testsuite") if root.tag == "testsuites" else [root]

        for suite_el in suite_elements:
            name = suite_el.get("name", xml_file.stem)
            package = xml_file.parent.name  # build/<pkg>/pytest.xml

            suite = TestSuite(
                name=name,
                package=package,
                tests=int(suite_el.get("tests", 0)),
                failures=int(suite_el.get("failures", 0)),
                errors=int(suite_el.get("errors", 0)),
                skipped=int(suite_el.get("skipped", 0) or suite_el.get("skip", 0)),
                time=float(suite_el.get("time", 0.0)),
            )

            for tc_el in suite_el.findall("testcase"):
                status = "passed"
                message = ""
                details = ""

                failure = tc_el.find("failure")
                error = tc_el.find("error")
                skipped = tc_el.find("skipped")

                if failure is not None:
                    status = "failed"
                    message = failure.get("message", "")
                    details = failure.text or ""
                elif error is not None:
                    status = "error"
                    message = error.get("message", "")
                    details = error.text or ""
                elif skipped is not None:
                    status = "skipped"
                    message = skipped.get("message", "")

                suite.cases.append(
                    TestCase(
                        name=tc_el.get("name", ""),
                        classname=tc_el.get("classname", ""),
                        time=float(tc_el.get("time", 0.0)),
                        status=status,
                        message=message,
                        details=details.strip(),
                    )
                )

            suites.append(suite)

    return suites


def parse_system_test_xml_files(xml_files: list[Path], verbose: bool = False) -> list[TestSuite]:
    """Parse system test JUnit XML files.

    Suite names are formatted as 'package_name/launch_test_file_basename'.
    The package field is derived from the suite name.
    """
    if verbose:
        for xml_file in xml_files:
            print(f"  system: {xml_file}")
    suites = parse_test_xml_files(xml_files)
    for suite in suites:
        if "/" in suite.name:
            suite.package = suite.name.split("/")[0]
        else:
            suite.package = suite.name
    return suites


def parse_lint_xml_files(xml_files: list[Path], verbose: bool = False) -> list[LintPackage]:
    """Parse ament lint xunit XML files into LintPackage objects.

    Files are at build/<pkg>/test_results/<pkg>/<tool>.xunit.xml.
    Groups by package, then by tool (stem of the filename).
    """
    # Collect per (package, tool) -> list of LintFile
    pkg_map: dict[str, dict[str, list[LintFile]]] = {}

    for xml_file in sorted(xml_files):
        # Derive package from grandparent dir: build/<pkg>/test_results/<pkg>/<tool>.xunit.xml
        package = xml_file.parent.parent.parent.name
        tool_name = xml_file.stem.replace(".xunit", "")

        if verbose:
            print(f"  lint: {xml_file}")
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
        except ET.ParseError as e:
            print(f"Warning: could not parse {xml_file}: {e}", file=sys.stderr)
            continue

        suite_elements = root.findall("testsuite") if root.tag == "testsuites" else [root]

        for suite_el in suite_elements:
            for tc_el in suite_el.findall("testcase"):
                file_name = tc_el.get("name", "")
                failure = tc_el.find("failure")
                error = tc_el.find("error")

                if failure is not None:
                    status = "failed"
                    details = (failure.text or failure.get("message", "")).strip()
                elif error is not None:
                    status = "failed"
                    details = (error.text or error.get("message", "")).strip()
                else:
                    status = "passed"
                    details = ""

                lint_file = LintFile(name=file_name, status=status, details=details)
                pkg_map.setdefault(package, {}).setdefault(tool_name, []).append(lint_file)

    result = []
    for package in sorted(pkg_map):
        tools = [LintTool(name=tool, files=files) for tool, files in sorted(pkg_map[package].items())]
        result.append(LintPackage(package=package, tools=tools))
    return result


def parse_ruff_json_files(json_files: list[Path], verbose: bool = False) -> list[LintPackage]:
    """Parse ruff --output-format=json files into LintPackage objects.

    Groups violations by ROS2 package derived from src/<group>/<pkg>/... paths.
    Only files with violations are represented.
    """
    file_details: dict[str, list[str]] = {}

    for json_file in json_files:
        if verbose:
            print(f"  ruff: {json_file}")
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: could not parse {json_file}: {e}", file=sys.stderr)
            continue

        for violation in data:
            filename = violation.get("filename", "unknown")
            code = violation.get("code") or ""
            message = violation.get("message") or ""
            location = violation.get("location") or {}
            row = location.get("row")
            col = location.get("column")
            loc = f"{row}:{col}" if row is not None else ""
            detail = f"{loc}: {code}: {message}" if loc else f"{code}: {message}"
            file_details.setdefault(filename, []).append(detail)

    if not file_details:
        return []

    pkg_map: dict[str, list[LintFile]] = {}
    for filename, details in sorted(file_details.items()):
        parts = Path(filename).parts
        try:
            src_idx = next(i for i, p in enumerate(parts) if p == "src")
            package = parts[src_idx + 2] if len(parts) > src_idx + 2 else parts[src_idx + 1]
        except StopIteration:
            package = parts[1] if len(parts) > 1 else (parts[0] if parts else "unknown")
        pkg_map.setdefault(package, []).append(LintFile(name=filename, status="failed", details="\n".join(details)))

    return [
        LintPackage(package=pkg, tools=[LintTool(name="ruff", files=files)]) for pkg, files in sorted(pkg_map.items())
    ]


def parse_pyright_json_files(json_files: list[Path], verbose: bool = False) -> list[LintPackage]:
    """Parse pyright --outputjson files into LintPackage objects.

    Groups diagnostics by ROS2 package derived from src/<group>/<pkg>/... paths.
    Only files with diagnostics are represented.
    """
    file_details: dict[str, list[str]] = {}

    for json_file in json_files:
        if verbose:
            print(f"  pyright: {json_file}")
        try:
            text = json_file.read_text(encoding="utf-8")
            # pyright-python wrapper can print arch-detection noise to stdout
            # before the JSON body; skip to the first line that begins a JSON object
            idx = text.find("\n{\n")
            if idx >= 0 and not text.lstrip().startswith("{\n"):
                text = text[idx + 1 :]
            data = json.loads(text)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: could not parse {json_file}: {e}", file=sys.stderr)
            continue

        for diag in data.get("generalDiagnostics", []):
            filename = diag.get("file", "unknown")
            severity = diag.get("severity", "error")
            message = diag.get("message", "")
            rule = diag.get("rule", "")
            rng = diag.get("range")
            if rng:
                start = rng.get("start", {})
                line = start.get("line", 0) + 1  # pyright uses zero-based lines
                col = start.get("character", 0) + 1
                loc = f"{line}:{col}"
            else:
                loc = ""
            parts = [loc, severity, rule, message]
            detail = ": ".join(p for p in parts if p)
            file_details.setdefault(filename, []).append(detail)

    if not file_details:
        return []

    pkg_map: dict[str, list[LintFile]] = {}
    for filename, details in sorted(file_details.items()):
        parts = Path(filename).parts
        try:
            src_idx = next(i for i, p in enumerate(parts) if p == "src")
            package = parts[src_idx + 2] if len(parts) > src_idx + 2 else parts[src_idx + 1]
        except StopIteration:
            package = parts[1] if len(parts) > 1 else (parts[0] if parts else "unknown")
        pkg_map.setdefault(package, []).append(LintFile(name=filename, status="failed", details="\n".join(details)))

    return [
        LintPackage(package=pkg, tools=[LintTool(name="pyright", files=files)])
        for pkg, files in sorted(pkg_map.items())
    ]


def parse_coverage_xml_files(xml_files: list[Path], verbose: bool = False) -> list[CoveragePackage]:
    """Parse coverage.xml (Cobertura format) files into CoveragePackage objects.

    Expected location: build/<pkg>/coverage.xml
    Per-file HTML pages are expected at build/<pkg>/coverage.html/<hash>_<file>.html
    """
    packages = []
    for xml_file in sorted(xml_files):
        package_name = xml_file.parent.name  # build/<pkg>/coverage.xml
        html_dir = xml_file.parent / "coverage.html"

        if verbose:
            print(f"  coverage: {xml_file}")
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
        except ET.ParseError as e:
            print(f"Warning: could not parse {xml_file}: {e}", file=sys.stderr)
            continue

        pkg_line_rate = float(root.get("line-rate", 0.0))
        pkg_lines_valid = int(root.get("lines-valid", 0))
        pkg_lines_covered = int(root.get("lines-covered", 0))

        # Build a lookup from filename stem → html file path for linking
        html_lookup: dict[str, str] = {}
        if html_dir.is_dir():
            for html_file in html_dir.glob("*.html"):
                if html_file.name != "index.html":
                    html_lookup[html_file.stem] = str(html_file)

        files: list[CoverageFile] = []
        for cls_el in root.findall(".//class"):
            filename = cls_el.get("filename", "")
            if not filename:
                continue
            line_rate = float(cls_el.get("line-rate", 0.0))
            lines = cls_el.findall("lines/line")
            lines_valid = len(lines)
            lines_covered = sum(1 for ln in lines if int(ln.get("hits", 0)) > 0)

            # Find matching per-file HTML report
            file_stem = Path(filename).stem
            html_path = ""
            for stem, path in html_lookup.items():
                if stem.endswith(f"_{file_stem}_py") or stem.endswith(f"_{file_stem}"):
                    html_path = path
                    break

            files.append(
                CoverageFile(
                    name=filename,
                    line_rate=line_rate,
                    lines_covered=lines_covered,
                    lines_valid=lines_valid,
                    html_path=html_path,
                )
            )

        files.sort(key=lambda f: f.line_rate)

        packages.append(
            CoveragePackage(
                package=package_name,
                line_rate=pkg_line_rate,
                lines_covered=pkg_lines_covered,
                lines_valid=pkg_lines_valid,
                files=files,
                html_dir=str(html_dir) if html_dir.is_dir() else "",
            )
        )

    return packages


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _md(text: str) -> str:
    text = _esc(" ".join(text.split())).replace("|", "&#124;")
    return re.sub(r"([\\`*_[\]~])", r"\\\1", text)


def _test_status(total, failures):
    if failures:
        return "#ef4444", "FAILED"
    return ("#22c55e", "PASSED") if total else ("#f59e0b", "NO TESTS")


def _empty_section(section, title, message):
    return f'<div class="content" id="section-{section}"><h2 class="section-title">{title}</h2><p>{message}</p></div>'


def _summary_group(section, label, cards):
    values = "".join(
        f'<div class="stat-card"><div class="val" style="color:{color}">{value}</div><div class="lbl">{name}</div></div>'
        for name, value, color in cards
    )
    return (
        f"<div class=\"stat-group\" onclick=\"document.getElementById('section-{section}').scrollIntoView({{behavior:'smooth'}})\">"
        f'<div class="stat-group-label">{_esc(label)}</div><div class="stat-group-cards">{values}</div></div>'
    )


def get_repo_name() -> str:
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"].rsplit("/", 1)[-1]
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        return remote.rstrip("/").split("/")[-1].removesuffix(".git")
    except subprocess.CalledProcessError:
        pass
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL, text=True)
            .strip()
            .split("/")[-1]
        )
    except subprocess.CalledProcessError:
        return ""


# ---------------------------------------------------------------------------
# Unit test rendering
# ---------------------------------------------------------------------------


def _group_by_class(cases: list[TestCase]) -> list[tuple[str, list[TestCase]]]:
    """Group cases by class name (last dotted component), preserving order."""
    groups: dict[str, list[TestCase]] = {}
    for tc in cases:
        key = tc.classname.split(".")[-1] if tc.classname else "(no class)"
        groups.setdefault(key, []).append(tc)
    return list(groups.items())


def _render_case(tc: TestCase) -> str:
    icons = {
        "passed": '<span class="status-icon status-pass">PASS</span>',
        "failed": '<span class="status-icon status-fail">FAIL</span>',
        "error": '<span class="status-icon status-error">ERROR</span>',
        "skipped": '<span class="status-icon status-skip">SKIP</span>',
    }
    icon = icons.get(tc.status, "")
    time_html = f'<span class="case-time">{tc.time:.3f}s</span>' if tc.time else ""
    msg_html = f'<div class="case-msg">{_esc(tc.message)}</div>' if tc.message else ""
    details_html = f'<div class="case-details">{_esc(tc.details)}</div>' if tc.details else ""
    return f"""
              <tr class="case-row {tc.status}">
                <td>
                  <div class="case-name-line">{icon} <span class="case-name">{_esc(tc.name)}</span> {time_html}</div>
                  {msg_html}{details_html}
                </td>
              </tr>"""


def _render_class_groups(suite_idx: str, cases: list[TestCase]) -> str:
    groups = _group_by_class(cases)
    html = []
    for j, (class_name, group_cases) in enumerate(groups):
        gid = f"{suite_idx}-{j}"
        n_fail = sum(1 for tc in group_cases if tc.status in ("failed", "error"))
        n_skip = sum(1 for tc in group_cases if tc.status == "skipped")
        n_pass = len(group_cases) - n_fail - n_skip
        badge_color = "#22c55e" if n_fail == 0 else "#ef4444"
        badge_text = "PASS" if n_fail == 0 else "FAIL"
        has_fail_cls = " has-fail" if n_fail else ""
        counts = f'<span style="color:#22c55e">{n_pass}✓</span>'
        if n_fail:
            counts += f' <span style="color:#ef4444">{n_fail}✗</span>'
        if n_skip:
            counts += f' <span style="color:#f59e0b">{n_skip} skip</span>'
        html.append(f"""
            <tr class="class-header{has_fail_cls}" onclick="toggleClass('{gid}')">
              <td colspan="3">
                <span class="toggle" id="ctoggle-{gid}">▶</span>
                <span class="class-name">{_esc(class_name)}</span>
                <span class="class-counts">{counts}</span>
                <span class="badge" style="background:{badge_color}">{badge_text}</span>
              </td>
            </tr>
            <tr id="cg-{gid}-cases" class="class-cases" style="display:none">
              <td colspan="3" style="padding:0">
                <table class="cases-inner-table">
                  {"".join(_render_case(tc) for tc in group_cases)}
                </table>
              </td>
            </tr>""")
    return "".join(html)


def _render_test_section(suites: list[TestSuite], section: str, title: str) -> str:
    total_tests = sum(s.tests for s in suites)
    total_failures = sum(s.failures for s in suites)
    total_errors = sum(s.errors for s in suites)
    test_color, test_status = _test_status(total_tests, total_failures + total_errors)

    suites = sorted(suites, key=lambda s: (s.failures + s.errors == 0, s.package))

    suite_rows = []
    for index, suite in enumerate(suites):
        i = f"{section}-{index}"
        suite_name = f" / {_esc(suite.name)}" if suite.name != suite.package else ""
        passed = suite.tests - suite.failures - suite.errors - suite.skipped
        badge_color, suite_status = _test_status(suite.tests, suite.failures + suite.errors)
        suite_rows.append(f"""
        <tr class="suite-header" onclick="toggleSuite('{i}')">
          <td><span class="toggle" id="toggle-{i}">▶</span> <strong>{_esc(suite.package)}</strong>{suite_name}</td>
          <td><span class="badge" style="background:{badge_color}">{suite_status.upper()}</span></td>
          <td>{suite.tests}</td>
          <td style="color:#22c55e;font-weight:600">{passed}</td>
          <td style="color:#ef4444;font-weight:600">{suite.failures + suite.errors}</td>
          <td style="color:#f59e0b;font-weight:600">{suite.skipped}</td>
          <td>{suite.time:.3f}s</td>
        </tr>
        <tr id="suite-{i}-cases" class="suite-cases" style="display:none">
          <td colspan="7" style="padding:0">
            <table class="cases-table">
              {_render_class_groups(i, suite.cases)}
            </table>
          </td>
        </tr>""")

    return f"""<div class="content" id="section-{section}">
  <div class="section-title collapsible" onclick="toggleSection('{section}')" style="display:flex;align-items:center;gap:12px">
    <span class="toggle section-toggle{" open" if total_failures + total_errors > 0 else ""}" id="section-{section}-toggle">▶</span>
    {_esc(title)}
    <span class="badge" style="background:{test_color};font-size:0.7rem">{test_status}</span>
    <span style="color:#475569;font-size:0.8rem;font-weight:400;text-transform:none;letter-spacing:0">{len(suites)} suite{"s" if len(suites) != 1 else ""} &middot; {total_tests} tests{f", {total_failures + total_errors} failing" if total_failures + total_errors else ""}</span>
  </div>
  <div id="section-{section}-body" style="display:{"block" if total_failures + total_errors > 0 else "none"}">
  <table class="suites-table"><thead><tr><th>Package / suite</th><th>Status</th><th>Tests</th><th>Passed</th><th>Failed</th><th>Skipped</th><th>Time</th></tr></thead><tbody>{"".join(suite_rows)}</tbody></table>
  </div>
</div>"""


# ---------------------------------------------------------------------------
# Lint rendering
# ---------------------------------------------------------------------------


def _render_lint_file(lf: LintFile) -> str:
    icon = (
        '<span class="status-icon status-pass">PASS</span>'
        if lf.status == "passed"
        else '<span class="status-icon status-fail">FAIL</span>'
    )
    details_html = f'<div class="case-details">{_esc(lf.details)}</div>' if lf.details else ""
    row_cls = "passed" if lf.status == "passed" else "failed"
    return f"""
              <tr class="case-row {row_cls}">
                <td>
                  <div class="case-name-line">{icon} <span class="case-name">{_esc(lf.name)}</span></div>
                  {details_html}
                </td>
              </tr>"""


def _render_lint_tools(pkg_idx: str, tools: list[LintTool]) -> str:
    html = []
    for j, tool in enumerate(tools):
        tid = f"lt-{pkg_idx}-{j}"
        badge_color = "#22c55e" if tool.failures == 0 else "#ef4444"
        badge_text = "PASS" if tool.failures == 0 else "FAIL"
        has_fail_cls = " has-fail" if tool.failures else ""
        counts = f'<span style="color:#22c55e">{tool.passed}✓</span>'
        if tool.failures:
            counts += f' <span style="color:#ef4444">{tool.failures}✗</span>'
        html.append(f"""
            <tr class="class-header lint-tool-header{has_fail_cls}" onclick="toggleLintTool('{tid}')">
              <td colspan="3">
                <span class="toggle" id="ttoggle-{tid}">▶</span>
                <span class="class-name lint-tool-name">{_esc(tool.name)}</span>
                <span class="class-counts">{counts} checks</span>
                <span class="badge" style="background:{badge_color}">{badge_text}</span>
              </td>
            </tr>
            <tr id="{tid}-files" class="class-cases" style="display:none">
              <td colspan="3" style="padding:0">
                <table class="cases-inner-table">
                  {"".join(_render_lint_file(lf) for lf in tool.files)}
                </table>
              </td>
            </tr>""")
    return "".join(html)


def _render_lint_section(lint_packages: list[LintPackage], section: str, title: str) -> str:
    if not lint_packages:
        return _empty_section(section, _esc(title), "0 issues reported.")

    total_pkg = len(lint_packages)
    total_files = sum(p.total_files for p in lint_packages)
    failed_pkg = sum(1 for p in lint_packages if p.failures > 0)
    overall_pass = failed_pkg == 0

    rows = []
    for index, pkg in enumerate(lint_packages):
        i = f"{section}-{index}"
        badge_color = "#22c55e" if pkg.failures == 0 else "#ef4444"
        badge_text = "PASS" if pkg.failures == 0 else "FAIL"
        rows.append(f"""
        <tr class="suite-header" onclick="toggleLintPkg('{i}')">
          <td><span class="toggle" id="ltoggle-{i}">▶</span> <strong>{_esc(pkg.package)}</strong></td>
          <td><span class="badge" style="background:{badge_color}">{badge_text}</span></td>
          <td>{pkg.total_files}</td>
          <td style="color:#22c55e;font-weight:600">{pkg.total_files - pkg.failures}</td>
          <td style="color:#ef4444;font-weight:600">{pkg.failures}</td>
        </tr>
        <tr id="lp-{i}-tools" class="suite-cases" style="display:none">
          <td colspan="5" style="padding:0">
            <table class="cases-table">
              {_render_lint_tools(i, pkg.tools)}
            </table>
          </td>
        </tr>""")

    status_color = "#22c55e" if overall_pass else "#ef4444"
    status_text = "PASSED" if overall_pass else "FAILED"
    collapsed = overall_pass
    body_display = "none" if collapsed else "block"
    arrow_cls = "" if collapsed else " open"

    return f"""
<div class="content" id="section-{section}" style="margin-top:8px">
  <div class="section-title collapsible" onclick="toggleSection('{section}')" style="display:flex;align-items:center;gap:12px">
    <span class="toggle section-toggle{arrow_cls}" id="section-{section}-toggle">▶</span>
    {_esc(title)}
    <span class="badge" style="background:{status_color};font-size:0.7rem">{status_text}</span>
    <span style="color:#475569;font-size:0.8rem;font-weight:400;text-transform:none;letter-spacing:0">{total_pkg} package{"s" if total_pkg != 1 else ""} &middot; {total_files} check{"s" if total_files != 1 else ""}{f", {failed_pkg} failing" if failed_pkg else ""}</span>
  </div>
  <div id="section-{section}-body" style="display:{body_display}">
  <table class="suites-table" style="margin-top:12px">
    <thead><tr><th>Package</th><th>Status</th><th>Checks</th><th>Passed</th><th>Failed</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
  </div>
</div>"""


# ---------------------------------------------------------------------------
# Coverage rendering
# ---------------------------------------------------------------------------


def _cov_bar(rate: float) -> str:
    """Render a small inline coverage bar."""
    pct = rate * 100
    color = "#22c55e" if pct >= 80 else ("#f59e0b" if pct >= 50 else "#ef4444")
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px">'
        f'<span style="display:inline-block;width:60px;height:7px;border-radius:4px;background:#1e293b;vertical-align:middle">'
        f'<span style="display:block;width:{min(pct, 100):.1f}%;height:100%;border-radius:4px;background:{color}"></span>'
        f"</span>"
        f'<span style="color:{color};font-weight:600;font-size:0.8rem">{pct:.0f}%</span>'
        f"</span>"
    )


def _render_coverage_section(
    cov_packages: list[CoveragePackage], report_output_path: Path, section: str, title: str
) -> str:
    if not sum(p.lines_valid for p in cov_packages):
        return _empty_section(section, _esc(title), "No executable lines.")

    total_covered = sum(p.lines_covered for p in cov_packages)
    total_valid = sum(p.lines_valid for p in cov_packages)
    overall_rate = total_covered / total_valid if total_valid else 0.0

    # Sort: lowest coverage first
    sorted_pkgs = sorted(cov_packages, key=lambda p: p.line_rate)

    # report_output_path is the HTML report file; coverage HTML dirs are siblings in build/
    report_dir = report_output_path.parent

    pkg_rows = []
    for index, pkg in enumerate(sorted_pkgs):
        pkg_idx = f"{section}-{index}"
        pct = pkg.line_rate * 100
        color = "#22c55e" if pct >= 80 else ("#f59e0b" if pct >= 50 else "#ef4444")

        # Link package name to the coverage index if available
        index_html = Path(pkg.html_dir) / "index.html" if pkg.html_dir else None
        if index_html and index_html.exists():
            try:
                rel = os.path.relpath(index_html, report_dir)
                pkg_link = f'<a href="{_esc(rel)}" target="_blank" style="color:#93c5fd;text-decoration:none">{_esc(pkg.package)}</a>'
            except ValueError:
                pkg_link = _esc(pkg.package)
        else:
            pkg_link = _esc(pkg.package)

        file_rows = []
        for file_idx, cov_file in enumerate(pkg.files):
            if cov_file.html_path:
                try:
                    rel = os.path.relpath(cov_file.html_path, report_dir)
                    file_name_html = f'<a href="{_esc(rel)}" target="_blank" style="color:#93c5fd;text-decoration:none">{_esc(cov_file.name)}</a>'
                except ValueError:
                    file_name_html = _esc(cov_file.name)
            else:
                file_name_html = f'<span style="color:#94a3b8">{_esc(cov_file.name)}</span>'

            file_rows.append(f"""
              <tr class="case-row">
                <td style="padding-left:56px;font-size:0.82rem;color:#94a3b8">{file_name_html}</td>
                <td style="white-space:nowrap">{_cov_bar(cov_file.line_rate)}</td>
                <td style="color:#475569;font-size:0.78rem;white-space:nowrap">{cov_file.lines_covered}/{cov_file.lines_valid}</td>
              </tr>""")

        pkg_rows.append(f"""
        <tr class="suite-header" onclick="toggleCovPkg('{pkg_idx}')">
          <td><span class="toggle" id="covtoggle-{pkg_idx}">▶</span> <strong>{pkg_link}</strong></td>
          <td>{_cov_bar(pkg.line_rate)}</td>
          <td style="color:{color};font-weight:600;white-space:nowrap">{pkg.lines_covered}/{pkg.lines_valid} lines</td>
          <td style="color:#475569;font-size:0.78rem">{len(pkg.files)} file{"s" if len(pkg.files) != 1 else ""}</td>
        </tr>
        <tr id="covpkg-{pkg_idx}-files" class="suite-cases" style="display:none">
          <td colspan="4" style="padding:0">
            <table class="cases-inner-table">
              {"".join(file_rows)}
            </table>
          </td>
        </tr>""")

    overall_color = "#22c55e" if overall_rate >= 0.8 else ("#f59e0b" if overall_rate >= 0.5 else "#ef4444")
    collapsed = overall_rate >= 0.995
    body_display = "none" if collapsed else "block"
    arrow_cls = "" if collapsed else " open"

    return f"""
<div class="content" id="section-{section}" style="margin-top:8px">
  <div class="section-title collapsible" onclick="toggleSection('{section}')" style="display:flex;align-items:center;gap:12px">
    <span class="toggle section-toggle{arrow_cls}" id="section-{section}-toggle">▶</span>
    {_esc(title)}
    <span style="color:{overall_color};font-weight:700;font-size:0.95rem">{overall_rate * 100:.1f}%</span>
    <span style="color:#475569;font-size:0.8rem;font-weight:400;text-transform:none;letter-spacing:0">{len(cov_packages)} package{"s" if len(cov_packages) != 1 else ""} &middot; {total_covered}/{total_valid} lines covered</span>
  </div>
  <div id="section-{section}-body" style="display:{body_display}">
  <table class="suites-table" style="margin-top:12px">
    <thead><tr><th>Package</th><th>Coverage</th><th>Lines</th><th>Files</th></tr></thead>
    <tbody>{"".join(pkg_rows)}</tbody>
  </table>
  </div>
</div>"""


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------


def _display_sections(sections: list[ReportSection]) -> list[ReportSection]:
    result = []
    coverage = []
    coverage_count = sum("coverage" in section.kinds for section in sections)
    for section in sections:
        if "coverage" not in section.kinds or len(section.kinds) == 1:
            result.append(section)
            continue
        result.append(
            dataclasses.replace(section, cov_packages=[], coverage_comparison=None,
                                kinds=[kind for kind in section.kinds if kind != "coverage"])
        )
        coverage.append(
            ReportSection(
                id=section.id,
                title="Coverage" if coverage_count == 1 else f"{section.title} — Coverage",
                cov_packages=section.cov_packages,
                kinds=["coverage"],
                coverage_comparison=section.coverage_comparison,
            )
        )
    lint_sources = [section for section in result if "lint" in section.kinds]
    mixed_lint = [section for section in lint_sources if "tests" in section.kinds]
    lint_targets = [section for section in lint_sources if "tests" not in section.kinds]
    if mixed_lint and len(lint_targets) == 1:
        target = lint_targets[0]
        packages = [
            dataclasses.replace(package, package=f"{source.title} — {package.package}")
            for source in lint_sources for package in source.lint_packages
        ]
        result[result.index(target)] = dataclasses.replace(target, lint_packages=packages)
    lint = []
    for section in mixed_lint:
        result[result.index(section)] = dataclasses.replace(section, lint_packages=[], kinds=["tests"])
        if len(lint_targets) != 1:
            lint.append(ReportSection(
                id=section.id,
                title="Lint" if len(lint_sources) == 1 else f"{section.title} — Lint",
                lint_packages=section.lint_packages,
                kinds=["lint"],
            ))
    return result + lint + coverage


def _coverage_delta(comparison: dict) -> str:
    delta = round(comparison["delta_pp"], 1)
    if not delta:
        return "unchanged (0.0 pp)"
    arrow = "↓ " if delta < 0 else "↑ "
    return f"{arrow}{abs(delta):.1f} pp"


def _coverage_comparison(comparison: dict, *, markdown: bool = False) -> str:
    escape = _md if markdown else _esc
    if comparison["status"] == "unavailable":
        return "Coverage comparison unavailable: " + escape(comparison["reason"])
    baseline = comparison["baseline"]
    repository = re.match(r"(https://[^/?#]+/[^/?#]+/[^/?#]+)/actions/runs/\d+(?:[/?#]|$)", baseline["run_url"])

    def link(label, url):
        label = escape(label)
        if not url:
            return label
        url = quote(url, safe=":/?&=#%")
        return f"[{label}]({url})" if markdown else f'<a href="{_esc(url)}">{label}</a>'

    def commit(sha):
        return link(sha[:7], f"{repository[1]}/commit/{sha}" if repository else None)

    result = (
        f'Baseline: {baseline["line_rate"] * 100:.1f}% at {commit(baseline["sha"])} '
        f'({link("CI run", baseline["run_url"])}).'
    )
    if comparison["status"] == "approximate":
        relation = "parent" if baseline.get("distance") == 1 else "earlier ancestor"
        result += f" Approximate comparison: baseline is the {relation} of the requested baseline"
        result += f' {commit(baseline["requested_sha"])}.' if baseline.get("requested_sha") else "."
    elif baseline.get("requested_sha") and baseline["requested_sha"] != baseline["sha"]:
        result += f' Requested baseline: {commit(baseline["requested_sha"])}.'
    if not markdown and baseline.get("created_at"):
        created = baseline["created_at"]
        try:
            timestamp = datetime.fromisoformat(created.replace("Z", "+00:00"))
            timestamp = timestamp.replace(tzinfo=timestamp.tzinfo or timezone.utc)
            created = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            pass
        result += f" Recorded {escape(created)}."
    return result


def render_html(
    sections: list[ReportSection],
    generated_at: str,
    title: str = "Build Report",
    output_path: Path = DEFAULT_REPORT_PATH,
    report_errors: list[str] | None = None,
    report_warnings: list[str] | None = None,
) -> str:
    sections = _display_sections(sections)
    repo_name = get_repo_name()
    title = f"{repo_name} — {title}" if repo_name else title
    overall_pass = not report_errors and not any(section.failures for section in sections)
    status_color = "#22c55e" if overall_pass else "#ef4444"
    status_text = "PASSED" if overall_pass else "FAILED"
    if overall_pass and (report_warnings or not sections):
        status_color = "#f59e0b"
        status_text = "WARNINGS" if sections else "NO RESULTS"

    summary = []
    content = []
    for index, section in enumerate(sections):
        # Positional namespaces cannot collide with user IDs or subsection suffixes.
        key = f"group-{index}"
        cards = []
        parts = []
        mixed = len(section.kinds) > 1
        for kind in ("tests", "lint", "coverage"):
            if kind not in section.kinds:
                continue
            part_key = f"{key}-{kind}" if mixed else key
            part_title = kind.title() if mixed else section.title
            if kind == "tests":
                total = sum(s.tests for s in section.suites)
                failed = sum(s.failures + s.errors for s in section.suites)
                skipped = sum(s.skipped for s in section.suites)
                cards.extend(
                    [
                        ("Tests", total, "#94a3b8"),
                        ("Passed", total - failed - skipped, "#22c55e"),
                        ("Failed", failed, "#ef4444"),
                        ("Skipped", skipped, "#f59e0b"),
                    ]
                )
                parts.append(_render_test_section(section.suites, part_key, part_title))
            elif kind == "lint":
                files = sum(p.total_files for p in section.lint_packages)
                failed = sum(p.failures for p in section.lint_packages)
                if files:
                    cards.append(("Reported checks", files, "#a5b4fc"))
                cards.append(("Lint issues", failed, "#ef4444" if failed else "#a5b4fc"))
                parts.append(_render_lint_section(section.lint_packages, part_key, part_title))
            else:
                covered = sum(p.lines_covered for p in section.cov_packages)
                valid = sum(p.lines_valid for p in section.cov_packages)
                cards.extend(
                    [
                        ("Coverage", f"{covered / valid * 100:.1f}%" if valid else "—", "#67e8f9"),
                        ("Covered lines", covered, "#67e8f9"),
                        ("Total lines", valid, "#94a3b8"),
                    ]
                )
                parts.append(_render_coverage_section(section.cov_packages, output_path, part_key, part_title))
                if section.coverage_comparison:
                    if section.coverage_comparison["status"] != "unavailable":
                        cards.append(("Change", _coverage_delta(section.coverage_comparison), "#67e8f9"))
                    parts.append(f'<p class="content">{_coverage_comparison(section.coverage_comparison)}</p>')
        summary.append(_summary_group(key, section.title, cards))
        if mixed:
            content.append(
                f'<section id="section-{key}"><h2 class="content section-title">{_esc(section.title)}</h2>{"".join(parts)}</section>'
            )
        elif parts:
            content.extend(parts)
        else:
            content.append(_empty_section(key, _esc(section.title), "No identifiable results."))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }}
  .header {{ background: #1e293b; border-bottom: 1px solid #334155; padding: 12px 24px; display: flex; align-items: center; gap: 8px 16px; flex-wrap: wrap; }}
  .header h1 {{ font-size: 1.25rem; font-weight: 700; color: #f8fafc; white-space: nowrap; }}
  .overall-badge {{ font-size: 0.7rem; font-weight: 700; padding: 2px 8px; border-radius: 10px; color: #fff; background: {
        status_color
    }; }}
  .summary {{ display: flex; flex-wrap: wrap; gap: 8px; padding: 8px 12px; }}
  .stat-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 6px 10px; flex: 1 1 80px; text-align: center; box-sizing: border-box; }}
  .stat-card .val {{ font-size: clamp(0.9rem, 2vw, 1.5rem); font-weight: 700; line-height: 1; }}
  .stat-card .lbl {{ font-size: 0.7rem; color: #94a3b8; margin-top: 3px; text-transform: uppercase; letter-spacing: 0.05em; }}
  .content {{ padding: 0 12px 8px; }}
  .section-title {{ font-size: 1rem; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 12px; margin-bottom: 12px; }}
  .suites-table {{ width: 100%; border-collapse: collapse; background: #1e293b; border: 1px solid #334155; border-radius: 10px; overflow: hidden; }}
  .suites-table th {{ background: #0f172a; color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 14px; text-align: left; font-weight: 600; }}
  .suites-table th:nth-child(2), .suites-table td:nth-child(2) {{ width: 60px; min-width: 60px; padding-left: 5px; }}
  .suite-header {{ cursor: pointer; transition: background 0.15s; }}
  .suite-header:hover {{ background: #273549; }}
  .suite-header td {{ padding: 12px 14px; border-top: 1px solid #334155; font-size: 0.9rem; white-space: nowrap; }}
  .suite-header td:first-child {{ padding-right: 5px; }}
  .suite-header td:nth-child(2) {{ padding-left: 5px; }}
  .toggle {{ display: inline-block; width: 16px; color: #64748b; transition: transform 0.2s; font-size: 0.7rem; }}
  .toggle.open {{ transform: rotate(90deg); }}
  .badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.7rem; font-weight: 700; color: #fff; }}
  .cases-table {{ width: 100%; border-collapse: collapse; background: #111827; }}
  .class-header {{ cursor: pointer; transition: background 0.15s; }}
  .class-header:hover {{ background: #1a2535; }}
  .class-header td {{ padding: 9px 14px 9px 28px; border-top: 1px solid #1e293b; font-size: 0.85rem; white-space: nowrap; }}
  .class-name {{ color: #93c5fd; font-weight: 600; margin-right: 10px; }}
  .lint-tool-name {{ color: #c4b5fd; }}
  .class-counts {{ font-size: 0.78rem; margin-left: 6px; display: inline-flex; gap: 8px; }}
  .cases-inner-table {{ width: 100%; border-collapse: collapse; }}
  .case-row td {{ padding: 7px 14px 7px 42px; font-size: 0.85rem; border-top: 1px solid #0f172a; vertical-align: top; width: 100%; }}
  .case-row.failed td {{ background: #1c0a0a; }}
  .case-row.error td {{ background: #1c0a0a; }}
  .case-row.skipped td {{ background: #1a1a0a; }}
  .case-row.passed td {{ background: #09180e; }}
  .case-name-line {{ display: flex; align-items: baseline; gap: 8px; flex-wrap: nowrap; min-width: 0; }}
  .status-icon {{ font-size: 0.75rem; font-weight: 700; padding: 1px 7px; border-radius: 8px; white-space: nowrap; flex-shrink: 0; }}
  .status-pass {{ background: #14532d; color: #86efac; }}
  .status-fail {{ background: #7f1d1d; color: #fca5a5; }}
  .status-error {{ background: #7f1d1d; color: #fca5a5; }}
  .status-skip {{ background: #713f12; color: #fcd34d; }}
  .case-name {{ color: #cbd5e1; word-break: break-all; flex: 1; min-width: 0; }}
  .case-time {{ color: #475569; font-size: 0.75rem; white-space: nowrap; flex-shrink: 0; margin-left: auto; }}
  .case-msg {{ color: #fca5a5; font-size: 0.8rem; margin-top: 4px; }}
  .case-details {{ margin-top: 8px; padding: 10px 12px; background: #000; border-radius: 6px; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 0.75rem; color: #e2e8f0; white-space: pre-wrap; word-break: break-all; max-height: 400px; overflow-y: auto; border: 1px solid #334155; }}
  .no-suites {{ padding: 60px; text-align: center; color: #64748b; }}
  .stat-group {{ display: flex; flex-direction: column; gap: 4px; border: 1px solid #334155; border-radius: 8px; padding: 6px 10px; background: #0f172a; cursor: pointer; transition: border-color 0.15s; flex: 1 1 auto; min-width: 200px; }}
  .stat-group:hover {{ border-color: #64748b; }}
  .section-title.collapsible {{ cursor: pointer; user-select: none; }}
  .section-title.collapsible:hover {{ color: #cbd5e1; }}
  .section-toggle {{ font-size: 0.8rem; }}
  .stat-group-label {{ font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; overflow-wrap: anywhere; }}
  .stat-group-cards {{ display: flex; gap: 8px; flex-wrap: wrap; }}
</style>
</head>
<body>
<div class="header">
  <h1>{_esc(title)}</h1>
  <span class="overall-badge">{status_text}</span>
</div>
<div class="summary">{"".join(summary)}</div>
{"".join(content)}
<script>
function toggleSection(name) {{
  const body = document.getElementById('section-' + name + '-body');
  const tgl = document.getElementById('section-' + name + '-toggle');
  const open = body.style.display === 'none';
  body.style.display = open ? 'block' : 'none';
  tgl.classList.toggle('open', open);
}}
function toggleSuite(i) {{
  const el = document.getElementById('suite-' + i + '-cases');
  const tgl = document.getElementById('toggle-' + i);
  const open = el.style.display === 'none';
  el.style.display = open ? '' : 'none';
  tgl.classList.toggle('open', open);
}}
function toggleClass(id) {{
  const el = document.getElementById('cg-' + id + '-cases');
  const tgl = document.getElementById('ctoggle-' + id);
  const open = el.style.display === 'none';
  el.style.display = open ? '' : 'none';
  tgl.classList.toggle('open', open);
}}
function toggleLintPkg(i) {{
  const el = document.getElementById('lp-' + i + '-tools');
  const tgl = document.getElementById('ltoggle-' + i);
  const open = el.style.display === 'none';
  el.style.display = open ? '' : 'none';
  tgl.classList.toggle('open', open);
}}
function toggleLintTool(id) {{
  const el = document.getElementById(id + '-files');
  const tgl = document.getElementById('ttoggle-' + id);
  const open = el.style.display === 'none';
  el.style.display = open ? '' : 'none';
  tgl.classList.toggle('open', open);
}}
function toggleCovPkg(i) {{
  const el = document.getElementById('covpkg-' + i + '-files');
  const tgl = document.getElementById('covtoggle-' + i);
  const open = el.style.display === 'none';
  el.style.display = open ? '' : 'none';
  tgl.classList.toggle('open', open);
}}
// Auto-expand test class groups with failures and their parent suites
document.querySelectorAll('.class-header.has-fail').forEach(el => {{
  const onclick = el.getAttribute('onclick') || '';
  const mClass = onclick.match(/toggleClass\\('(.+?)'\\)/);
  if (mClass) {{
    const id = mClass[1];
    const cgEl = document.getElementById('cg-' + id + '-cases');
    const cgTgl = document.getElementById('ctoggle-' + id);
    if (cgEl) {{ cgEl.style.display = ''; cgTgl?.classList.add('open'); }}
    const suiteCases = el.closest('.suite-cases');
    if (suiteCases) {{
      suiteCases.style.display = '';
      const idx = suiteCases.id.slice('suite-'.length, -'-cases'.length);
      document.getElementById('toggle-' + idx)?.classList.add('open');
    }}
  }}
}});
// Auto-expand lint tools with failures and their parent packages
document.querySelectorAll('.lint-tool-header.has-fail').forEach(el => {{
  const m = el.getAttribute('onclick').match(/toggleLintTool\\('(.+?)'\\)/);
  if (!m) return;
  const id = m[1];
  const toolEl = document.getElementById(id + '-files');
  const toolTgl = document.getElementById('ttoggle-' + id);
  if (toolEl) {{ toolEl.style.display = ''; toolTgl?.classList.add('open'); }}
  const pkgCases = el.closest('.suite-cases');
  if (pkgCases) {{
    pkgCases.style.display = '';
    const pkgIdx = pkgCases.id.slice('lp-'.length, -'-tools'.length);
    document.getElementById('ltoggle-' + pkgIdx)?.classList.add('open');
  }}
}});
</script>
<div class="generated" style="text-align:center;padding:16px;color:#64748b;font-size:0.75rem">Generated {
        _esc(generated_at)
    }</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Markdown summary rendering ($GITHUB_STEP_SUMMARY / PR comments)
# ---------------------------------------------------------------------------


def render_markdown_summary(
    sections: list[ReportSection],
    title: str = "Build Report",
    max_items: int = 30,
    report_errors: list[str] | None = None,
    report_warnings: list[str] | None = None,
) -> str:
    sections = _display_sections(sections)
    overall_pass = not report_errors and not any(section.failures for section in sections)
    status = "✅ PASSED" if overall_pass else "❌ FAILED"
    if overall_pass and (report_warnings or not sections):
        status = "⚠️ WARNINGS" if sections else "⚠️ NO RESULTS"
    lines = [f"### {title} — {status}", ""]
    details = []
    if sections:
        lines.extend(["| Section | Result | Details |", "| --- | --- | --- |"])
    for section in sections:
        parts = []
        result = "—"
        if "tests" in section.kinds:
            total = sum(s.tests for s in section.suites)
            failed = sum(s.failures + s.errors for s in section.suites)
            skipped = sum(s.skipped for s in section.suites)
            counts = [f"{total - failed - skipped} passed"]
            if failed:
                counts.append(f"{failed} failed")
            if skipped:
                counts.append(f"{skipped} skipped")
            parts.append(("Tests", ", ".join(counts) if total else "no tests collected"))
            result = "✅" if total else "⚠️"
        if "lint" in section.kinds:
            files = sum(p.total_files for p in section.lint_packages)
            failed = sum(p.failures for p in section.lint_packages)
            word = "check" if files == 1 else "checks"
            detail = (
                f"{failed} failed of {files} {word}" if failed else f"{files} {word} passed" if files else "0 issues"
            )
            parts.append(("Lint", detail))
            if result == "—":
                result = "✅"
        if "coverage" in section.kinds:
            covered = sum(p.lines_covered for p in section.cov_packages)
            valid = sum(p.lines_valid for p in section.cov_packages)
            if result == "—":
                result = "📊" if valid else "⚠️"
            detail = "no executable lines"
            if valid:
                rate = covered / valid
                detail = f"{rate * 100:.1f}% ({covered:,}/{valid:,} lines)"
                if section.coverage_comparison and section.coverage_comparison["status"] != "unavailable":
                    detail += " · " + _coverage_delta(section.coverage_comparison)
                elif section.coverage_comparison:
                    result = "⚠️"
            parts.append(("Coverage", detail))
        if section.failures:
            result = "❌"
        detail = "; ".join(f"{kind}: {text}" if len(parts) > 1 else text for kind, text in parts)
        lines.append(f"| {_md(section.title)} | {result if parts else '⚠️'} | {detail or 'no identifiable results'} |")

        if section.coverage_comparison:
            label = f"**{_md(section.title)}** — " if section.title != "Coverage" else ""
            details.extend(["", label + _coverage_comparison(section.coverage_comparison, markdown=True)])
        items = []
        for suite in sorted(section.suites, key=lambda s: (s.package, s.name)):
            for case in suite.cases:
                if case.status not in ("failed", "error"):
                    continue
                label = f"{case.classname}::{case.name}" if case.classname else case.name
                messages = (case.message or case.details).strip().splitlines()
                first = _md(messages[0][:200]) if messages else ""
                items.append(f"- {_md(label)} ({_md(suite.package)})" + (f" — {first}" if first else ""))
        items.extend(
            f"- {_md(lf.name)} — {_md(tool.name)}: {len(lf.details.splitlines()) or 1} error(s)"
            for pkg in section.lint_packages
            for tool in pkg.tools
            for lf in tool.files
            if lf.status == "failed"
        )
        if items:
            details.extend(["", f"<details><summary>{_esc(section.title)} failures ({section.failures})</summary>", ""])
            details.extend(items[:max_items])
            if len(items) > max_items:
                details.append(f"- …and {len(items) - max_items} more — see the full report artifact")
            details.extend(["", "</details>"])
    return "\n".join(lines + details) + "\n"


# ---------------------------------------------------------------------------
# Portable report JSON
# ---------------------------------------------------------------------------


def _save_report_data(json_path: Path, sections: list[ReportSection]) -> None:
    data = {"report_sections": [dataclasses.asdict(section) for section in sections]}
    for section in data["report_sections"]:
        if section["coverage_comparison"] is None:
            del section["coverage_comparison"]
        for package in section["cov_packages"]:
            # Machine-local coverage links cannot resolve on another runner.
            package["html_dir"] = ""
            for file in package["files"]:
                file["html_path"] = ""
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_data(data: dict) -> tuple[list[TestSuite], list[TestSuite], list[LintPackage], list[CoveragePackage]]:
    def load_suites(items):
        return [
            TestSuite(
                **{k: v for k, v in item.items() if k != "cases"},
                cases=[TestCase(**case) for case in item.get("cases", [])],
            )
            for item in items
        ]

    lint = [
        LintPackage(
            package=p["package"],
            tools=[
                LintTool(name=t["name"], files=[LintFile(**f) for f in t.get("files", [])]) for t in p.get("tools", [])
            ],
        )
        for p in data.get("lint_packages", [])
    ]
    coverage = [
        CoveragePackage(
            **{k: v for k, v in p.items() if k != "files"}, files=[CoverageFile(**f) for f in p.get("files", [])]
        )
        for p in data.get("cov_packages", [])
    ]
    return load_suites(data.get("suites", [])), load_suites(data.get("system_suites", [])), lint, coverage


def _load_report_data(json_path: Path):
    data = json.loads(json_path.read_text(encoding="utf-8"))
    result = _load_data(data)
    for section in data.get("report_sections", []):
        for destination, values in zip(result, _load_data(section)):
            destination.extend(values)
    return result


def _load_report_sections(json_path: Path) -> list[ReportSection]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    sections = []
    for section in data["report_sections"]:
        suites, system_suites, lint, coverage = _load_data(section)
        sections.append(
            ReportSection(
                id=section["id"],
                title=section["title"],
                suites=suites + system_suites,
                lint_packages=lint,
                cov_packages=coverage,
                kinds=section["kinds"],
                coverage_comparison=section.get("coverage_comparison"),
            )
        )
    return sections
