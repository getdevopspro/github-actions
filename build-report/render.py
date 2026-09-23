"""Parse build results and render standalone HTML and Markdown reports."""

import dataclasses
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

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


def _render_class_groups(suite_idx: int, cases: list[TestCase]) -> str:
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


# ---------------------------------------------------------------------------
# System test rendering
# ---------------------------------------------------------------------------


def _render_system_test_section(suites: list[TestSuite]) -> str:
    if not suites:
        return ""

    # Group suites by package; sort failing packages first then alphabetical
    pkg_groups: dict[str, list[TestSuite]] = {}
    for suite in suites:
        pkg_groups.setdefault(suite.package, []).append(suite)
    sorted_packages = sorted(pkg_groups.items(), key=lambda x: (all(s.failures + s.errors == 0 for s in x[1]), x[0]))

    total_tests = sum(s.tests for s in suites)
    total_failures = sum(s.failures + s.errors for s in suites)
    overall_pass = total_failures == 0
    status_color = "#22c55e" if overall_pass else "#ef4444"
    status_text = "PASSED" if overall_pass else "FAILED"
    collapsed = overall_pass
    body_display = "none" if collapsed else "block"
    arrow_cls = "" if collapsed else " open"

    pkg_rows = []
    for pkg_idx, (package, pkg_suites) in enumerate(sorted_packages):
        pkg_tests = sum(s.tests for s in pkg_suites)
        pkg_failures = sum(s.failures + s.errors for s in pkg_suites)
        pkg_skipped = sum(s.skipped for s in pkg_suites)
        pkg_passed = pkg_tests - pkg_failures - pkg_skipped
        pkg_time = sum(s.time for s in pkg_suites)
        pkg_badge_color = "#22c55e" if pkg_failures == 0 else "#ef4444"

        # Sort test files within package: failing first
        pkg_suites_sorted = sorted(pkg_suites, key=lambda s: (s.failures + s.errors == 0, s.name))

        file_rows = []
        for file_idx, suite in enumerate(pkg_suites_sorted):
            file_name = suite.name.split("/")[-1] if "/" in suite.name else suite.name
            file_failures = suite.failures + suite.errors
            file_passed = suite.tests - file_failures - suite.skipped
            file_badge_color = "#22c55e" if file_failures == 0 else "#ef4444"
            fid = f"sysfile-{pkg_idx}-{file_idx}"
            has_file_fail_cls = " has-fail" if file_failures else ""
            counts = f'<span style="color:#22c55e">{file_passed}✓</span>'
            if file_failures:
                counts += f' <span style="color:#ef4444">{file_failures}✗</span>'
            if suite.skipped:
                counts += f' <span style="color:#f59e0b">{suite.skipped} skip</span>'
            file_rows.append(f"""
            <tr class="class-header{has_file_fail_cls}" onclick="toggleSysFile('{fid}')">
              <td colspan="3">
                <span class="toggle" id="ftoggle-{fid}">▶</span>
                <span class="class-name">{_esc(file_name)}</span>
                <span class="class-counts">{counts}</span>
                <span class="badge" style="background:{file_badge_color}">{"PASS" if file_failures == 0 else "FAIL"}</span>
              </td>
            </tr>
            <tr id="{fid}-cases" class="class-cases" style="display:none">
              <td colspan="3" style="padding:0">
                <table class="cases-inner-table">
                  {"".join(_render_case(tc) for tc in suite.cases)}
                </table>
              </td>
            </tr>""")

        pkg_rows.append(f"""
        <tr class="suite-header" onclick="toggleSysPkg({pkg_idx})">
          <td><span class="toggle" id="syspkgtoggle-{pkg_idx}">▶</span> <strong>{_esc(package)}</strong></td>
          <td><span class="badge" style="background:{pkg_badge_color}">{"PASS" if pkg_failures == 0 else "FAIL"}</span></td>
          <td>{pkg_tests}</td>
          <td style="color:#22c55e;font-weight:600">{pkg_passed}</td>
          <td style="color:#ef4444;font-weight:600">{pkg_failures}</td>
          <td style="color:#f59e0b;font-weight:600">{pkg_skipped}</td>
          <td>{pkg_time:.3f}s</td>
        </tr>
        <tr id="syspkg-{pkg_idx}-suites" class="suite-cases" style="display:none">
          <td colspan="7" style="padding:0">
            <table class="cases-table">
              {"".join(file_rows)}
            </table>
          </td>
        </tr>""")

    return f"""
<div class="content" id="section-system" style="margin-top:8px">
  <div class="section-title collapsible" onclick="toggleSection('system')" style="display:flex;align-items:center;gap:12px">
    <span class="toggle section-toggle{arrow_cls}" id="section-system-toggle">▶</span>
    System Tests
    <span class="badge" style="background:{status_color};font-size:0.7rem">{status_text}</span>
    <span style="color:#475569;font-size:0.8rem;font-weight:400;text-transform:none;letter-spacing:0">{len(sorted_packages)} package{"s" if len(sorted_packages) != 1 else ""} &middot; {total_tests} tests{f", {total_failures} failing" if total_failures else ""}</span>
  </div>
  <div id="section-system-body" style="display:{body_display}">
  <table class="suites-table" style="margin-top:12px">
    <thead><tr><th>Package</th><th>Status</th><th>Tests</th><th>Passed</th><th>Failed</th><th>Skipped</th><th>Time</th></tr></thead>
    <tbody>{"".join(pkg_rows)}</tbody>
  </table>
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


def _render_lint_tools(pkg_idx: int, tools: list[LintTool]) -> str:
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
                <span class="class-counts">{counts} files</span>
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


def _render_lint_section(lint_packages: list[LintPackage]) -> str:
    if not lint_packages:
        return ""

    total_pkg = len(lint_packages)
    total_files = sum(p.total_files for p in lint_packages)
    failed_pkg = sum(1 for p in lint_packages if p.failures > 0)
    overall_pass = failed_pkg == 0

    rows = []
    for i, pkg in enumerate(lint_packages):
        badge_color = "#22c55e" if pkg.failures == 0 else "#ef4444"
        badge_text = "PASS" if pkg.failures == 0 else "FAIL"
        rows.append(f"""
        <tr class="suite-header" onclick="toggleLintPkg({i})">
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
<div class="content" id="section-lint" style="margin-top:8px">
  <div class="section-title collapsible" onclick="toggleSection('lint')" style="display:flex;align-items:center;gap:12px">
    <span class="toggle section-toggle{arrow_cls}" id="section-lint-toggle">▶</span>
    Lint
    <span class="badge" style="background:{status_color};font-size:0.7rem">{status_text}</span>
    <span style="color:#475569;font-size:0.8rem;font-weight:400;text-transform:none;letter-spacing:0">{total_pkg} package{"s" if total_pkg != 1 else ""} &middot; {total_files} file{"s" if total_files != 1 else ""}{f", {failed_pkg} failing" if failed_pkg else ""}</span>
  </div>
  <div id="section-lint-body" style="display:{body_display}">
  <table class="suites-table" style="margin-top:12px">
    <thead><tr><th>Package</th><th>Status</th><th>Files</th><th>Passed</th><th>Failed</th></tr></thead>
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


