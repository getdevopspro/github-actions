"""Verify artifact selection, report aggregation, and failure handling offline."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
ACTION = REPO / "build" / "report" / "publish"
PREPARE = ACTION.parent / "prepare"
sys.path.insert(0, str(PREPARE))
from prepare import prepare_inputs
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
        # GitHub includes declared defaults in the inputs context.
        defaults = dict(
            re.findall(
                r"^      ((?:pre|post)-[\w-]+-name):\n(?:        .*\n)*?        default: '([^']*)'",
                workflow,
                re.MULTILINE,
            )
        )
        outputs = prepare_inputs({**defaults, **inputs})
        return {key: outputs[key] for key in ("artifacts", "artifact-sections")}

    @staticmethod
    def producer(prefix="post-test-unit", name="unit-results"):
        return {
            f"{prefix}-command": "run-check",
            f"{prefix}-artifact-name": name,
            f"{prefix}-artifact-path": "build/not-created-yet.xml",
        }

    def test_disabled_by_default_even_with_artifacts(self):
        self.assertEqual(self.configure(), {"artifacts": "", "artifact-sections": "{}"})
        self.assertEqual(self.configure(**self.producer()), {"artifacts": "", "artifact-sections": "{}"})
        self.assertEqual(
            self.configure(
                **{**self.producer(), "build-report-enabled": False, "build-report-artifacts": "unit-results"}
            ),
            {"artifacts": "", "artifact-sections": "{}"},
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
        self.assertEqual(result["artifacts"], "pre-results\nlint-results\nunit-results\npost-results")

    def test_all_pre_and_post_artifact_types_are_selected(self):
        labels = {
            "checks": "Checks",
            "lint": "Lint",
            "test": "Test",
            "test-unit": "Unit Test",
            "test-coverage": "Test Coverage",
            "test-integration": "Integration Test",
            "test-e2e": "E2E Test",
        }
        for phase in ("pre", "post"):
            for kind in ("checks", "lint", "test", "test-unit", "test-coverage", "test-integration", "test-e2e"):
                with self.subTest(phase=phase, kind=kind):
                    result = self.configure(**{"build-report-enabled": True, **self.producer(f"{phase}-{kind}")})
                    self.assertEqual(result["artifacts"], "unit-results")
                    self.assertEqual(
                        json.loads(result["artifact-sections"]),
                        {
                            "unit-results": {"id": f"{phase}-{kind}", "title": f"{labels[kind]} ({phase}-steps)"},
                        },
                    )

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
        self.assertEqual(result["artifacts"], "b\na")
        self.assertEqual(set(json.loads(result["artifact-sections"])), {"a", "b"})

    def test_custom_step_names_change_titles_without_changing_group_identity(self):
        for title in ("Contract tests", 'Acceptance | <tests> "quoted"', "Checks before deployment"):
            result = self.configure(
                **{
                    "build-report-enabled": True,
                    **self.producer("post-test-integration"),
                    "post-test-integration-name": title,
                    "pre-test-unit-command": "no-artifact",
                }
            )
            self.assertEqual(
                json.loads(result["artifact-sections"]),
                {
                    "unit-results": {"id": "post-test-integration", "title": title},
                },
            )

    def test_blank_selected_step_names_fail_in_prepare(self):
        with self.assertRaisesRegex(ValueError, "post-test-unit-name must be nonempty"):
            self.configure(
                **{
                    "build-report-enabled": True,
                    **self.producer(),
                    "post-test-unit-name": "  ",
                }
            )

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
        self.assertEqual(self.configure(**inputs), {"artifacts": "", "artifact-sections": "{}"})
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
            workflow.index("      - name: Prepare build inputs"), workflow.index("      - name: Checkout repository")
        )
        self.assertEqual(workflow.count("uses: $/build/report/prepare"), 1)

    def test_prepare_action_outputs_match_direct_preparation(self):
        inputs = {
            "build-report-enabled": True,
            **self.producer(),
            "post-test-unit-name": "Unit Tests",
            "post-test-unit-docker-login": True,
            "post-test-unit-artifact-retention-days": 30,
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            subprocess.run(
                [sys.executable, "-B", str(PREPARE / "prepare.py")],
                env=dict(os.environ, BUILD_INPUTS=json.dumps(inputs), GITHUB_OUTPUT=str(output)),
                check=True, capture_output=True, text=True,
            )
            self.assertEqual(action_outputs(output), prepare_inputs(inputs))

    def test_prepare_action_rejects_invalid_inputs_before_writing_outputs(self):
        for inputs in ([], {"pre-lint-artifact-name": "lint-results"}):
            with self.subTest(inputs=inputs), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "output"
                result = subprocess.run(
                    [sys.executable, "-B", str(PREPARE / "prepare.py")],
                    env=dict(os.environ, BUILD_INPUTS=json.dumps(inputs), GITHUB_OUTPUT=str(output)),
                    capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())

    def test_baseline_is_explicit_and_independent_of_report_enablement(self):
        # Coverage producers do not opt in, even with baseline options configured.
        result = self.configure(**{
            "build-report-enabled": True, **self.producer("post-test-coverage"),
            "baseline-artifact": "", "baseline-workflow": "",
        })
        self.assertEqual(result["artifacts"], "unit-results")
        for phase in ("pre", "post"):
            result = self.configure(**{
                "baseline-enabled": True, "baseline-artifact": "reference-results",
                f"{phase}-checks-command": "compare-results",
            })
            self.assertEqual(result, {"artifacts": "", "artifact-sections": "{}"})

    def test_enabled_baseline_requires_artifact_workflow_and_command(self):
        valid = {"baseline-enabled": True, "baseline-artifact": "reference-results", "pre-checks-command": "compare"}
        for change, message in [
            ({"baseline-artifact": ""}, "valid baseline-artifact"),
            ({"baseline-artifact": "../results"}, "valid baseline-artifact"),
            ({"baseline-workflow": " "}, "requires baseline-workflow"),
            ({"pre-checks-command": " "}, "at least one pre/post command"),
        ]:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                self.configure(**{**valid, **change})

    def test_baseline_bundle_cannot_be_overwritten_by_pre_post_artifacts(self):
        for report_enabled in (False, True):
            with self.subTest(report_enabled=report_enabled), self.assertRaisesRegex(ValueError, "baseline bundle"):
                self.configure(**{
                    "baseline-enabled": True, "baseline-artifact": "reference-results",
                    "build-report-enabled": report_enabled, "source-artifact-name": "custom-source",
                    **self.producer(name="build-baseline-custom-source"),
                })


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "output").mkdir()
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results"]))
        self.artifact = self.root / "input/unit-results"
        self.artifact.mkdir(parents=True)
        self.section_defaults(**{"unit-results": {"id": "checks", "title": "Checks"}})

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
        self.generated = result
        check = subprocess.run(
            [sys.executable, "-B", str(ACTION / "collect.py"), "check", "--root", str(self.root)],
            capture_output=True,
            text=True,
        )
        return check, (self.root / "output/build_report.md").read_text()

    def section_defaults(self, **groups):
        (self.root / "artifact-sections.json").write_text(json.dumps(groups))

    def test_workflow_sections_show_coverage_separately(self):
        prepared = SelectionTests().configure(
            **{
                "build-report-enabled": True,
                **SelectionTests.producer("pre-test-unit", "unit-results"),
                "pre-test-unit-name": "Fast tests",
                **SelectionTests.producer("post-test-integration", "contract-results"),
                "post-test-integration-name": "Contract tests",
                **SelectionTests.producer("post-test-e2e", "acceptance-results"),
                "post-test-e2e-name": "Acceptance tests",
            }
        )
        (self.root / "artifacts.json").write_text(json.dumps(prepared["artifacts"].splitlines()))
        (self.root / "artifact-sections.json").write_text(prepared["artifact-sections"])
        for name in prepared["artifacts"].splitlines():
            self.write(
                "tests.xml",
                '<testsuite name="same"><testcase name="test" classname="Example"/></testsuite>',
                self.root / "input" / name,
            )
        self.write("coverage.xml", '<coverage line-rate="0.5" lines-covered="1" lines-valid="2"/>')
        self.write("lint.json", "[]")
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("| Fast tests | ✅ | 1 passed |", markdown)
        self.assertIn("| Coverage | 📊 | 50.0% (1/2 lines) |", markdown)
        for title in ("Contract tests", "Acceptance tests"):
            self.assertIn(f"| {title} | ✅ | 1 passed |", markdown)
        self.assertIn("| Lint | ✅ | 0 issues |", markdown)
        sections = json.loads((self.root / "output/build_report.json").read_text())["report_sections"]
        self.assertEqual(sections[0]["id"], "pre-test-unit")
        self.assertEqual(sections[0]["kinds"], ["coverage", "lint", "tests"])
        collect.validate_report({"report_sections": sections})
        page = (self.root / "output/build_report.html").read_text()
        self.assertIn('class="stat-group-label">Coverage</div>', page)
        ids = re.findall(r'\bid="([^"]+)"', page)
        self.assertEqual(len(ids), len(set(ids)))
        for target in re.findall(r"getElementById\('(section-[^']+)'\)\.scrollIntoView", page):
            self.assertIn(target, ids)
        self.assertNotIn("::warning::", self.generated.stdout)

    def test_empty_suites_do_not_warn_when_the_artifact_has_tests(self):
        for native in (False, True):
            with self.subTest(native=native):
                for path in self.artifact.iterdir():
                    path.unlink()
                if native:
                    self.write("empty.xml", '<testsuite name="empty" tests="0"/>')
                    self.write("tests.xml", '<testsuite name="tests" tests="2"/>')
                else:
                    self.write(
                        "report.json",
                        json.dumps({"suites": [
                            {"name": "empty", "package": "empty", "tests": 0},
                            {"name": "tests", "package": "example", "tests": 2},
                        ]}),
                    )
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 0)
                self.assertIn("2 passed", markdown)
                self.assertNotIn("::warning::", self.generated.stdout)
                self.assertNotIn("Report warnings", markdown)

    def test_separate_coverage_sections_keep_multiple_producers_distinct(self):
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results", "post-results"]))
        self.section_defaults(**{
            "unit-results": {"id": "pre-test", "title": "Before"},
            "post-results": {"id": "post-test", "title": "After"},
        })
        for name in ("unit-results", "post-results"):
            directory = self.root / "input" / name
            self.write("tests.xml", '<testsuite name="tests" tests="1"/>', directory)
            self.write("coverage.xml", '<coverage line-rate="0.5" lines-covered="1" lines-valid="2"/>', directory)
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        for title in ("Before", "After"):
            self.assertIn(f"| {title} | ✅ | 1 passed |", markdown)
            self.assertIn(f"| {title} — Coverage | 📊 | 50.0% (1/2 lines) |", markdown)
        self.assertNotIn("::warning::", self.generated.stdout)

    def test_legacy_json_and_system_xml_use_the_workflow_name(self):
        self.section_defaults(**{"unit-results": {"id": "post-test", "title": "System Test (post-steps)"}})
        self.write(
            "report.json",
            json.dumps(
                {
                    "suites": [{"name": "unit", "package": "example", "tests": 1}],
                    "system_suites": [{"name": "system", "package": "example", "tests": 1}],
                    "lint_packages": [],
                    "cov_packages": [],
                }
            ),
        )
        self.write("system_tests.xml", '<testsuite name="legacy" tests="1"/>')
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("| System Test (post-steps) | ✅ | 3 passed |", markdown)
        self.assertNotIn("| Unit tests |", markdown)
        self.assertNotIn("| System tests |", markdown)

    def test_ros_style_json_keeps_unit_system_and_lint_producer_names(self):
        inputs = {"build-report-enabled": True}
        reports = {
            "post-test-unit": (
                "Unit Test (post-steps)",
                {
                    "suites": [{"name": "unit", "package": "example", "tests": 2}],
                    "cov_packages": [{"package": "example", "line_rate": 0.5, "lines_covered": 1, "lines_valid": 2}],
                },
            ),
            "post-test": (
                "System Test (post-steps)",
                {"system_suites": [{"name": "system", "package": "example", "tests": 3}]},
            ),
            "post-lint": ("Python Lint (post-steps)", {"lint_packages": [{"package": "example", "tools": []}]}),
        }
        for prefix, (title, values) in reports.items():
            inputs.update(SelectionTests.producer(prefix, prefix))
            inputs[f"{prefix}-name"] = title
            self.write(
                "results.json",
                json.dumps({**dict.fromkeys(collect.REPORT_KEYS, []), **values}),
                self.root / "input" / prefix,
            )
        prepared = SelectionTests().configure(**inputs)
        (self.root / "artifacts.json").write_text(json.dumps(prepared["artifacts"].splitlines()))
        (self.root / "artifact-sections.json").write_text(prepared["artifact-sections"])
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("| Unit Test (post-steps) | ✅ | 2 passed |", markdown)
        self.assertIn("| Coverage | 📊 | 50.0% (1/2 lines) |", markdown)
        self.assertIn("| System Test (post-steps) | ✅ | 3 passed |", markdown)
        self.assertIn("| Python Lint (post-steps) | ✅ | 0 issues |", markdown)
        self.assertNotIn("::warning::", self.generated.stdout)

    def test_all_pre_post_names_apply_to_results_without_inferring_type_from_name(self):
        for phase in ("pre", "post"):
            for kind in ("checks", "lint", "test", "test-unit", "test-coverage", "test-integration", "test-e2e"):
                prefix = f"{phase}-{kind}"
                with self.subTest(prefix=prefix):
                    prepared = SelectionTests().configure(
                        **{
                            "build-report-enabled": True,
                            **SelectionTests.producer(prefix),
                            f"{prefix}-name": "Quality gate",
                        }
                    )
                    (self.root / "artifact-sections.json").write_text(prepared["artifact-sections"])
                    self.write("lint.json", "[]")
                    check, markdown = self.run_report()
                    self.assertEqual(check.returncode, 0)
                    self.assertIn("| Quality gate | ✅ | 0 issues |", markdown)
                    self.assertNotIn("no tests collected", markdown)
                    self.assertNotIn("::warning::", self.generated.stdout)

    def test_named_group_failures_and_titles_are_preserved_safely(self):
        self.section_defaults(**{"unit-results": {"id": "post-test", "title": 'Contract | <script> "tests"'}})
        self.write(
            "tests.xml",
            '<testsuite name="suite"><testcase name="broken" classname="Example"><failure message="failed"/></testcase></testsuite>',
        )
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("Build Report — ❌ FAILED", markdown)
        self.assertIn("| Contract &#124; &lt;script&gt; &quot;tests&quot; | ❌ | 0 passed, 1 failed |", markdown)
        self.assertIn("Example::broken", markdown)
        page = (self.root / "output/build_report.html").read_text()
        self.assertIn("Contract | &lt;script&gt; &quot;tests&quot;", page)
        self.assertIn("toggleClass('group-0-0-0')", page)
        self.assertIn('id="cg-group-0-0-0-cases"', page)

    def test_empty_native_group_warns_and_missing_artifact_never_creates_a_group(self):
        self.section_defaults(**{"unit-results": {"id": "pre-test", "title": "Smoke tests"}})
        xml = self.write("empty.xml", "<testsuites/>")
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("| Smoke tests | ⚠️ | no tests collected |", markdown)
        self.assertIn("::warning::", self.generated.stdout)
        xml.unlink()
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertNotIn("| Smoke tests |", markdown)

    def test_named_group_html_controls_expand_failures_and_toggle_details(self):
        self.section_defaults(**{"unit-results": {"id": "smoke-cases", "title": "Smoke tests"}})
        self.write(
            "tests.xml",
            '<testsuite name="suite"><testcase name="failed" classname="Example"><failure/></testcase></testsuite>',
        )
        self.run_report()
        page = (self.root / "output/build_report.html").read_text()
        # Execute the generated controls with the actual element IDs and one failing suite.
        script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const page = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const nodes = new Map([...page.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => [id, {
  id, style: {display: 'none'}, classes: new Set(),
  classList: {
    add(name) { nodes.get(id).classes.add(name); },
    toggle(name, enabled) {
      if (enabled) nodes.get(id).classes.add(name); else nodes.get(id).classes.delete(name);
    },
  },
}]));
const parent = nodes.get('suite-group-0-0-cases');
const onclick = page.match(/<tr class="class-header has-fail" onclick="([^"]+)"/)[1];
const row = {getAttribute: () => onclick, closest: () => parent};
const context = {document: {
  getElementById: id => nodes.get(id),
  querySelectorAll: selector => selector === '.class-header.has-fail' ? [row] : [],
}};
vm.createContext(context);
vm.runInContext(page.match(/<script>([\s\S]*?)<\/script>/)[1], context);
assert.equal(parent.style.display, '');
assert(nodes.get('toggle-group-0-0').classes.has('open'));
assert.equal(nodes.get('cg-group-0-0-0-cases').style.display, '');
context.toggleSuite('group-0-0');
assert.equal(parent.style.display, 'none');
context.toggleClass('group-0-0-0');
assert.equal(nodes.get('cg-group-0-0-0-cases').style.display, 'none');
context.toggleSection('group-0');
assert.equal(nodes.get('section-group-0-body').style.display, 'block');
"""
        result = subprocess.run(["node", "-e", script], input=json.dumps(page), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_explicit_title_overrides_the_whole_artifact_and_conflicts_preserve_results(self):
        self.write("native.xml", '<testsuite name="native" tests="1"/>')
        for title in ("Contracts", "Different title"):
            with self.subTest(title=title):
                for name, override in (("a", "Contracts"), ("b", title)):
                    self.write(
                        f"{name}.json",
                        json.dumps(
                            {"section_title": override, "suites": [{"name": name, "package": "example", "tests": 1}]}
                        ),
                    )
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 0 if title == "Contracts" else 1)
                self.assertIn("| Contracts | ✅ | 3 passed |", markdown)
                self.assertNotIn("| Checks |", markdown)
                section = json.loads((self.root / "output/build_report.json").read_text())["report_sections"][0]
                self.assertEqual(section["id"], "checks")
                if title != "Contracts":
                    self.assertIn("conflicting section_title overrides", markdown)

    def test_title_override_applies_to_lint_and_coverage_without_changing_fields(self):
        self.write(
            "report.json", json.dumps({"section_title": "Static analysis", "lint_packages": [], "sections": ["lint"]})
        )
        self.write("coverage.xml", '<coverage line-rate="0.5" lines-covered="1" lines-valid="2"/>')
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("| Static analysis | ✅ | 0 issues |", markdown)
        self.assertIn("| Coverage | 📊 | 50.0% (1/2 lines) |", markdown)
        self.assertNotIn("no tests collected", markdown)

    def test_direct_action_defaults_to_artifact_name(self):
        (self.root / "artifact-sections.json").unlink()
        self.write("results.xml", '<testsuite name="suite" tests="1"/>')
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("| unit-results | ✅ | 1 passed |", markdown)

    def test_invalid_title_metadata_does_not_hide_other_results(self):
        self.write("good.xml", '<testsuite name="good" tests="1"/>')
        for title in (None, {}, [], 1, " ", "\n"):
            with self.subTest(title=title):
                self.write("bad.json", json.dumps({"section_title": title, "suites": []}))
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 1)
                self.assertIn("Report input errors", markdown)
                self.assertIn("1 passed", markdown)

    def test_native_json_title_overrides_are_validated(self):
        self.write("good.xml", '<testsuite name="good" tests="1"/>')
        for title in ("Analysis", None, {}):
            with self.subTest(title=title):
                self.write("pyright.json", json.dumps({"generalDiagnostics": [], "section_title": title}))
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 0 if title == "Analysis" else 1)
                self.assertIn("1 passed", markdown)
                if title == "Analysis":
                    self.assertIn("| Analysis | ✅ | 1 passed |", markdown)
                    self.assertIn("| Lint | ✅ | 0 issues |", markdown)
                else:
                    self.assertIn("section_title must be string", markdown)

    def test_same_title_does_not_merge_different_step_ids(self):
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results", "post-results"]))
        self.section_defaults(
            **{
                "unit-results": {"id": "pre-test", "title": "Smoke tests"},
                "post-results": {"id": "post-test", "title": "Smoke tests"},
            }
        )
        for name in ("unit-results", "post-results"):
            self.write("tests.xml", '<testsuite name="smoke" tests="1"/>', self.root / "input" / name)
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertEqual(markdown.count("| Smoke tests | ✅ | 1 passed |"), 2)

    def test_matching_producer_ids_merge_artifacts_and_preserve_explicit_title(self):
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results", "lint-results"]))
        self.section_defaults(
            **dict.fromkeys(("unit-results", "lint-results"), {"id": "pre-checks", "title": "Quality checks"})
        )
        self.write(
            "tests.json",
            json.dumps(
                {"section_title": "Project checks", "suites": [{"name": "tests", "package": "example", "tests": 1}]}
            ),
        )
        self.write("lint.json", "[]", self.root / "input/lint-results")
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("| Project checks | ✅ | 1 passed |", markdown)
        self.assertIn("| Lint | ✅ | 0 issues |", markdown)
        self.assertEqual(markdown.count("| Project checks |"), 1)

    def test_mixed_sections_have_unique_working_html_controls(self):
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results", "post-results"]))
        self.section_defaults(
            **{
                "unit-results": {"id": "checks", "title": "Before"},
                "post-results": {"id": "checks-tests", "title": "After"},
            }
        )
        for name in ("unit-results", "post-results"):
            directory = self.root / "input" / name
            self.write(
                "tests.xml", '<testsuite name="same"><testcase name="test" classname="Example"/></testsuite>', directory
            )
            self.write(
                "lint.json",
                json.dumps(
                    {
                        "lint_packages": [
                            {
                                "package": "example",
                                "tools": [{"name": "style", "files": [{"name": "a.py", "status": "failed"}]}],
                            }
                        ]
                    }
                ),
                directory,
            )
            self.write("coverage.xml", '<coverage line-rate="0.5" lines-covered="1" lines-valid="2"/>', directory)
        check, _ = self.run_report()
        self.assertEqual(check.returncode, 1)
        page = (self.root / "output/build_report.html").read_text()
        script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const page = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const ids = [...page.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => id);
