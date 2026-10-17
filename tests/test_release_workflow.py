"""Check the Release workflow and the release helpers it calls."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".github/workflows/release.yml"


def step(path, name, indent):
    block = path.read_text().split(f"\n{' ' * indent}- name: {name}\n", 1)[1]
    return re.split(rf"\n {{{indent}}}- |\n(?=\S)", block, maxsplit=1)[0]


def script(block):
    return textwrap.dedent(re.split(r"run: \|\n", block, maxsplit=1)[1])


def git_env(**extra):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0", **extra})
    return env


def run(command, cwd, env=None, check=True):
    return subprocess.run(command, cwd=cwd, env=env or git_env(), check=check, capture_output=True, text=True)


def commit(repo, message):
    run([
        "git", "-c", "user.name=Release Test", "-c", "user.email=test@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "--quiet", "--allow-empty", "-m", message,
    ], repo)


class CommitShaTests(unittest.TestCase):
    def test_commit_sha_is_the_checked_out_commit(self):
        block = step(RELEASE, "Determine commit SHA", 6)
        self.assertNotIn("pull_request", block)
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            output = repo / "output"
            output.touch()
            run(["git", "init", "--quiet"], repo)
            commit(repo, "Test fixture")
            result = run(["bash", "-c", script(block)], repo, git_env(GITHUB_OUTPUT=str(output)), check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_text(), f"sha={run(['git', 'rev-parse', 'HEAD'], repo).stdout.strip()}\n")

    def test_commit_sha_output_exports_the_job_output(self):
        workflow = RELEASE.read_text()
        outputs = workflow.split("\n    outputs:\n", 1)[1].split("\n    inputs:\n", 1)[0]
        self.assertRegex(outputs, r"      commit-sha:\n        description: .*\n        value: \$\{\{ jobs\.release\.outputs\.commit-sha \}\}\n")
        self.assertIn("      commit-sha: ${{ steps.determine_sha.outputs.sha }}\n", workflow)

    def test_commit_sha_is_taken_before_the_release_commits(self):
        workflow = RELEASE.read_text()
        sha = workflow.index("      - name: Determine commit SHA\n")
        self.assertLess(workflow.index("      - name: checkout repository\n"), sha)
        for later in ("      - name: run make target before push\n", "      - name: push git version\n"):
            self.assertLess(sha, workflow.index(later))


if __name__ == "__main__":
    unittest.main()