def _render_coverage_section(cov_packages: list[CoveragePackage], report_output_path: Path) -> str:
    if not cov_packages:
        return ""

    total_covered = sum(p.lines_covered for p in cov_packages)
    total_valid = sum(p.lines_valid for p in cov_packages)
    overall_rate = total_covered / total_valid if total_valid else 0.0

    # Sort: lowest coverage first
    sorted_pkgs = sorted(cov_packages, key=lambda p: p.line_rate)

    # report_output_path is the HTML report file; coverage HTML dirs are siblings in build/
    report_dir = report_output_path.parent

    pkg_rows = []
    for pkg_idx, pkg in enumerate(sorted_pkgs):
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
        <tr class="suite-header" onclick="toggleCovPkg({pkg_idx})">
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
<div class="content" id="section-coverage" style="margin-top:8px">
  <div class="section-title collapsible" onclick="toggleSection('coverage')" style="display:flex;align-items:center;gap:12px">
    <span class="toggle section-toggle{arrow_cls}" id="section-coverage-toggle">▶</span>
    Code Coverage
    <span style="color:{overall_color};font-weight:700;font-size:0.95rem">{overall_rate * 100:.1f}%</span>
    <span style="color:#475569;font-size:0.8rem;font-weight:400;text-transform:none;letter-spacing:0">{len(cov_packages)} package{"s" if len(cov_packages) != 1 else ""} &middot; {total_covered}/{total_valid} lines covered</span>
  </div>
  <div id="section-coverage-body" style="display:{body_display}">
  <table class="suites-table" style="margin-top:12px">
    <thead><tr><th>Package</th><th>Coverage</th><th>Lines</th><th>Files</th></tr></thead>
    <tbody>{"".join(pkg_rows)}</tbody>
  </table>
  </div>