assert.equal(new Set(ids).size, ids.length);
const nodes = new Map(ids.map(id => [id, {
  id, style: {display: 'none'}, scrollIntoView() {},
  classList: {add() {}, toggle() {}},
}]));
const tools = [...page.matchAll(/class="class-header lint-tool-header has-fail" onclick="toggleLintTool\('([^']+)'\)"/g)]
  .map(([, id]) => id);
assert.equal(tools.length, 2);
const packageId = id => `lp-${id.slice(3).replace(/-\d+$/, '')}-tools`;
const rows = tools.map(id => ({
  getAttribute: () => `toggleLintTool('${id}')`,
  closest: () => nodes.get(packageId(id)),
}));
const context = {document: {
  getElementById(id) { assert(nodes.has(id), `missing element ${id}`); return nodes.get(id); },
  querySelectorAll: selector => selector === '.lint-tool-header.has-fail' ? rows : [],
}};
vm.createContext(context);
vm.runInContext(page.match(/<script>([\s\S]*?)<\/script>/)[1], context);
for (const id of tools) {
  assert.equal(nodes.get(packageId(id)).style.display, '');
  assert.equal(nodes.get(`${id}-files`).style.display, '');
}
for (const [, handler] of page.matchAll(/\bonclick="([^"]+)"/g)) vm.runInContext(handler, context);
"""
        result = subprocess.run(["node", "-e", script], input=json.dumps(page), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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
        self.assertIn("| Checks | ✅ | 3 passed |", markdown)
        page = (self.root / "output/build_report.html").read_text()
        self.assertIn("project — Build Report", page)
        for absent in ("Unit tests", "System tests", "Lint", "Coverage"):
            self.assertNotIn(f"| {absent} |", markdown)
            self.assertNotIn(f'class="stat-group-label">{absent.title()}<', page)
        for absent in ("system", "lint", "coverage"):
            self.assertNotIn(f"getElementById('section-{absent}')", page)
        self.assertNotIn("::warning::", self.generated.stdout)

    def test_clean_lint_reports_are_present_without_invented_file_counts(self):
        for content in (
            [],
            {"generalDiagnostics": []},
            {"lint_packages": []},
            {"sections": ["lint"], **dict.fromkeys(collect.REPORT_KEYS, [])},
        ):
            with self.subTest(content=content):
                self.write("lint.json", json.dumps(content))
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 0, check.stderr)
                self.assertIn("| Checks | ✅ | 0 issues |", markdown)
                page = (self.root / "output/build_report.html").read_text()
                self.assertIn('id="section-group-0"', page)
                self.assertNotIn('<div class="lbl">Files</div>', page)
                self.assertNotIn("| Unit tests |", markdown)
                self.assertNotIn("::warning::", self.generated.stdout)

    def test_legacy_empty_sections_are_omitted_without_hiding_populated_sections(self):
        self.write(
            "report.json",
            json.dumps(
                {
                    **dict.fromkeys(collect.REPORT_KEYS, []),
                    "suites": [{"name": "suite", "package": "example", "tests": 1}],
                }
            ),
        )
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("| Checks | ✅ | 1 passed |", markdown)
        for absent in ("System tests", "Lint", "Coverage"):
            self.assertNotIn(f"| {absent} |", markdown)

    def test_generic_json_and_native_results_share_the_producer_section(self):
        data = {"suites": [{"name": "suite", "package": "example", "tests": 1}]}
        for metadata in ({"sections": ["tests"]}, {}):
            with self.subTest(metadata=metadata):
                self.write("report.json", json.dumps({**data, **metadata}))
                if not metadata:
                    self.write("native.xml", '<testsuite name="native" tests="1"/>')
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 0)
                self.assertIn("| Checks | ✅", markdown)
                self.assertNotIn("| Unit tests |", markdown)

    def test_legacy_system_xml_uses_the_producer_and_warns_for_zero_tests(self):
        self.write("system_tests.xml", '<testsuite name="empty"/>')
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("| Checks | ⚠️ | no tests collected |", markdown)
        self.assertNotIn("| Tests |", markdown)
        self.assertIn("NO TESTS", (self.root / "output/build_report.html").read_text())

    def test_zero_tests_and_ambiguous_empty_json_warn_without_a_false_pass(self):
        for name, content in (
            ("report.xml", '<testsuite name="empty" tests="0"/>'),
            ("report.xml", "<testsuites/>"),
            ("report.json", json.dumps(dict.fromkeys(collect.REPORT_KEYS, []))),
        ):
            with self.subTest(content=content):
                for path in self.artifact.iterdir():
                    path.unlink()
                self.write(name, content)
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 0)
                self.assertIn("::warning::", self.generated.stdout)
                self.assertIn("Report warnings", markdown)
                self.assertNotIn("✅ PASSED", markdown)
                self.assertNotIn(">PASS<", (self.root / "output/build_report.html").read_text())
                if name.endswith("xml"):
                    self.assertIn("| Checks | ⚠️ | no tests collected |", markdown)

    def test_invalid_values_cannot_hide_failures(self):
        suite = {"name": "example", "package": "example"}
        for value in (
            {"suites": [{**suite, "tests": -1}]},
            {"suites": [{**suite, "failures": -1}]},
            {"suites": [{**suite, "tests": True}]},
            {"suites": [{**suite, "time": float("nan")}]},
            {"suites": [{**suite, "cases": [{"name": "a", "classname": "", "time": 0, "status": "typo"}]}]},
            {"suites": [{"name": "missing package"}]},
            {
                "lint_packages": [
                    {"package": "example", "tools": [{"name": "lint", "files": [{"name": "a", "status": "error"}]}]}
                ]
            },
            {"suites": [], "sections": ["typo"]},
            {"suites": [], "unknown": "field"},
            {"cov_packages": [{"package": "example", "line_rate": 1.1, "lines_covered": 11, "lines_valid": 10}]},
        ):
            with self.subTest(value=value):
                self.write("report.json", json.dumps(value))
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 1)
                self.assertIn("Report input errors", markdown)

    def test_native_numeric_errors_fail_after_publishing_available_results(self):
        self.write("good.xml", '<testsuite name="good" tests="1"/>')
        for content in (
            '<testsuite name="bad" failures="-1"/>',
            '<testsuite name="bad" time="NaN"/>',
            '<coverage line-rate="0.5" lines-covered="3" lines-valid="2"/>',
        ):
            with self.subTest(content=content):
                self.write("bad.xml", content)
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 1)
                self.assertIn("1 passed", markdown)
                self.assertIn("Report input errors", markdown)

    def test_section_metadata_cannot_hide_failures(self):
        self.write(
            "report.json",
            json.dumps(
                {
                    "sections": ["lint"],
                    "lint_packages": [],
                    "suites": [{"name": "suite", "package": "example", "tests": 1, "failures": 1}],
                }
            ),
        )
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("| Checks | ❌", markdown)
        self.assertIn("| Lint | ✅ | 0 issues |", markdown)

    def test_warning_messages_cannot_inject_workflow_commands(self):
        self.write("empty%\n::error::injected.xml", '<testsuite name="empty"/>')
        check, _ = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("%25%0A::error::injected.xml", self.generated.stdout)
        self.assertNotIn("\n::error::", self.generated.stdout)

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
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("| Checks | ✅ | 1 passed |", markdown)
        self.assertIn("| Lint | ❌ | 1 failed of 1 check |", markdown)
        self.assertIn("80.0% (8/10 lines)", markdown)

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
        self.assertIn("| Checks | ✅ | 1 passed |", markdown)
        self.assertNotIn("Unattributed results", markdown)

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
        self.assertIn("2 errors, 0 warnings, 0 information", markdown)
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
        self.section_defaults(**{"unit-results": {"id": "post-test", "title": "Archived tests"}})
        payload = b'<testsuite name="example" tests="1"><testcase name="test"/></testsuite>'
        with tarfile.open(self.artifact / "results.tar", "w") as archive:
            member = tarfile.TarInfo("build/results.xml")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("1 passed", markdown)
        self.assertIn("| Archived tests | ✅", markdown)

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
        self.assertNotIn("| Lint |", markdown)
        self.assertNotIn("| Unit tests |", markdown)

    def test_coverage_without_executable_lines_warns(self):
        self.write("coverage.xml", '<coverage line-rate="0" lines-covered="0" lines-valid="0"/>')
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("no executable lines", markdown)
        self.assertIn("::warning::", self.generated.stdout)

    @staticmethod
    def coverage_result(delta=-50, status="exact"):
        return {
            "cov_packages": [{"package": "example", "line_rate": 0.5, "lines_covered": 1, "lines_valid": 2}],
            "coverage_comparison": {
                "status": status, "delta_pp": delta,
                "baseline": {"sha": "a" * 40, "requested_sha": "b" * 40,
                             "run_url": "https://example.test/actions/runs/42", "line_rate": 1,
                             "created_at": "2026-01-01T00:00:00Z"},
            },
        }

    def test_supplied_comparison_is_rendered_without_recalculating_or_failing(self):
        # The producer owns comparison scope and arithmetic, even if it differs from total coverage.
        data = self.coverage_result(delta=-12.3)
        data["suites"] = [{"name": "unit", "package": "example", "tests": 1}]
        self.write("result.json", json.dumps(data))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        for report in (markdown, (self.root / "output/build_report.html").read_text()):
            self.assertIn("↓ −12.3 pp", report)
            self.assertEqual(report.count("↓ −12.3 pp"), 1)
            self.assertNotIn("↓ −50.0 pp", report)
            self.assertIn("https://example.test/actions/runs/42", report)
            self.assertIn("aaaaaaa", report)
        self.assertNotIn("::warning::", self.generated.stdout)
        saved = (self.root / "output/build_report.json").read_text()
        collect.validate_report(json.loads(saved))
        self.write("result.json", saved)
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("↓ −12.3 pp", markdown)

    def test_approximate_comparison_is_labelled_and_unchanged_coverage_is_visible(self):
        self.write("result.json", json.dumps(self.coverage_result(delta=0, status="approximate")))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        for report in (markdown, (self.root / "output/build_report.html").read_text()):
            self.assertIn("0.0 pp", report)
            self.assertIn("Approximate comparison", report)
        self.assertIn("::notice::", self.generated.stdout)
        self.assertNotIn("::warning::", self.generated.stdout)

    def test_parent_baseline_links_both_commits_without_repeated_coverage_text(self):
        data = self.coverage_result(delta=0, status="approximate")
        baseline = data["coverage_comparison"]["baseline"]
        baseline.update(distance=1, run_url="https://github.example.test/example/project/actions/runs/42")
        self.write("result.json", json.dumps(data))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("| Checks | 📊 | 50.0% (1/2 lines) · baseline 100.0% · → 0.0 pp (unchanged) |", markdown)
        self.assertIn("parent of the requested baseline", markdown)
        self.assertIn("[aaaaaaa](https://github.example.test/example/project/commit/" + "a" * 40 + ")", markdown)
        self.assertIn("[bbbbbbb](https://github.example.test/example/project/commit/" + "b" * 40 + ")", markdown)
        self.assertIn("[CI run](https://github.example.test/example/project/actions/runs/42)", markdown)
        self.assertNotIn("<p>", markdown)
        self.assertNotIn("Coverage change:", markdown)
        self.assertNotIn(baseline["created_at"], markdown)
        page = (self.root / "output/build_report.html").read_text()
        self.assertIn('href="https://github.example.test/example/project/commit/' + "a" * 40 + '"', page)
        self.assertIn('href="https://github.example.test/example/project/commit/' + "b" * 40 + '"', page)
        self.assertIn("2026-01-01 00:00 UTC", page)
        self.assertIn("parent", self.generated.stdout)

    def test_parent_metadata_is_optional_and_distance_is_validated(self):
        for distance in (None, 2):
            data = self.coverage_result(status="approximate")
            if distance is not None:
                data["coverage_comparison"]["baseline"]["distance"] = distance
            self.write("result.json", json.dumps(data))
            check, markdown = self.run_report()
            self.assertEqual(check.returncode, 0)
            self.assertIn("earlier ancestor", markdown)
        for distance in (-1, 1.5, True):
            data["coverage_comparison"]["baseline"]["distance"] = distance
            self.write("result.json", json.dumps(data))
            check, _ = self.run_report()
            self.assertEqual(check.returncode, 1)

    def test_embedded_lint_moves_to_the_only_lint_section_without_losing_failures(self):
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results", "lint-results"]))
        self.section_defaults(**{
            "unit-results": {"id": "post-test-unit", "title": "Unit tests"},
            "lint-results": {"id": "post-lint", "title": "Static analysis"},
        })
        self.write("results.json", json.dumps({
            "suites": [{"name": "unit", "package": "example", "tests": 2}],
            "lint_packages": [{"package": "example", "tools": [{"name": "flake8", "files": [
                {"name": "same.py", "status": "passed"},
            ]}, {"name": "pep257", "files": [{"name": "same.py", "status": "failed"}]}]}],
        }))
        self.write("lint.json", "[]", self.root / "input/lint-results")
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("| Unit tests | ✅ | 2 passed |", markdown)
        self.assertIn("| Static analysis | ❌ | 1 failed of 2 checks |", markdown)
        page = (self.root / "output/build_report.html").read_text()
        self.assertIn("Unit tests — example", page)
        self.assertIn("flake8", page)
        self.assertIn("pep257", page)
        sections = json.loads((self.root / "output/build_report.json").read_text())["report_sections"]
        self.assertEqual(sections[0]["lint_packages"][0]["package"], "example")
        self.assertEqual(sections[1]["lint_packages"], [])

    def test_embedded_lint_does_not_merge_distinct_named_lint_producers(self):
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results", "pre-lint", "post-lint"]))
        self.section_defaults(**{
            "unit-results": {"id": "post-test-unit", "title": "Unit tests"},
            "pre-lint": {"id": "pre-lint", "title": "Source lint"},
            "post-lint": {"id": "post-lint", "title": "Generated lint"},
        })
        self.write("results.json", json.dumps({
            "suites": [{"name": "unit", "package": "example", "tests": 2}],
            "lint_packages": [], "sections": ["lint"],
        }))
        for name in ("pre-lint", "post-lint"):
            self.write("lint.json", "[]", self.root / "input" / name)
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("| Unit tests | ✅ | 2 passed |", markdown)
        for title in ("Unit tests — Lint", "Source lint", "Generated lint"):
            self.assertIn(f"| {title} | ✅ | 0 issues |", markdown)

    def test_unavailable_comparison_warns_escapes_content_and_has_no_delta(self):
        data = self.coverage_result()
        data["coverage_comparison"] = {"status": "unavailable", "reason": "Missing <data>%\n::error::injected"}
        self.write("result.json", json.dumps(data))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("comparison unavailable", markdown)
        self.assertIn("Missing &lt;data&gt;", markdown)
        self.assertNotIn(" pp", markdown)
        self.assertIn("%25%0A::error::injected", self.generated.stdout)
        self.assertNotIn("\n::error::injected", self.generated.stdout)

    def test_invalid_comparisons_fail_contract_validation(self):
        for comparison in (
            {"status": "exact"}, {"status": "unknown"},
            {"status": "unavailable", "reason": "missing", "delta_pp": 0},
            {**self.coverage_result()["coverage_comparison"], "delta_pp": float("nan")},
            {**self.coverage_result()["coverage_comparison"], "delta_pp": 101},
            {**self.coverage_result()["coverage_comparison"], "baseline": {
                "sha": "a" * 40, "line_rate": 0.5, "run_url": "javascript:alert(1)"}},
        ):
            with self.subTest(comparison=comparison):
                data = self.coverage_result()
                data["coverage_comparison"] = comparison
                self.write("result.json", json.dumps(data))
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 1)
                self.assertIn("Report input errors", markdown)

    def test_multiple_comparisons_in_one_producer_are_rejected(self):
        for name in ("first.json", "second.json"):
            self.write(name, json.dumps(self.coverage_result()))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("multiple coverage comparisons", markdown)

    def test_separate_producers_keep_their_own_comparisons(self):
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results", "post-results"]))
        for name, delta in (("unit-results", -5), ("post-results", 10)):
            self.write("result.json", json.dumps(self.coverage_result(delta)), self.root / "input" / name)
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("↓ −5.0 pp", markdown)
        self.assertIn("↑ +10.0 pp", markdown)
        self.assertNotIn("::warning::", self.generated.stdout)

    def test_generated_report_can_be_read_again_without_changing_producer_identity(self):
        self.write(
            "results.json",
            json.dumps(
                {
                    "section_title": "Original title",
                    "suites": [{"name": "suite", "package": "example", "tests": 1, "failures": 1}],
                    "cov_packages": [{"package": "example", "line_rate": 0.5, "lines_covered": 1, "lines_valid": 2}],
                }
            ),
        )
        check, _ = self.run_report()
        self.assertEqual(check.returncode, 1)
        saved = (self.root / "output/build_report.json").read_text()
        collect.validate_report(json.loads(saved))
        self.write("results.json", saved)
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("| Checks | ❌ | 0 passed, 1 failed |", markdown)
        self.assertIn("| Coverage | 📊 | 50.0% (1/2 lines) |", markdown)
        self.assertNotIn("Original title", markdown)
        self.assertNotIn("::warning::", self.generated.stdout)

    def test_pyright_warnings_information_and_multiline_diagnostics_are_nonblocking(self):
        diagnostics = [
            {"file": "src/group/example/code.py", "severity": severity, "message": "First line\nMore context"}
            for severity in ("warning", "warning", "information")
        ]
        self.write("pyright.json", json.dumps({"generalDiagnostics": diagnostics,
                                              "summary": {"errorCount": 0, "warningCount": 4, "informationCount": 1}}))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0, check.stdout)
        self.assertIn("PASSED WITH WARNINGS", markdown)
        self.assertIn("0 errors, 2 warnings, 1 information", markdown)
        self.assertIn("lint warnings (non-blocking)", markdown)
        self.assertIn("lint information (non-blocking)", markdown)
        self.assertNotIn("lint errors</summary>", markdown)
        self.assertIn("::warning::", self.generated.stdout)
        page = (self.root / "output/build_report.html").read_text()
        self.assertIn('class="case-row warning"', page)
        self.assertIn("Warning (2)", page)
        self.assertIn("Information (1)", page)
        saved = json.loads((self.root / "output/build_report.json").read_text())
        file = saved["report_sections"][0]["lint_packages"][0]["tools"][0]["files"][0]
        self.assertEqual(file["status"], "warning")
        self.assertEqual(len(file["diagnostics"]), 3)

    def test_pyright_information_only_and_mixed_errors(self):
        for severities, status, code in ((["information"], "information", 0),
                                          (["warning", "error", "information"], "failed", 1)):
            with self.subTest(severities=severities):
                self.write("pyright.json", json.dumps({"generalDiagnostics": [
                    {"file": "src/group/example/code.py", "severity": severity, "message": severity}
                    for severity in severities]}))
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, code)
                saved = json.loads((self.root / "output/build_report.json").read_text())
                file = saved["report_sections"][0]["lint_packages"][0]["tools"][0]["files"][0]
                self.assertEqual(file["status"], status)
                self.assertEqual(len(file["diagnostics"]), len(severities))
                self.assertIn("1 information", markdown)
                self.assertEqual("lint errors</summary>" in markdown, bool(code))

    def test_pyright_summary_cannot_hide_errors_or_claim_invalid_counts(self):
        for summary in ([], {"errorCount": 1}, {"errorCount": -1}, {"errorCount": True},
                        {"warningCount": -1}, {"informationCount": 1.5}):
            with self.subTest(summary=summary):
                self.write("pyright.json", json.dumps({"generalDiagnostics": [], "summary": summary}))
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 1)
                self.assertIn("Report input errors", markdown)
        self.write("pyright.json", json.dumps({"generalDiagnostics": [
            {"file": "code.py", "severity": "warning", "message": "warning"}], "summary": {"warningCount": 0}}))
        self.assertEqual(self.run_report()[0].returncode, 1)

    def test_legacy_lint_severities_use_check_counts_without_counting_message_lines(self):
        self.write("report.json", json.dumps({"lint_packages": [{"package": "example", "tools": [{
            "name": "custom", "files": [
                {"name": "one.py", "status": "warning", "details": "line1\nline2\nline3"},
                {"name": "two.py", "status": "information", "message": "note"},
                {"name": "three.py", "status": "passed"}]}]}]}))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("3 checks: 0 failed, 1 warning, 1 information", markdown)
        self.assertNotIn("3 error", markdown)
        self.assertIn("line1 line2 line3", markdown)

    def test_invalid_lint_severity_and_inconsistent_status_preserve_other_results(self):
        self.write("passing.xml", '<testsuite name="unit" tests="1"/>')
        for file in (
            {"name": "code.py", "status": "passed", "diagnostics": [{"severity": "error", "message": "error"}]},
            {"name": "code.py", "status": "warning", "diagnostics": [{"severity": "unknown", "message": "bad"}]},
            {"name": "code.py", "status": "warning", "diagnostics": [{"severity": "warning", "message": "bad", "line": 0}]},
        ):
            with self.subTest(file=file):
                self.write("lint.json", json.dumps({"lint_packages": [{"package": "example", "tools": [{
                    "name": "custom", "files": [file]}]}]}))
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 1)
                self.assertIn("1 passed", markdown)
                self.assertIn("Report input errors", markdown)

    def test_outcomes_and_reported_tool_policy_failures_survive_normalization(self):
        for data in (
            {"outcome": {"status": "failed", "message": "Coverage policy failed"}},
            {"outcome": {"status": "error", "message": "Tool did not complete"}},
            {"outcome": {"status": "passed"}, "issues": [{"kind": "tool", "severity": "error", "tool": "checker",
                "exit_code": 2, "message": "Execution failed", "details": "Missing <configuration>"}]},
            {"outcome": {"status": "skipped"}, "issues": [{"kind": "policy", "severity": "error", "message": "Required baseline missing"}]},
            {"outcome": {"status": "passed"}, "suites": [{"name": "unit", "package": "example", "tests": 1, "failures": 1}]},
        ):
            with self.subTest(data=data):
                self.write("result.json", json.dumps({"schema_version": 1, **data}))
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 1)
                self.assertIn("Reported failures (blocking)", markdown)
                self.assertNotIn("Report input errors", markdown)
                saved = (self.root / "output/build_report.json").read_text()
                collect.validate_report(json.loads(saved))
                self.write("result.json", saved)
                self.assertEqual(self.run_report()[0].returncode, 1)

    def test_outcome_merge_cannot_replace_an_error_with_a_pass(self):
        self.write("a.json", json.dumps({"outcome": {"status": "error", "message": "tool failed"}}))
        self.write("b.json", json.dumps({"outcome": {"status": "passed", "message": "other tool passed"}}))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertIn("tool failed", markdown)
        self.assertIn("other tool passed", markdown)

    def test_notices_and_skipped_outcomes_are_nonblocking_and_escaped(self):
        self.write("result.json", json.dumps({"schema_version": 1, "outcome": {"status": "skipped", "message": "Not applicable"},
            "issues": [{"kind": "notice", "severity": "warning", "message": "<script>%\n::error::injected"},
                       {"kind": "notice", "severity": "information", "message": "informational note"}]}))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("⏭️", markdown)
        self.assertIn("Reported notices (non-blocking)", markdown)
        self.assertNotIn("<script>", markdown)
        self.assertNotIn("\n::error::injected", self.generated.stdout)
        self.assertIn("::notice::", self.generated.stdout)

    @staticmethod
    def comparison_result():
        return {"schema_version": 1, "baselines": [{"id": "base", "status": "exact", "sha": "a" * 40,
                    "run_url": "https://github.com/example/project/actions/runs/42"}],
                "comparisons": [{"name": "Test count", "status": "available", "baseline_id": "base",
                    "current": 12, "previous": 10, "delta": -9, "unit": "tests", "delta_unit": "tests"}]}

    def test_shared_baseline_is_independent_of_coverage_and_deltas_are_not_recomputed(self):
        data = self.comparison_result()
        data["comparisons"].append({"name": "Line coverage", "status": "available", "baseline_id": "base",
                                    "current": 84.6, "previous": 82.3, "delta": 2.3, "unit": "%", "delta_unit": "pp"})
        self.write("result.json", json.dumps(data))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        for report in (markdown, (self.root / "output/build_report.html").read_text()):
            self.assertIn("Baselines", report)
            self.assertIn("Comparisons", report)
            self.assertIn("↓ −9 tests", report)
            self.assertIn("↑ +2.3 pp", report)
            self.assertEqual(report.count("/actions/runs/42"), 1)
            self.assertNotIn("B2", report)
        self.assertNotIn("no executable lines", markdown)
        self.assertNotIn("::warning::", self.generated.stdout)
        self.write("result.json", json.dumps({"baselines": data["baselines"]}))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("#### Baselines", markdown)
        self.assertNotIn("#### Comparisons", markdown)

    def test_local_baseline_ids_do_not_merge_distinct_provenance(self):
        first = self.comparison_result()
        second = self.comparison_result()
        second["baselines"][0].update(sha="b" * 40, run_url="https://github.com/example/project/actions/runs/41")
        data = {"report_sections": [dict(id=name, title=name, kinds=[], **{
            key: value for key, value in source.items() if key != "schema_version"})
            for name, source in (("first", first), ("second", second))]}
        self.write("result.json", json.dumps(data))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 0)
        self.assertIn("| B1 | Exact: [aaaaaaa]", markdown)
        self.assertIn("| B2 | Exact: [bbbbbbb]", markdown)
        normalized = json.loads((self.root / "output/build_report.json").read_text())
        comparisons = normalized["report_sections"][0]["comparisons"]
        self.assertNotEqual(comparisons[0]["baseline_id"], comparisons[1]["baseline_id"])
        self.write("result.json", json.dumps(normalized))
        self.assertEqual(self.run_report()[0].returncode, 0)
        self.assertEqual(json.loads((self.root / "output/build_report.json").read_text()), normalized)

    def test_invalid_contract_versions_references_and_tool_severities_are_blocking(self):
        base = self.comparison_result()
        invalid = [
            {**base, "schema_version": 2},
            {**base, "baselines": []},
            {**base, "baselines": base["baselines"] * 2},
            {**base, "baselines": [{"id": "base", "status": "unavailable", "reason": "missing"}]},
            {**base, "comparisons": [{**base["comparisons"][0], "delta": float("inf")}]},
            {"issues": [{"kind": "tool", "severity": "warning", "tool": "checker", "message": "failed"}]},
            {"issues": [{"kind": "tool", "severity": "error", "message": "missing tool identity"}]},
        ]
        for data in invalid:
            with self.subTest(data=data):
                self.write("result.json", json.dumps(data))
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 1)
                self.assertIn("Report input errors", markdown)

    def test_small_nonzero_changes_never_display_as_unchanged(self):
        for delta, expected in ((0, "→ 0.0 pp (unchanged)"), (0.001, "↑ +&lt;0.1 pp"), (-0.001, "↓ −&lt;0.1 pp")):
            with self.subTest(delta=delta):
                data = self.comparison_result()
                data["comparisons"][0].update(delta=delta, delta_unit="pp")
                self.write("result.json", json.dumps(data))
                check, markdown = self.run_report()
                self.assertEqual(check.returncode, 0)
                for report in (markdown, (self.root / "output/build_report.html").read_text()):
                    self.assertIn(expected, report)
                    if delta:
                        self.assertNotIn("unchanged", report)

    def test_documented_full_example_roundtrips_and_separates_input_errors(self):
        example = json.loads((ACTION / "examples/report-v1.json").read_text())
        collect.validate_report(example)
        self.write("result.json", json.dumps(example))
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results", "missing-results", "invalid-results"]))
        self.write("broken.json", "{", self.root / "input/invalid-results")
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        for report in (markdown, (self.root / "output/build_report.html").read_text()):
            self.assertIn("Report input errors (blocking)", report)
            self.assertIn("Reported failures (blocking)", report)
            self.assertIn("clang-tidy (exit 2)", report)
            self.assertIn("artifact is missing", report)
            self.assertIn("broken.json", report)
            self.assertIn("↑ +2.3 pp", report)
            self.assertIn("↓ −0.4 pp", report)
            self.assertIn("→ 0.0 pp (unchanged)", report)
            self.assertIn("Baselines", report)
        saved = json.loads((self.root / "output/build_report.json").read_text())
        collect.validate_report(saved)
        self.write("result.json", json.dumps(saved))
        (self.root / "artifacts.json").write_text(json.dumps(["unit-results"]))
        check, markdown = self.run_report()
        self.assertEqual(check.returncode, 1)
        self.assertNotIn("Report input errors", markdown)
        self.assertIn("0 errors, 2 warnings, 1 information", markdown)
        self.assertEqual(json.loads((self.root / "output/build_report.json").read_text())["report_sections"][0]["baselines"],
                         saved["report_sections"][0]["baselines"])


class PrepareTests(unittest.TestCase):
    def test_group_metadata_is_validated_and_saved_before_download(self):
        valid = {"unit-results": {"id": "post-test-unit", "title": "Unit checks"}}
        for groups in (
            valid,
            [],
            {"missing-artifact": valid["unit-results"]},
            {"unit-results": {"id": "unit"}},
            {"unit-results": {"id": "bad'id", "title": "Tests"}},
            {"unit-results": {"id": "unit", "title": " "}},
            {"unit-results": {"id": "unit", "title": "Tests", "unknown": "field"}},
            {"unit-results": {"id": "tests", "title": "First"}, "other-results": {"id": "tests", "title": "Second"}},
        ):
            with self.subTest(groups=groups), tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / "outputs"
                result = subprocess.run(
                    [sys.executable, "-B", str(ACTION / "collect.py"), "prepare"],
                    env=dict(
                        os.environ,
                        REPORT_ARTIFACT_NAMES="unit-results\nother-results",
                        REPORT_ARTIFACT_SECTIONS=json.dumps(groups),
                        RUNNER_TEMP=temp,
                        GITHUB_OUTPUT=str(output),
                    ),
                    capture_output=True,
                    text=True,
                )
                if groups == valid:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    saved = Path(action_outputs(output)["root"]) / "artifact-sections.json"
                    self.assertEqual(json.loads(saved.read_text()), valid)
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())

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
