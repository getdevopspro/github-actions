"""Exercise every version-file action format against temporary project files."""

import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import textwrap
import unittest


ACTION = Path(__file__).resolve().parents[1] / "version-file/action.yml"
TEXT_TARGETS = ("Makefile", "justfile", "package.json", "package-lock.json", "script")


class VersionFileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="version-file-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "target file"

    def update(self, target, version="2026.9.0", chart="demo"):
        name = (
            "Set Ansible collection version" if target == "galaxy.yml"
            else f"Set version in {target}"
        )
        step = ACTION.read_text().split(
            f"    - name: {name}\n", 1,
        )[1].split("\n    - name:", 1)[0]
        script = self.root / "update-version"
        script.write_text(textwrap.dedent(step.split("      run: |\n", 1)[1]))
        command = shlex.split(step.split("      shell: ", 1)[1].splitlines()[0])
        if "{0}" in command:
            command[command.index("{0}")] = str(script)
        else:
            command.append(str(script))
        return subprocess.run(
            command,
            cwd=self.root,
            env=os.environ | {
                "VERSION": version,
                "VERSION_FILE": str(self.path),
                "VERSION_CHART": chart,
                "GALAXY_FILE": str(self.path),
                "GALAXY_VERSION": version,
            },
            capture_output=True, text=True,
        )

    def assert_update(self, target, before, after):
        self.path.write_bytes(before.encode())
        result = self.update(target)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.path.read_bytes(), after.encode())

    def test_plain_file_is_created_and_overwritten(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                if existing:
                    self.path.write_text("old version\nold contents\n")
                result = self.update("file")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.path.read_bytes(), b"2026.9.0\n")

    def test_makefile_preserves_existing_match_scope(self):
        unchanged = " VERSION = keep\nVERSION\t= keep\nexport VERSION=keep\nOTHER_VERSION = keep\n"
        self.assert_update(
            "Makefile",
            "VERSION ?= 1.0.0\nVERSION := 2.0.0\n" + unchanged,
            "VERSION ?= 2026.9.0\nVERSION ?= 2026.9.0\n" + unchanged,
        )

    def test_justfile_preserves_other_assignments(self):
        unchanged = 'app_version := "keep"\n version := "keep"\n'
        self.assert_update(
            "justfile",
            'version := "1.0.0"\n' + unchanged,
            'version := "2026.9.0"\n' + unchanged,
        )

    def test_package_updates_version_lines_without_reformatting(self):
        before = '{\n  "version": "1.0.0",\n  "nested": {\n    "version": "2.0.0",\n    "name": "demo"\n  }\n}\n'
        after = before.replace('"version": "1.0.0"', '"version": "2026.9.0"').replace(
            '"version": "2.0.0"', '"version": "2026.9.0"',
        )
        self.assert_update("package.json", before, after)

    def test_package_lock_only_updates_first_fifteen_lines(self):
        lines = ['{', '  "version": "1.0.0",'] + ['  "placeholder": true,'] * 12
        lines += ['  "version": "2.0.0",', '  "version": "3.0.0",', '}']
        before = "\n".join(lines) + "\n"
        after = before.replace('"1.0.0"', '"2026.9.0"').replace('"2.0.0"', '"2026.9.0"')
        self.assert_update("package-lock.json", before, after)

    def test_missing_package_lock_is_a_successful_no_op(self):
        result = self.update("package-lock.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.path.exists())

    def test_script_only_updates_unindented_version_assignment(self):
        unchanged = "export VERSION=keep\n VERSION=keep\nVERSION =keep\nOTHER_VERSION=keep\n"
        self.assert_update("script", "VERSION=1.0.0\n" + unchanged, "VERSION=2026.9.0\n" + unchanged)

    def test_chart_updates_chart_version_and_value_tags(self):
        chart = "demo chart"
        folder = self.root / "charts" / chart
        folder.mkdir(parents=True)
        (folder / "Chart.yaml").write_text('version: 1.0.0\nappVersion: "keep"\n')
        (folder / "values.yaml").write_text('image:\n  tag: "1.0.0"\n  repository: example/demo\n')
        result = self.update("Helm chart", chart=chart)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((folder / "Chart.yaml").read_text(), 'version: 2026.9.0\nappVersion: "keep"\n')
        self.assertEqual((folder / "values.yaml").read_text(), 'image:\n  tag: 2026.9.0\n  repository: example/demo\n')

    def test_missing_required_files_fail(self):
        for target in (*TEXT_TARGETS[:3], "script", "Helm chart"):
            with self.subTest(target=target):
                result = self.update(target)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.path.exists())

    def test_nonmatching_text_files_are_unchanged(self):
        for target in TEXT_TARGETS:
            with self.subTest(target=target):
                self.assert_update(target, "# No matching version field\n", "# No matching version field\n")

    def test_paths_and_versions_are_not_executed_as_shell_code(self):
        self.path = self.root / "target ' $(touch injected-path)"
        for target, before in (
            ("file", "old\n"), ("Makefile", "VERSION ?= old\n"),
            ("justfile", 'version := "old"\n'),
            ("package.json", '  "version": "old",\n'),
            ("package-lock.json", '  "version": "old",\n'),
            ("script", "VERSION=old\n"),
        ):
            with self.subTest(target=target):
                self.path.write_text(before)
                result = self.update(target, version="$(touch injected-version)")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("$(touch injected-version)", self.path.read_text())
                self.assertFalse((self.root / "injected-path").exists())
                self.assertFalse((self.root / "injected-version").exists())

    def test_galaxy_preserves_metadata_quotes_comments_and_nested_versions(self):
        for field in (
            "version: 1.0.0",
            "version: '1.0.0' # collection release",
            'version:  "1.0.0"  # collection release',
            '"version" : 1.0.0',
            "'version': 1.0.0",
        ):
            with self.subTest(field=field):
                contents = (
                    "---\n# Example collection\nnamespace: example\nname: demo\n"
                    f"{field}\n  # Metadata comment\n\n"
                    'description: "Café demo"\ndependencies:\n'
                    '  example.dependency: ">=1.0.0"\n'
                    "custom:\n  version: 1.0.0\n"
                ).encode()
                self.path.write_bytes(contents)
                result = self.update("galaxy.yml")
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = contents.replace(
                    field.encode(), field.replace("1.0.0", "2026.9.0").encode(), 1,
                )
                self.assertEqual(self.path.read_bytes(), expected)

    def test_galaxy_accepts_semver_calver_prereleases_and_build_metadata(self):
        for version in ("1.2.3", "2026.9.0", "2026.9.0-build", "2026.9.0-rc.1+build.02"):
            with self.subTest(version=version):
                self.path.write_text("version: 1.0.0\n")
                result = self.update("galaxy.yml", version)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.path.read_text(), f"version: {version}\n")

    def test_galaxy_preserves_line_endings_and_missing_final_newline(self):
        for ending in (b"\n", b"\r\n", b""):
            with self.subTest(ending=ending):
                self.path.write_bytes(b"version: 1.0.0" + ending)
                result = self.update("galaxy.yml")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.path.read_bytes(), b"version: 2026.9.0" + ending)

    def test_galaxy_treats_paths_as_literal_data(self):
        self.path = self.root / "galaxy ' $(touch injected) [draft].yml"
        self.path.write_text("version: 1.0.0\n")
        result = self.update("galaxy.yml")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.path.read_text(), "version: 2026.9.0\n")
        self.assertFalse((self.root / "injected").exists())

    def test_galaxy_rejects_invalid_versions_without_writing(self):
        for version in (
            "", "v2026.9.0", "2026.09.0", "01.2.3", "1.2.03", "2026.9",
            "2026.9.0-01", "2026.9.0-rc.01", "2026.9.0+", "2026.9.0-",
            "2026.9.0\n", "2026.9.0\nnamespace: changed", "2026.9.０",
            "$(touch injected)",
        ):
            with self.subTest(version=version):
                contents = b"version: 1.0.0\n"
                self.path.write_bytes(contents)
                result = self.update("galaxy.yml", version)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("SemVer", result.stderr)
                self.assertEqual(self.path.read_bytes(), contents)
                self.assertFalse((self.root / "injected").exists())

    def test_galaxy_rejects_missing_duplicate_or_unsupported_fields_without_writing(self):
        for contents in (
            b"namespace: example\n",
            b"nested:\n  version: 1.0.0\n",
            b"version: 1.0.0\nversion: 2.0.0\n",
            b'version: 1.0.0\n"version": 2.0.0\n',
            b"version: 1.0.0\n'version': 2.0.0\n",
            b"version: \n",
            b"version: >-\n  1.0.0\n",
            b"version: [1, 0, 0]\n",
            b"version: &release 1.0.0\n",
            b"version:1.0.0\n",
            b"version: 1.0.0#suffix\n",
            b"version: 1.0.0\n  continued\n",
            b"version: 1.0.0\n  # Comment\n\n  continued\n",
        ):
            with self.subTest(contents=contents):
                self.path.write_bytes(contents)
                result = self.update("galaxy.yml")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("version-galaxy:", result.stderr)
                self.assertEqual(self.path.read_bytes(), contents)

    def test_galaxy_missing_file_is_not_created(self):
        result = self.update("galaxy.yml")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version-galaxy:", result.stderr)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