</div>"""


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------


def render_html(
    suites: list[TestSuite],
    system_suites: list[TestSuite],
    lint_packages: list[LintPackage],
    cov_packages: list[CoveragePackage],
    generated_at: str,
    title: str = "Test Report",
    output_path: Path = DEFAULT_REPORT_PATH,
    report_errors: list[str] | None = None,
) -> str:
    repo_name = get_repo_name()
    title = f"{repo_name} — {title}" if repo_name else title

    total_tests = sum(s.tests for s in suites)
    total_failures = sum(s.failures for s in suites)
    total_errors = sum(s.errors for s in suites)
    total_skipped = sum(s.skipped for s in suites)
    total_passed = total_tests - total_failures - total_errors - total_skipped
    lint_total_files = sum(p.total_files for p in lint_packages)
    lint_failures = sum(p.failures for p in lint_packages)
    sys_total = sum(s.tests for s in system_suites)
    sys_failures = sum(s.failures + s.errors for s in system_suites)
    sys_skipped = sum(s.skipped for s in system_suites)
    sys_passed = sys_total - sys_failures - sys_skipped
    cov_covered = sum(p.lines_covered for p in cov_packages)
    cov_valid = sum(p.lines_valid for p in cov_packages)
    cov_rate = cov_covered / cov_valid if cov_valid else 0.0
    overall_pass = (
        not report_errors and total_failures == 0 and total_errors == 0 and lint_failures == 0 and sys_failures == 0
    )

    status_color = "#22c55e" if overall_pass else "#ef4444"
    status_text = "PASSED" if overall_pass else "FAILED"

    suites = sorted(suites, key=lambda s: (s.failures + s.errors == 0, s.package))

    suite_rows = []
    for i, suite in enumerate(suites):
        passed = suite.tests - suite.failures - suite.errors - suite.skipped
        suite_status = "pass" if (suite.failures == 0 and suite.errors == 0) else "fail"
        badge_color = "#22c55e" if suite_status == "pass" else "#ef4444"
        suite_rows.append(f"""
        <tr class="suite-header" onclick="toggleSuite({i})">
          <td><span class="toggle" id="toggle-{i}">▶</span> <strong>{_esc(suite.package)}</strong></td>
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

    system_html = _render_system_test_section(system_suites)
    lint_html = _render_lint_section(lint_packages)
    coverage_html = _render_coverage_section(cov_packages, output_path)

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
  .stat-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 6px 10px; flex: 1 1 0; min-width: 0; text-align: center; box-sizing: border-box; }}
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
  .stat-group-label {{ font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; white-space: nowrap; }}
  .stat-group-cards {{ display: flex; gap: 8px; flex-wrap: nowrap; }}
</style>
</head>
<body>
<div class="header">
  <h1>{_esc(title)}</h1>
  <span class="overall-badge">{status_text}</span>
