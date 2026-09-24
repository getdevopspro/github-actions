"""Check pre/post matrix names and their command configuration."""

import json
from pathlib import Path
import re
import sys
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/build.yml"
PREPARE = WORKFLOW.parents[2] / "build/report/prepare"
sys.path.insert(0, str(PREPARE))
from prepare import prepare_inputs


KINDS = ("checks", "lint", "test", "test-unit", "test-coverage", "test-integration", "test-e2e")


class BuildStepTests(unittest.TestCase):
    def prepare(self, phase, inputs):
        outputs = prepare_inputs(inputs)
        return json.loads(outputs[f"{phase}-step-names"]), json.loads(outputs[f"{phase}-step-matrix"])

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

    def test_input_text_is_preserved_as_data(self):
        name = "Checks ''' with quotes"
        command = 'printf "%s\\n" "$HOME"\njust test --label "quoted"'
        for phase in ("pre", "post"):
            with self.subTest(phase=phase):
                names, configurations = self.prepare(phase, {
                    f"{phase}-test-name": name,
                    f"{phase}-test-command": command,
                })
                self.assertEqual(names, [name])
                self.assertEqual(configurations[0]["command"], command)

    def test_typed_workflow_inputs_keep_command_strings(self):
        _, configurations = self.prepare("post", {
            "post-test-command": "run-tests",
            "post-test-docker-login": True,
            "post-test-qemu-install": False,
            "post-test-artifact-overwrite": False,
            "post-test-artifact-retention-days": 30,
        })
        self.assertEqual(configurations[0]["docker-login"], "true")
        self.assertEqual(configurations[0]["qemu-install"], "false")
        self.assertEqual(configurations[0]["artifact-overwrite"], "false")
        self.assertEqual(configurations[0]["artifact-retention-days"], "30")

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
