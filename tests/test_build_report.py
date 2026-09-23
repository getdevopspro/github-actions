"""Verify artifact selection, report aggregation, and failure handling offline."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest


REPO = Path(__file__).resolve().parents[1]
ACTION = REPO / "build-report"
sys.path.insert(0, str(ACTION))
import collect


def action_outputs(path):
    values = {}
    lines = iter(path.read_text().splitlines())
    for line in lines:
        if "<<" in line:
            key, marker = line.split("<<", 1)
            parts = []
            for part in lines:
                if part == marker:
                    break
                parts.append(part)
            values[key] = "\n".join(parts)
        else:
            key, value = line.split("=", 1)
            values[key] = value
    return values


class SelectionTests(unittest.TestCase):
    def configure(self, **inputs):
        workflow = (REPO / ".github/workflows/build.yml").read_text()
        step = workflow.split("      - name: Prepare build report\n", 1)[1].split("      - name:", 1)[0]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                env=dict(os.environ, BUILD_INPUTS=json.dumps(inputs), GITHUB_OUTPUT=str(output)),
            )
            if result.returncode:
                raise ValueError(result.stderr)
            return action_outputs(output)

    @staticmethod
    def producer(prefix="post-test-unit", name="unit-results"):
        return {
            f"{prefix}-command": "run-check",
            f"{prefix}-artifact-name": name,
            f"{prefix}-artifact-path": "build/not-created-yet.xml",
        }

    def test_disabled_by_default_even_with_artifacts(self):
        self.assertEqual(self.configure(), {"artifacts": ""})
        self.assertEqual(self.configure(**self.producer()), {"artifacts": ""})
        self.assertEqual(
            self.configure(
                **{**self.producer(), "build-report-enabled": False, "build-report-artifacts": "unit-results"}
            ),
            {"artifacts": ""},
        )

    def test_enabled_selects_pre_and_post_reports_including_checks(self):
        result = self.configure(
            **{
                "build-report-enabled": True,
                **self.producer("pre-checks", "pre-results"),
                **self.producer("pre-lint", "lint-results"),
                **self.producer("post-test-unit", "unit-results"),
                **self.producer("post-checks", "post-results"),
                "post-test-command": "run-without-report",
            }
        )
        self.assertEqual(result, {"artifacts": "pre-results\nlint-results\nunit-results\npost-results"})

    def test_all_pre_and_post_artifact_types_are_selected(self):
        for phase in ("pre", "post"):
            for kind in ("checks", "lint", "test", "test-unit", "test-coverage", "test-integration", "test-e2e"):
                with self.subTest(phase=phase, kind=kind):
                    result = self.configure(**{"build-report-enabled": True, **self.producer(f"{phase}-{kind}")})
                    self.assertEqual(result, {"artifacts": "unit-results"})

    def test_partial_artifact_configuration_fails_for_every_pre_post_type(self):
        for phase in ("pre", "post"):
            for kind in ("checks", "lint", "test", "test-unit", "test-coverage", "test-integration", "test-e2e"):
                prefix = f"{phase}-{kind}"
                for missing in ("command", "artifact-name", "artifact-path"):
                    for enabled in (False, True):
                        inputs = self.producer(prefix)
                        inputs[f"{prefix}-{missing}"] = " \n "
                        with self.subTest(prefix=prefix, missing=missing, enabled=enabled):
                            with self.assertRaisesRegex(ValueError, f"requires {prefix}-{missing}"):
                                self.configure(**inputs, **{"build-report-enabled": enabled})

    def test_explicit_subset_is_deduplicated(self):
        result = self.configure(
            **{
                "build-report-enabled": True,
                "build-report-artifacts": "b\na\nb",
                **self.producer("pre-test", "a"),
                **self.producer("post-test", "b"),
                **self.producer("post-checks", "logs"),
            }
        )
        self.assertEqual(result, {"artifacts": "b\na"})

    def test_explicit_names_must_have_configured_producers(self):
        with self.assertRaisesRegex(ValueError, "must reference configured pre/post"):
            self.configure(**{"build-report-enabled": True, "build-report-artifacts": "typo", **self.producer()})

    def test_subset_does_not_hide_invalid_unselected_pre_post_configuration(self):
        with self.assertRaisesRegex(ValueError, "requires pre-lint-artifact-path"):
            self.configure(
                **{
                    "build-report-enabled": True,
                    "build-report-artifacts": "unit-results",
                    **self.producer(),
                    "pre-lint-command": "lint",
                    "pre-lint-artifact-name": "lint-results",
                }
            )

    def test_reporting_requires_at_least_one_artifact(self):
        with self.assertRaisesRegex(ValueError, "requires at least one pre/post artifact"):
            self.configure(**{"build-report-enabled": True, "post-test-command": "run-tests"})

    def test_duplicate_producers_cannot_overwrite_report_inputs(self):
        inputs = {**self.producer("pre-test"), **self.producer("post-test")}
        self.assertEqual(self.configure(**inputs), {"artifacts": ""})
        with self.assertRaisesRegex(ValueError, "must use distinct artifact names"):
            self.configure(**inputs, **{"build-report-enabled": True})

    def test_invalid_and_reserved_names_fail_early(self):
        for name in ("..", "../outside", "path/name", "path\\name", "bad:name", "a\nb"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "valid single artifact name"):
                self.configure(**self.producer(name=name))
        for name in ("build-report", "source-code"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "must not conflict"):
                self.configure(
                    **{
                        "build-report-enabled": True,
                        "source-artifact-name": "source-code",
                        **self.producer(name=name),
                    }
                )

    def test_validation_runs_before_checkout(self):
        workflow = (REPO / ".github/workflows/build.yml").read_text()
        self.assertLess(
            workflow.index("      - name: Prepare build report"), workflow.index("      - name: Checkout repository")
        )


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "output").mkdir()
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results"]))
        self.artifact = self.root / "input/unit-results"
        self.artifact.mkdir(parents=True)

    def write(self, name, content, directory=None):
        path = (directory or self.artifact) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def run_report(self):
        result = subprocess.run(
            [sys.executable, "-B", str(ACTION / "collect.py"), "generate", "--root", str(self.root)],
            capture_output=True,
            text=True,
            env=dict(os.environ, GITHUB_REPOSITORY="example/project"),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        check = subprocess.run(
            [sys.executable, "-B", str(ACTION / "collect.py"), "check", "--root", str(self.root)],
            capture_output=True,
            text=True,
        )
        return check, (self.root / "output/build_report.md").read_text()

    def test_pytest_and_gtest_reports_share_one_artifact(self):
        self.write(
            "build/unit-test-results.xml",
            '<testsuites><testsuite name="cpp" tests="2"><testcase name="a"/><testcase name="b"/></testsuite></testsuites>',
        )
        self.write(
            "build/launch-test-results.xml",
            '<testsuites><testsuite name="launch" tests="1"><testcase name="c"/></testsuite></testsuites>',
        )
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("3 passed", markdown)
        self.assertIn("| Lint | — | no results |", markdown)
        self.assertIn("project — Build Report", (self.root / "output/build_report.html").read_text())

    def test_assertions_fail_even_when_junit_totals_are_missing(self):
        self.write(
            "result.xml",
            '<testsuite name="suite"><testcase name="example"><failure message="a &lt; b">details</failure></testcase></testsuite>',
        )
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("1 failed", markdown)
        self.assertIn("a &lt; b", (self.root / "output/build_report.html").read_text())

    def test_existing_json_preserves_system_lint_and_coverage(self):
        data = {
            "suites": [],
            "system_suites": [
                {
                    "name": "system",
                    "package": "example",
                    "tests": 1,
                    "failures": 0,
                    "errors": 0,
                    "skipped": 0,
                    "time": 0.1,
                    "cases": [],
                }
            ],
            "lint_packages": [
                {
                    "package": "example",
                    "tools": [
                        {
                            "name": "ruff",
                            "files": [
                                {"name": "file.py", "status": "failed", "message": "lint error", "details": "example"}
                            ],
                        }
                    ],
                }
            ],
            "cov_packages": [
                {"package": "example", "line_rate": 0.8, "lines_covered": 8, "lines_valid": 10, "files": []}
            ],
        }
        self.write("report.json", json.dumps(data))
        baseline = self.root / "baseline"
        baseline.mkdir()
        self.write(
            "baseline.json",
            json.dumps(
                {
                    "cov_packages": [
                        {"package": "example", "line_rate": 0.9, "lines_covered": 9, "lines_valid": 10, "files": []}
                    ]
                }
            ),
            baseline,
        )
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("System tests | ✅ | 1 passed", markdown)
        self.assertIn("Lint | ❌", markdown)
        self.assertIn("80.0% (8/10 lines) ↓ 10.0%", markdown)

    def test_missing_or_invalid_reports_publish_failed_summary(self):
        for content in ("not XML", '{"suites": "invalid"}', None):
            with self.subTest(content=content):
                for path in self.artifact.iterdir():
                    path.unlink()
                if content:
                    self.write("bad.json" if content.startswith("{") else "bad.xml", content)
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 1)
                self.assertIn("Report input errors", markdown)
                self.assertIn("Build Report — ❌ FAILED", markdown)

    def test_one_missing_artifact_does_not_hide_available_results(self):
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results", "system-results"]))
        self.write("result.xml", '<testsuite name="suite" tests="1"><testcase name="example"/></testsuite>')
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("1 passed", markdown)
        self.assertIn("system-results: artifact is missing", markdown)

    def test_single_match_from_multiple_artifacts_is_flattened_by_downloader(self):
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results", "system-results"]))
        self.artifact.rmdir()
        self.write(
            "result.xml",
            '<testsuite name="suite" tests="1"><testcase name="example"/></testsuite>',
            self.root / "input",
        )
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("1 passed", markdown)
        self.assertIn("Report input errors", markdown)

    def test_same_suite_name_in_separate_reports_keeps_all_results(self):
        self.write(
            "a.xml", '<testsuite name="pytest"><testcase name="first"><error message="failed"/></testcase></testsuite>'
        )
        self.write("b.xml", '<testsuite name="pytest"><testcase name="second"/></testsuite>')
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("1 passed, 1 failed", markdown)

    def test_ruff_and_pyright_for_same_package_keep_both_tools(self):
        self.write(
            "ruff.json",
            json.dumps(
                [
                    {
                        "filename": "src/group/example/file.py",
                        "message": "ruff failure",
                        "code": "F401",
                        "location": {"row": 1, "column": 1},
                    }
                ]
            ),
        )
        self.write(
            "pyright.json",
            json.dumps(
                {
                    "generalDiagnostics": [
                        {
                            "file": "src/group/example/file.py",
                            "severity": "error",
                            "message": "pyright failure",
                            "range": {"start": {"line": 0, "character": 0}},
                        }
                    ]
                }
            ),
        )
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("2 error(s)", markdown)
        self.assertIn("ruff:", markdown)
        self.assertIn("pyright:", markdown)

    def test_download_failure_cannot_pass_with_valid_local_results(self):
        self.write("result.xml", '<testsuite name="suite" tests="1"><testcase name="example"/></testsuite>')
        from unittest.mock import patch

        with patch.dict(os.environ, REPORT_DOWNLOAD_OUTCOME="failure"):
            check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("Report artifact download failed", markdown)

    def test_absent_generated_report_fails(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(collect.check(self.root), 1)

    def test_tar_wrapped_reports_are_read(self):
        payload = b'<testsuite name="example" tests="1"><testcase name="test"/></testsuite>'
        with tarfile.open(self.artifact / "results.tar", "w") as archive:
            member = tarfile.TarInfo("build/results.xml")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("1 passed", markdown)

    def test_archive_traversal_and_links_are_rejected(self):
        for name, symlink in (("../escape.xml", False), ("/tmp/escape.xml", False), ("link.xml", True)):
            with self.subTest(name=name):
                with tarfile.open(self.artifact / "results.tar", "w") as archive:
                    member = tarfile.TarInfo(name)
                    if symlink:
                        member.type = tarfile.SYMTYPE
                        member.linkname = "/tmp/escape.xml"
                    archive.addfile(member)
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 1)
                self.assertIn("unsafe path or link", markdown)

    def test_cobertura_coverage_is_rendered(self):
        self.write("coverage.xml", '<coverage line-rate="0.75" lines-covered="3" lines-valid="4"/>')
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("75.0% (3/4 lines)", markdown)

    def test_invalid_optional_baseline_does_not_fail_current_results(self):
        self.write("result.xml", '<testsuite name="suite" tests="1"><testcase name="example"/></testsuite>')
        self.write("baseline.xml", "invalid", self.root / "baseline")
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("1 passed", markdown)


class PrepareTests(unittest.TestCase):
    def test_single_and_multiple_artifact_download_paths(self):
        for names in ("unit-results", "unit-results\nlint-results"):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / "outputs"
                result = subprocess.run(
                    [sys.executable, "-B", str(ACTION / "collect.py"), "prepare"],
                    env=dict(os.environ, REPORT_ARTIFACT_NAMES=names, RUNNER_TEMP=temp, GITHUB_OUTPUT=str(output)),
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                values = action_outputs(output)
                self.assertEqual(values["name"], names if "\n" not in names else "")
                self.assertEqual(values["pattern"], "{unit-results,lint-results}" if "\n" in names else "")
                self.assertTrue(Path(values["root"]).is_dir())

    def test_unsafe_or_empty_artifact_names_are_rejected(self):
        for name in ("", "..", "../bad", "dir/name", "dir\\name"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                collect.artifact_names(name)


if __name__ == "__main__":
    unittest.main()