</div>
<div class="summary">
  <div class="stat-group" onclick="document.getElementById('section-unit').scrollIntoView({{behavior:'smooth'}})">
    <div class="stat-group-label">Unit Tests</div>
    <div class="stat-group-cards">
      <div class="stat-card"><div class="val" style="color:#94a3b8">{
        total_tests
    }</div><div class="lbl">Total</div></div>
      <div class="stat-card"><div class="val" style="color:#22c55e">{
        total_passed
    }</div><div class="lbl">Passed</div></div>
      <div class="stat-card"><div class="val" style="color:#ef4444">{
        total_failures + total_errors
    }</div><div class="lbl">Failed</div></div>
      <div class="stat-card"><div class="val" style="color:#f59e0b">{
        total_skipped
    }</div><div class="lbl">Skipped</div></div>
    </div>
  </div>
  <div class="stat-group" onclick="document.getElementById('section-system').scrollIntoView({{behavior:'smooth'}})">
    <div class="stat-group-label">System Tests</div>
    <div class="stat-group-cards">
      <div class="stat-card" style="border-color:#0e4429"><div class="val" style="color:#94a3b8">{
        sys_total
    }</div><div class="lbl">Total</div></div>
      <div class="stat-card" style="border-color:#0e4429"><div class="val" style="color:#22c55e">{
        sys_passed
    }</div><div class="lbl">Passed</div></div>
      <div class="stat-card" style="border-color:#0e4429"><div class="val" style="color:{
        "#ef4444" if sys_failures else "#22c55e"
    }">{sys_failures}</div><div class="lbl">Failed</div></div>
      <div class="stat-card" style="border-color:#0e4429"><div class="val" style="color:#f59e0b">{
        sys_skipped
    }</div><div class="lbl">Skipped</div></div>
    </div>
  </div>
  <div class="stat-group" onclick="document.getElementById('section-lint').scrollIntoView({{behavior:'smooth'}})">
    <div class="stat-group-label">Lint</div>
    <div class="stat-group-cards">
      <div class="stat-card" style="border-color:#312e81"><div class="val" style="color:#a5b4fc">{
        lint_total_files
    }</div><div class="lbl">Files</div></div>
      <div class="stat-card" style="border-color:#312e81"><div class="val" style="color:{
        "#ef4444" if lint_failures else "#a5b4fc"
    }">{lint_failures}</div><div class="lbl">Errors</div></div>
    </div>
  </div>
  <div class="stat-group" onclick="document.getElementById('section-coverage').scrollIntoView({{behavior:'smooth'}})">
    <div class="stat-group-label">Coverage</div>
    <div class="stat-group-cards">
      <div class="stat-card" style="border-color:#164e63"><div class="val" style="color:{
        "#22c55e" if cov_rate >= 0.8 else ("#f59e0b" if cov_rate >= 0.5 else "#ef4444")
    }">{cov_rate * 100:.0f}%</div><div class="lbl">Lines</div></div>
      <div class="stat-card" style="border-color:#164e63"><div class="val" style="color:#67e8f9">{
        cov_covered
    }</div><div class="lbl">Covered</div></div>
      <div class="stat-card" style="border-color:#164e63"><div class="val" style="color:#94a3b8">{
        cov_valid
    }</div><div class="lbl">Total</div></div>
    </div>
  </div>
