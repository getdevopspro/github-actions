"""Check which commit the Build prepare job checks out and how it names it."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/build.yml"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"


def step(name):
    block = WORKFLOW.read_text().split(f"\n      - name: {name}\n", 1)[1]
    return re.split(r"\n      - name: |\n  (?=\S)", block, maxsplit=1)[0]


def run(block, env, cwd=None):
    script = textwrap.dedent(block.split("        run: |\n", 1)[1])
    with tempfile.TemporaryDirectory() as temp:
        output = Path(temp) / "output"
        output.touch()
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=cwd,
            env={"PATH": os.environ["PATH"], "GITHUB_OUTPUT": str(output), **env},
            capture_output=True,
            text=True,
        )
        return result, dict(line.split("=", 1) for line in output.read_text().splitlines())


class PullRequestCheckoutTests(unittest.TestCase):
    def resolve(self, mode, event, head=HEAD_SHA):
        return run(step("Resolve pull request checkout"), {"PR_CHECKOUT": mode, "EVENT_NAME": event, "PR_HEAD_SHA": head})

    def test_head_checks_out_the_pull_request_head(self):
        result, outputs = self.resolve("head", "pull_request")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(outputs, {"ref": HEAD_SHA})

    def test_merge_and_events_without_a_pull_request_keep_the_default_checkout(self):
        for mode, event, head in (
            ("merge", "pull_request", HEAD_SHA),
            ("merge", "pull_request_target", HEAD_SHA),
            ("merge", "push", ""),
            ("head", "push", ""),
            ("head", "workflow_dispatch", ""),
        ):
            with self.subTest(mode=mode, event=event):
                result, outputs = self.resolve(mode, event, head)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(outputs, {"ref": ""})
                self.assertNotIn("::notice::", result.stdout)

    def test_head_keeps_the_default_checkout_for_pull_request_target(self):
        result, outputs = self.resolve("head", "pull_request_target")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(outputs, {"ref": ""})
        self.assertIn("::notice::pr-checkout: head applies only to pull_request events", result.stdout)

    def test_unknown_modes_fail(self):
        for mode in ("", "Head", "base"):
            with self.subTest(mode=mode):
                result, outputs = self.resolve(mode, "pull_request")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("pr-checkout must be merge or head", result.stderr)
                self.assertEqual(outputs, {})

    def test_checkout_follows_the_resolved_ref(self):
        workflow = WORKFLOW.read_text()
        self.assertLess(
            workflow.index("      - name: Resolve pull request checkout"),
            workflow.index("      - name: Checkout repository"),
        )
        resolve = step("Resolve pull request checkout")
        for line in (
            "        id: pr_checkout\n",
            "          PR_CHECKOUT: ${{ inputs.pr-checkout }}\n",
            "          EVENT_NAME: ${{ github.event_name }}\n",
            "          PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}\n",
        ):
            self.assertIn(line, resolve)
        self.assertIn("          ref: ${{ steps.pr_checkout.outputs.ref }}\n", step("Checkout repository"))


if __name__ == "__main__":
    unittest.main()
