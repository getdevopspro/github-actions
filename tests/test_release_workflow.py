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
BUILD = ROOT / ".github/workflows/build.yml"
GIT_PUSH = ROOT / "release/git-push/action.yml"


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


class VersionFileTests(unittest.TestCase):
    def test_workflows_pass_version_file_to_the_action(self):
        for workflow, name in ((BUILD, "Set version in file"), (RELEASE, "set version in file")):
            with self.subTest(workflow=workflow.name):
                self.assertIn("\n      version-file:\n", workflow.read_text())
                self.assertIn("          version-file: ${{ inputs.version-file }}\n", step(workflow, name, 6))


class GitPushTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.origin = self.root / "origin.git"
        self.work = self.root / "work"
        run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(self.origin)], self.root)
        run(["git", "clone", "--quiet", str(self.origin), str(self.work)], self.root)
        run(["git", "checkout", "--quiet", "-b", "main"], self.work)
        (self.work / "Makefile").write_text("VERSION ?= 1.2.2\n")
        run(["git", "add", "Makefile"], self.work)
        commit(self.work, "Test fixture")
        run(["git", "push", "--quiet", "origin", "main"], self.work)

    def push(self, version, add_files, prefix=None):
        block = step(GIT_PUSH, "Push git version", 4)
        default = re.search(r"\n  version-tag-prefix:\n(?:    .*\n)*?    default: '(.*)'\n", GIT_PUSH.read_text())
        inputs = {
            "version": version,
            "version-tag-prefix": default.group(1) if prefix is None else prefix,
            "git-user-name": "Release Bot",
            "git-user-email": "bot@example.invalid",
            "git-add-files": add_files,
        }

        def render(text):
            text = re.sub(r"\$\{\{ inputs\.([\w-]+) \}\}", lambda match: inputs[match.group(1)], text)
            text = text.replace("${{ github.event.repository.default_branch }}", "main")
            self.assertNotIn("${{", text)
            return text

        env = git_env(GITHUB_REF_TYPE="branch")
        for line in block.split("      env:\n", 1)[1].split("      run: |\n", 1)[0].splitlines():
            key, value = line.strip().split(": ", 1)
            env[key] = render(value)
        return run(["bash", "-c", render(script(block))], self.work, env, check=False)

    def remote(self, *args):
        return run(["git", "--git-dir", str(self.origin), *args], self.root).stdout.strip()

    def test_default_prefix_tags_the_version_without_changes(self):
        result = self.push("1.2.3", "Makefile")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Creating and pushing tag v1.2.3", result.stdout)
        self.assertEqual(self.remote("tag", "--list"), "v1.2.3")

    def test_custom_prefix_names_the_tag_and_bump_commit(self):
        (self.work / "Makefile").write_text("VERSION ?= 1.2.3\n")
        result = self.push("1.2.3", "Makefile", prefix="release-")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.remote("tag", "--list"), "release-1.2.3")
        self.assertEqual(self.remote("log", "-1", "--format=%s", "main"), "chore: bump version to release-1.2.3")
        self.assertEqual(self.remote("rev-parse", "release-1.2.3^{commit}"), self.remote("rev-parse", "main"))

    def test_existing_tag_is_not_recreated(self):
        for prefix, tag in ((None, "v1.2.3"), ("release-", "release-1.2.3")):
            with self.subTest(prefix=prefix):
                run(["git", "tag", tag], self.work)
                result = self.push("1.2.3", "Makefile", prefix=prefix)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"Tag {tag} already exists", result.stdout)
                self.assertEqual(self.remote("tag", "--list"), "")

    def test_release_workflow_passes_its_tag_prefix(self):
        self.assertIn(
            "          version-tag-prefix: ${{ inputs.version-tag-prefix }}\n",
            step(RELEASE, "push git version", 6),
        )


if __name__ == "__main__":
    unittest.main()