</div>
{
        f'''<div class="content" id="section-unit">
  <div class="section-title collapsible" onclick="toggleSection('unit')" style="display:flex;align-items:center;gap:12px">
    <span class="toggle section-toggle{" open" if total_failures + total_errors > 0 else ""}" id="section-unit-toggle">▶</span>
    Unit Tests
    <span class="badge" style="background:{"#22c55e" if total_failures + total_errors == 0 else "#ef4444"};font-size:0.7rem">{"PASSED" if total_failures + total_errors == 0 else "FAILED"}</span>
    <span style="color:#475569;font-size:0.8rem;font-weight:400;text-transform:none;letter-spacing:0">{len(suites)} suite{"s" if len(suites) != 1 else ""} &middot; {total_tests} tests{f", {total_failures + total_errors} failing" if total_failures + total_errors else ""}</span>
  </div>
  <div id="section-unit-body" style="display:{"block" if total_failures + total_errors > 0 else "none"}">
  <table class="suites-table"><thead><tr><th>Package</th><th>Status</th><th>Tests</th><th>Passed</th><th>Failed</th><th>Skipped</th><th>Time</th></tr></thead><tbody>{"".join(suite_rows)}</tbody></table>
  </div>
</div>'''
        if suites
        else ""
    }
{system_html}
{lint_html}
{coverage_html}
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
function toggleSysPkg(i) {{
  const el = document.getElementById('syspkg-' + i + '-suites');
  const tgl = document.getElementById('syspkgtoggle-' + i);
  const open = el.style.display === 'none';
  el.style.display = open ? '' : 'none';
  tgl.classList.toggle('open', open);
}}
function toggleSysFile(id) {{
  const el = document.getElementById(id + '-cases');
  const tgl = document.getElementById('ftoggle-' + id);
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
// Auto-expand unit test class groups with failures and their parent suites
document.querySelectorAll('.class-header.has-fail').forEach(el => {{
  const onclick = el.getAttribute('onclick') || '';
  const mClass = onclick.match(/toggleClass\\('(.+?)'\\)/);
  const mFile = onclick.match(/toggleSysFile\\('(.+?)'\\)/);
  if (mClass) {{
    const id = mClass[1];
    const cgEl = document.getElementById('cg-' + id + '-cases');
    const cgTgl = document.getElementById('ctoggle-' + id);
    if (cgEl) {{ cgEl.style.display = ''; cgTgl?.classList.add('open'); }}
    const suiteCases = el.closest('.suite-cases');
    if (suiteCases) {{
      suiteCases.style.display = '';
      const idx = suiteCases.id.replace('suite-', '').replace('-cases', '');
      document.getElementById('toggle-' + idx)?.classList.add('open');
    }}
  }} else if (mFile) {{
    const id = mFile[1];
    const fileEl = document.getElementById(id + '-cases');
    const fileTgl = document.getElementById('ftoggle-' + id);
    if (fileEl) {{ fileEl.style.display = ''; fileTgl?.classList.add('open'); }}
    const pkgCases = el.closest('.suite-cases');
    if (pkgCases) {{
      pkgCases.style.display = '';
      const idx = pkgCases.id.replace('syspkg-', '').replace('-suites', '');
      document.getElementById('syspkgtoggle-' + idx)?.classList.add('open');
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
    const pkgIdx = pkgCases.id.replace('lp-', '').replace('-tools', '');
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
    suites: list[TestSuite],
    system_suites: list[TestSuite],
    lint_packages: list[LintPackage],
    cov_packages: list[CoveragePackage],
    title: str = "Test Report",
    max_items: int = 30,
    baseline_cov_rate: float | None = None,
    report_errors: list[str] | None = None,
) -> str:
    total = sum(s.tests for s in suites)
    failures = sum(s.failures + s.errors for s in suites)
    skipped = sum(s.skipped for s in suites)
    passed = total - failures - skipped
    sys_total = sum(s.tests for s in system_suites)
    sys_fail = sum(s.failures + s.errors for s in system_suites)
    sys_skipped = sum(s.skipped for s in system_suites)
    sys_passed = sys_total - sys_fail - sys_skipped
    lint_files = sum(p.total_files for p in lint_packages)
    lint_fail = sum(p.failures for p in lint_packages)
    cov_covered = sum(p.lines_covered for p in cov_packages)
    cov_valid = sum(p.lines_valid for p in cov_packages)
    overall_pass = not report_errors and failures == 0 and sys_fail == 0 and lint_fail == 0

    def _test_detail(n_passed: int, n_failed: int, n_skipped: int, n_total: int) -> str:
        if not n_total:
            return "no results"
        parts = [f"{n_passed} passed"]
        if n_failed:
            parts.append(f"{n_failed} failed")
        if n_skipped:
            parts.append(f"{n_skipped} skipped")
        return ", ".join(parts)

    lint_file_word = "file" if lint_files == 1 else "files"
    if lint_fail:
        lint_detail = f"{lint_fail} error(s) in {lint_files} {lint_file_word}"
    elif lint_files:
        lint_detail = f"{lint_files} {lint_file_word} clean"
    else:
        lint_detail = "no results"

    # Coverage result is a comparison against the baseline (❌ only on a decrease);
    # without a baseline there is nothing to judge against, so the result is "—".
    if not cov_valid:
        cov_result = "—"
        cov_detail = "no data"
    else:
        cov_rate = cov_covered / cov_valid
        cov_detail = f"{cov_rate * 100:.1f}% ({cov_covered}/{cov_valid} lines)"
        if baseline_cov_rate is None:
            cov_result = "—"
        else:
            # Compare at the displayed precision (0.1pp) so a hairline float
            # difference doesn't flag a regression the reader can't see.
            delta = round(cov_rate * 1000) - round(baseline_cov_rate * 1000)
            cov_result = "❌" if delta < 0 else "✅"
            if delta:
                arrow = "↓" if delta < 0 else "↑"
                cov_detail += f" {arrow} {abs(delta) / 10:.1f}%"

    lines = [
        f"### {title} — {'✅ PASSED' if overall_pass else '❌ FAILED'}",
        "",
        "| Section | Result | Details |",
        "| --- | --- | --- |",
        f"| Unit tests | {'❌' if failures else '✅' if total else '—'} | {_test_detail(passed, failures, skipped, total)} |",
        f"| System tests | {'❌' if sys_fail else '✅' if sys_total else '—'} | {_test_detail(sys_passed, sys_fail, sys_skipped, sys_total)} |",
        f"| Lint | {'❌' if lint_fail else '✅' if lint_files else '—'} | {lint_detail} |",
        f"| Coverage | {cov_result} | {cov_detail} |",
    ]

    def _failing_cases(suite_list: list[TestSuite]) -> list[str]:
        items = []
        for suite in sorted(suite_list, key=lambda s: (s.package, s.name)):
            for tc in suite.cases:
                if tc.status not in ("failed", "error"):
                    continue
                label = f"{tc.classname}::{tc.name}" if tc.classname else tc.name
                msg_lines = (tc.message or tc.details or "").strip().splitlines()
                first = msg_lines[0][:200] if msg_lines else ""
                items.append(f"- `{label}` ({suite.package})" + (f" — {first}" if first else ""))
        return items

    def _details_block(summary: str, items: list[str]) -> list[str]:
        if not items:
            return []
        block = ["", f"<details><summary>{summary}</summary>", ""]
        block.extend(items[:max_items])
        if len(items) > max_items:
            block.append(f"- …and {len(items) - max_items} more — see the full report artifact")
        block.extend(["", "</details>"])
        return block

    lint_items = [
        f"- `{lf.name}` — {tool.name}: {len(lf.details.splitlines()) or 1} error(s)"
        for pkg in lint_packages
        for tool in pkg.tools
        for lf in tool.files
        if lf.status == "failed"
    ]

    lines.extend(_details_block(f"Unit test failures ({failures})", _failing_cases(suites)))
    lines.extend(_details_block(f"System test failures ({sys_fail})", _failing_cases(system_suites)))
    lines.extend(_details_block(f"Lint failures ({lint_fail})", lint_items))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Portable report JSON
# ---------------------------------------------------------------------------


def _save_report_data(
    json_path: Path,
    suites: list[TestSuite],
    system_suites: list[TestSuite],
    lint_packages: list[LintPackage],
    cov_packages: list[CoveragePackage],
) -> None:
    # Strip machine-local HTML paths from coverage data — they are absolute paths
    # into the build tree that won't resolve on another machine. Stats are preserved;
    # links are regenerated at render time when the build artifacts are present.
    def _portable_cov_pkg(pkg: CoveragePackage) -> dict:
        d = dataclasses.asdict(pkg)
        d["html_dir"] = ""
        for f in d["files"]:
            f["html_path"] = ""
        return d

    data = {
        "suites": [dataclasses.asdict(s) for s in suites],
        "system_suites": [dataclasses.asdict(s) for s in system_suites],
        "lint_packages": [dataclasses.asdict(p) for p in lint_packages],
        "cov_packages": [_portable_cov_pkg(p) for p in cov_packages],
    }
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_report_data(
    json_path: Path,
) -> tuple[list[TestSuite], list[TestSuite], list[LintPackage], list[CoveragePackage]]:
    if not json_path.exists():
        return [], [], [], []
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: could not load existing report data from {json_path}: {e}", file=sys.stderr)
        return [], [], [], []

    def load_suites(items: list[dict]) -> list[TestSuite]:
        result = []
        for d in items:
            cases = [TestCase(**c) for c in d.get("cases", [])]
            result.append(TestSuite(**{k: v for k, v in d.items() if k != "cases"}, cases=cases))
        return result

    def load_lint_packages(items: list[dict]) -> list[LintPackage]:
        result = []
        for p in items:
            tools = [
                LintTool(name=t["name"], files=[LintFile(**f) for f in t.get("files", [])]) for t in p.get("tools", [])
            ]
            result.append(LintPackage(package=p["package"], tools=tools))
        return result

    def load_cov_packages(items: list[dict]) -> list[CoveragePackage]:
        result = []
        for p in items:
            files = [CoverageFile(**f) for f in p.get("files", [])]
            result.append(CoveragePackage(**{k: v for k, v in p.items() if k != "files"}, files=files))
        return result

    return (
        load_suites(data.get("suites", [])),
        load_suites(data.get("system_suites", [])),
        load_lint_packages(data.get("lint_packages", [])),
        load_cov_packages(data.get("cov_packages", [])),
    )
