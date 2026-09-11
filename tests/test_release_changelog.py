"""Run changelog generation locally; git-cliff 2.14.1 is the reference version.

Set GIT_CLIFF_BIN or put git-cliff on PATH. These tests exercise the action's
generation block, bypassing its downloader and artifact upload step.
"""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ACTION = Path(__file__).resolve().parents[1] / "release/changelog/action.yml"
ROOT_NOTE = "Root history marker"
PREVIOUS_NOTE = "Previous history marker"
CURRENT_NOTE = "Current release marker"


class ChangelogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.git_bin = shutil.which("git")
        cls.cliff_bin = shutil.which(os.environ.get("GIT_CLIFF_BIN", "git-cliff"))
        if not cls.git_bin or not cls.cliff_bin:
            raise RuntimeError(
                "git and git-cliff are required; install git-cliff or set "
                "GIT_CLIFF_BIN=/path/to/git-cliff (tested with 2.14.1)"
            )
        marker = '        echo "Setting up git-cliff context..."\n'
        source = ACTION.read_text()
        if source.count(marker) != 1:
            raise RuntimeError("Cannot find the action's changelog generation block")
        body = source.split(marker, 1)[1].split("\n    - name:", 1)[0]
        cls.script = "set -euo pipefail\n" + textwrap.dedent(body)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="changelog-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.runner_temp = self.root / "runner"
        self.runner_temp.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.bin / "git-cliff").symlink_to(self.cliff_bin)
        self.output_name = "docs/releases/CHANGELOG.md"
        self.changelog = self.repo / self.output_name
        self.github_output = self.root / "github-output"
        self.summary = self.root / "summary"
        self.artifact_dir = self.runner_temp / "artifact"
        self.env = {
            "LANG": "C.UTF-8",
            "XDG_CACHE_HOME": str(self.root / "cache"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Changelog Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Changelog Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "ARTIFACT": "true",
            "CHANGELOG_ARTIFACT_DIR": str(self.artifact_dir),
            "CHANGELOG_OUTPUT": self.output_name,
            "CONFIG": str(ACTION.parent / "cliff.toml"),
            "GIT_CLIFF_ARGS": "",
            "GIT_CLIFF_OFFLINE": "true",
            "CLIFF_USE_EMOJIS": "false",
            "CLIFF_VERSION_PREFIX": "v",
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPO": "example/project",
            "GITHUB_REPOSITORY": "example/project",
            "GITHUB_SERVER_URL": "https://example.invalid",
            "GITHUB_TOKEN": "",
            "GH_TOKEN": "",
            "PREPEND": "true",
            "PREVIOUS_VERSION": "v2026.8.1",
            "RUNNER_TEMP": str(self.runner_temp),
            "SUMMARY": "true",
            "VERSION": "v2026.9.0",
            "GITHUB_OUTPUT": str(self.github_output),
            "GITHUB_STEP_SUMMARY": str(self.summary),
        }
        self.commit_count = 0
        self.git("init", "--quiet")

    def git(self, *args):
        return subprocess.run(
            [self.git_bin, *args], cwd=self.repo, env=self.env, check=True,
            capture_output=True, text=True,
        ).stdout

    def commit(self, message):
        self.commit_count += 1
        date = f"2026-09-01T12:00:{self.commit_count:02d}+00:00"
        self.env.update({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date})
        self.git(
            "-c", "commit.gpgsign=false", "commit", "--quiet", "--allow-empty",
            "-m", message,
        )

    def add_release_history(self):
        self.commit("feat: root history marker")
        self.git("tag", "v2026.8.0")
        self.commit("feat: previous history marker")
        self.git("tag", "v2026.8.1")
        self.commit("fix: current release marker")

    def run_action(self, **inputs):
        return subprocess.run(
            ["bash", "-c", self.script], cwd=self.repo, env=self.env | inputs,
            capture_output=True, text=True,
        )

    def assert_release_outputs(self):
        header, body = self.github_output.read_text().split("\n", 1)
        self.assertTrue(header.startswith("content<<"))
        delimiter = header.removeprefix("content<<") + "\n"
        self.assertTrue(body.endswith(delimiter))
        content = body[:-len(delimiter)]
        self.assertEqual(self.summary.read_text(), "# Release changelog\n\n" + content)
        self.assertEqual((self.artifact_dir / "CHANGELOG.md").read_text(), content)
        self.assertTrue(content.endswith("\n"))
        self.assertFalse(content.endswith("\n\n"))
        return content

    def assert_only_current_release(self, content):
        headings = re.findall(r"(?m)^## \[?(v[0-9.]+)", content)
        self.assertEqual(headings, ["v2026.9.0"])
        self.assertIn(CURRENT_NOTE, content)
        self.assertNotIn(ROOT_NOTE, content)
        self.assertNotIn(PREVIOUS_NOTE, content)

    def assert_staged_changelog(self):
        self.assertEqual(self.git("diff", "--cached", "--name-only").strip(), self.output_name)
        self.assertEqual(self.git("show", ":" + self.output_name), self.changelog.read_text())

    def assert_no_release_outputs(self):
        self.assertFalse(self.github_output.exists())
        self.assertFalse(self.summary.exists())
        self.assertFalse(self.artifact_dir.exists())
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")

    def test_missing_nested_changelog_saves_history_but_publishes_current_notes(self):
        self.add_release_history()
        result = self.run_action()
        self.assertEqual(result.returncode, 0, result.stderr)
        history = self.changelog.read_text()
        self.assertIn(ROOT_NOTE, history)
        self.assertIn(PREVIOUS_NOTE, history)
        self.assertIn(CURRENT_NOTE, history)
        self.assertEqual(
            re.findall(r"(?m)^## \[?(v[0-9.]+)", history),
            ["v2026.9.0", "v2026.8.1", "v2026.8.0"],
        )
        self.assert_only_current_release(self.assert_release_outputs())
        self.assert_staged_changelog()

    def test_existing_changelog_preserves_manual_history(self):
        self.add_release_history()
        self.changelog.parent.mkdir(parents=True)
        manual_history = "## v2026.8.1\n\nHand-edited historical note kept exactly.\n"
        self.changelog.write_text(manual_history)
        result = self.run_action()
        self.assertEqual(result.returncode, 0, result.stderr)
        history = self.changelog.read_text()
        self.assertTrue(history.endswith(manual_history), history)
        self.assertEqual(history.count("Hand-edited historical note kept exactly."), 1)
        self.assertIn(CURRENT_NOTE, history)
        self.assertNotIn(ROOT_NOTE, history)
        self.assertNotIn(PREVIOUS_NOTE, history)
        self.assert_only_current_release(self.assert_release_outputs())
        self.assert_staged_changelog()

    def test_initial_missing_ref_includes_root_commit(self):
        self.commit("feat: root history marker")
        self.commit("fix: current release marker")
        result = self.run_action(PREVIOUS_VERSION="0.0.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        content = self.assert_release_outputs()
        self.assertIn(ROOT_NOTE, content)
        self.assertIn(CURRENT_NOTE, content)
        self.assertEqual(self.changelog.read_text(), content)
        self.assert_staged_changelog()

    def test_explicit_overwrite_uses_tagged_version_instead_of_head(self):
        self.add_release_history()
        self.git("tag", "v2026.9.0")
        self.commit("feat: after release marker")
        self.changelog.parent.mkdir(parents=True)
        self.changelog.write_text("Existing history to overwrite.\n")
        result = self.run_action(PREPEND="false")
        self.assertEqual(result.returncode, 0, result.stderr)
        content = self.assert_release_outputs()
        self.assert_only_current_release(content)
        self.assertNotIn("After release marker", content)
        self.assertNotIn("Existing history to overwrite.", content)
        self.assertEqual(self.changelog.read_text(), content)
        self.assert_staged_changelog()

    def test_invalid_previous_ref_fails_without_initializing_changelog(self):
        self.add_release_history()
        result = self.run_action(PREVIOUS_VERSION="v-does-not-exist")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.changelog.exists())
        self.assert_no_release_outputs()

    def test_dangling_symlink_is_not_initialized(self):
        self.add_release_history()
        self.changelog.parent.mkdir(parents=True)
        missing_target = self.changelog.parent / "missing-target.md"
        self.changelog.symlink_to(missing_target.name)
        result = self.run_action()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.changelog.is_symlink())
        self.assertFalse(missing_target.exists())
        self.assert_no_release_outputs()


if __name__ == "__main__":
    unittest.main()
