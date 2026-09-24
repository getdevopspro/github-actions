"""Check pre/post matrix names and their command configuration."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/build.yml"
KINDS = ("checks", "lint", "test", "test-unit", "test-coverage", "test-integration", "test-e2e")


class BuildStepTests(unittest.TestCase):
    def prepare(self, phase, inputs):
        workflow = WORKFLOW.read_text()
        step = workflow.split(f"      - name: Set {phase}-steps matrix\n", 1)[1].split("      - name:", 1)[0]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        script = re.sub(
            r"\$\{\{\s*(.*?)\s*\}\}",
            lambda match: next(
                (inputs[key.strip().removeprefix("inputs.")] for key in match[1].split("||")
                 if inputs.get(key.strip().removeprefix("inputs."))),
                "",
            ),
            script,
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            subprocess.run(
                [sys.executable, "-c", script],
                env=dict(os.environ, GITHUB_OUTPUT=str(output)),
                check=True,
                capture_output=True,
                text=True,
            )
            values = output.read_text()
        matrix = json.loads(re.search(r"^matrix<<[^\n]+\n([^\n]+)", values, re.MULTILINE)[1])
        names = json.loads(re.search(r"^names=(.*)$", values, re.MULTILINE)[1])
        return names, matrix

    def test_empty_phases_have_no_matrix_jobs(self):
        for phase in ("pre", "post"):
            with self.subTest(phase=phase):
                self.assertEqual(self.prepare(phase, {}), ([], []))

    def test_custom_and_duplicate_names_preserve_each_configuration(self):
        for phase in ("pre", "post"):
            with self.subTest(phase=phase):
                inputs = {"docker-version": "28.0.0", f"{phase}-compose-version": "v2.32.4"}
                expected = []
                for index, kind in enumerate(KINDS):
                    config = {
                        "name": "Shared checks" if index < 2 else f'Custom "{kind}" ✓',
                        "command": f"run-{kind}",
                        "runner": f"runner-{index}",
                        "docker-login": "true" if index % 2 else "false",
                        "qemu-install": "false",
                        "artifact-name": f"results-{index}",
                        "artifact-path": f"build/{kind}.xml",
                        "artifact-overwrite": "true",
                        "artifact-if-no-files-found": "error",
                        "artifact-retention-days": str(index + 1),
                    }
                    inputs.update({f"{phase}-{kind}-{key}": value for key, value in config.items()})
                    expected.append({**config, "docker-version": "28.0.0", "compose-version": "v2.32.4"})
                names, configurations = self.prepare(phase, inputs)
                self.assertEqual(configurations, expected)
                self.assertEqual(names, [config["name"] for config in expected])

    def test_disabled_commands_do_not_shift_name_configuration_pairs(self):
        for phase in ("pre", "post"):
            with self.subTest(phase=phase):
                names, configurations = self.prepare(phase, {
                    f"{phase}-checks-name": "Disabled checks",
                    f"{phase}-lint-name": "Python Lint",
                    f"{phase}-lint-command": "run-lint",
                    f"{phase}-test-name": "Disabled tests",
                    f"{phase}-test-unit-name": "Unit Tests",
                    f"{phase}-test-unit-command": "run-unit-tests",
                })
                self.assertEqual(names, ["Python Lint", "Unit Tests"])
                self.assertEqual([config["command"] for config in configurations], ["run-lint", "run-unit-tests"])

    def test_phase_names_are_static_and_only_names_enter_the_matrix(self):
        workflow = WORKFLOW.read_text()
        for phase in ("pre", "post"):
            with self.subTest(phase=phase):
                job = re.split(r"\n  (?=\S)", workflow.split(f"\n  {phase}-steps:\n", 1)[1], maxsplit=1)[0]
                self.assertIn(f"    name: {phase.title()} Step\n", job)
                self.assertIn(f"name: ${{{{ fromJson(needs.prepare.outputs.{phase}-step-names) }}}}", job)
                self.assertIn(f"toJSON(fromJSON(needs.prepare.outputs.{phase}-step-matrix)[strategy.job-index])", job)


if __name__ == "__main__":
    unittest.main()
