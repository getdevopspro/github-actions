"""Exercise CalVer generation in temporary local Git repositories."""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


VERSION_SCRIPT = Path(__file__).resolve().parents[1] / "release/version/calver/version.sh"
GIT = shutil.which("git")

# From usage-syncer/justfile's version and next-version recipes. Use a shell
# function in place of `just version` so these tests need no sibling checkout.
USAGE_SYNCER_RECIPES = r"""
set -euo pipefail
version() {
    git tag --list 'v[0-9]*' | sed 's/^v//' | sort -V | tail -1 | grep . || echo "0.0.0"
}
year=$(date -u +%Y)
month=$((10#$(date -u +%m)))
current=$(version)
printf '%s\n' "$current"
if [ "${current%.*}" = "${year}.${month}" ]; then
    echo "${year}.${month}.$((${current##*.} + 1))"
else
    echo "${year}.${month}.0"
fi
"""


@unittest.skipUnless(GIT, "git is required")
class CalVerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="calver-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.output = self.root / "github-output"
        self.env = {
            key: value for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        self.env.update({
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
        })
        self.write_stub("date", """#!/bin/sh
[ "$#" -eq 2 ] && [ "$1" = -u ] || exit 1
case "$2" in
    '+%Y %m') printf '%s\\n' "$TEST_UTC_YEAR_MONTH" ;;
    '+%Y') printf '%s\\n' "${TEST_UTC_YEAR_MONTH%% *}" ;;
    '+%m') printf '%s\\n' "${TEST_UTC_YEAR_MONTH##* }" ;;
    *) exit 1 ;;
esac
""")
        self.git("init", "--quiet")
        self.commit()

    def write_stub(self, name, contents):
        path = self.bin / name
        path.write_text(contents)
        path.chmod(0o755)

    def git(self, *args):
        return subprocess.run(
            [GIT, *args], cwd=self.repo, env=self.env, check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    def commit(self):
        self.git(
            "-c", "user.name=CalVer Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "--quiet", "--allow-empty",
            "-m", "Test fixture",
        )

    def add_tags(self, *tags):
        for tag in tags:
            self.git("tag", "--", tag)

    def run_version(self, utc="2026 09", **inputs):
        self.output.unlink(missing_ok=True)
        env = self.env | {
            "GITHUB_OUTPUT": str(self.output),
            "TEST_UTC_YEAR_MONTH": utc,
            "VERSION_OUTPUT_FORMAT": "{{.Major}}.{{.Minor}}.{{.Patch}}",
            "VERSION_TAG": "false",
            "VERSION_TAG_PREFIX": "v",
        } | inputs
        result = subprocess.run(
            ["bash", str(VERSION_SCRIPT)], cwd=self.repo, env=env,
            capture_output=True, text=True,
        )
        output = self.output.read_text() if self.output.exists() else ""
        return result, output

    def assert_version(self, version, previous, **inputs):
        result, output = self.run_version(**inputs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, f"version={version}\nprevious-version={previous}\n")

    def test_initial_release_is_read_only(self):
        head = self.git("rev-parse", "HEAD")
        self.assert_version("2026.9.0", "0.0.0")
        self.assertEqual(self.git("tag", "--list"), "")
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_same_month_increments_highest_numeric_patch(self):
        self.add_tags("v2026.8.99", "v2026.9.2", "v2026.9.9", "v2026.9.10")
        self.assert_version("2026.9.11", "v2026.9.10")

    def test_month_rollover_starts_at_zero(self):
        self.add_tags("v2026.8.99")
        self.assert_version("2026.9.0", "v2026.8.99")

    def test_year_rollover_starts_at_zero(self):
        self.add_tags("v2026.12.99")
        self.assert_version("2027.1.0", "v2026.12.99", utc="2027 01")

    def test_global_latest_tag_controls_reset(self):
        self.add_tags("v2026.9.8", "v2027.1.0")
        self.assert_version("2026.9.0", "v2027.1.0")

    def test_semver_history_is_preserved_during_calver_migration(self):
        self.add_tags("v2.9.99", "v3.1.1")
        self.assert_version("2026.9.0", "v3.1.1")

    def test_history_selection_does_not_require_strict_calver(self):
        self.add_tags("v2026.9.8", "v2026.13.99")
        self.assert_version("2026.9.0", "v2026.13.99")

    def test_default_prefix_filters_history(self):
        self.add_tags(
            "v2026.9.1", "2026.9.99", "vv2026.9.98", "release-2026.9.97",
            "vnext", "v-2026.9.99", "vrc-2026.9.99", "2026.9.2-rc1",
        )
        self.assert_version("2026.9.2", "v2026.9.1")

    def test_unprefixed_candidates_do_not_count_as_releases(self):
        self.add_tags("2026.9.0-rc1", "2026.9.0-rc2")
        self.assert_version("2026.9.0", "0.0.0")

    def test_empty_prefix_selects_unprefixed_tags(self):
        self.add_tags("2026.9.1", "v2026.9.99", "release-2026.9.98")
        self.assert_version("2026.9.2", "2026.9.1", VERSION_TAG_PREFIX="")

    def test_custom_prefix_is_literal_and_preserved(self):
        self.add_tags("release.+-2026.9.1", "releaseX+-2026.9.99", "v2026.9.98")
        self.assert_version("2026.9.2", "release.+-2026.9.1", VERSION_TAG_PREFIX="release.+-")

    def test_build_output_format_preserves_previous_tag(self):
        self.add_tags("v2026.9.3", "2026.9.4-rc2")
        tags = self.git("tag", "--list")
        self.assert_version(
            "2026.9.4-build", "v2026.9.3",
            VERSION_OUTPUT_FORMAT="{{.Major}}.{{.Minor}}.{{.Patch}}-build",
        )
        self.assertEqual(self.git("tag", "--list"), tags)

    def test_current_month_nonnumeric_patch_fails_without_outputs_or_tags(self):
        for patch in ("99-rc1", "99-build", "99+metadata", "-1", "0+1"):
            with self.subTest(patch=patch):
                tag = "v2026.9." + patch
                self.add_tags(tag)
                result, output = self.run_version(VERSION_TAG="true")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("numeric patch", result.stderr)
                self.assertEqual(output, "")
                self.assertEqual(self.git("tag", "--list"), tag)
                self.git("tag", "--delete", "--", tag)

    def test_tag_shell_expression_is_rejected_without_execution(self):
        self.add_tags("v2026.9.$(touch${IFS}calver-injection)")
        result, output = self.run_version()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("numeric patch", result.stderr)
        self.assertEqual(output, "")
        self.assertFalse((self.repo / "calver-injection").exists())

    def test_numeric_patch_increment_uses_base_ten(self):
        self.add_tags("v2026.9.09")
        self.assert_version("2026.9.10", "v2026.9.09")

    def test_matches_usage_syncer_recipes_for_release_history(self):
        cases = (
            ("2026 09", ()),
            ("2026 09", ("v3.1.1",)),
            ("2026 09", ("v2026.9.2", "v2026.9.9", "v2026.9.10")),
            ("2026 09", ("v2026.8.99",)),
            ("2027 01", ("v2026.12.99",)),
            ("2026 09", ("v2026.9.8", "v2027.1.0")),
            ("2026 09", ("v2026.9.3", "2026.9.4-rc2", "vnext")),
            ("2026 09", ("v2026.9.3", "v2026.13.99")),
        )
        for index, (utc, tags) in enumerate(cases):
            with self.subTest(utc=utc, tags=tags):
                self.repo = self.root / f"recipe-{index}"
                self.repo.mkdir()
                self.git("init", "--quiet")
                self.commit()
                self.add_tags(*tags)
                reference = subprocess.run(
                    ["bash", "-c", USAGE_SYNCER_RECIPES], cwd=self.repo,
                    env=self.env | {"TEST_UTC_YEAR_MONTH": utc},
                    capture_output=True, text=True, check=True,
                )
                previous, version = reference.stdout.splitlines()
                previous = "v" + previous if previous != "0.0.0" else previous
                self.assert_version(version, previous, utc=utc)

    def test_optional_tag_creation_is_local(self):
        self.assert_version("2026.9.0", "0.0.0", VERSION_TAG="true")
        self.assertEqual(self.git("tag", "--list"), "v2026.9.0")
        self.assertEqual(self.git("rev-parse", "v2026.9.0"), self.git("rev-parse", "HEAD"))

    def test_tag_creation_never_overwrites_existing_tag(self):
        self.add_tags("v2026.9.0", "v2027.1.0")
        original = self.git("rev-parse", "v2026.9.0")
        self.commit()
        self.assertNotEqual(self.git("rev-parse", "HEAD"), original)
        result, output = self.run_version(VERSION_TAG="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, "")
        self.assertEqual(self.git("rev-parse", "v2026.9.0"), original)

    def test_failed_tag_listing_is_fatal_even_with_partial_output(self):
        self.write_stub("git", f"""#!/bin/sh
if [ "$#" -eq 2 ] && [ "$1" = tag ] && [ "$2" = --list ]; then
    printf '%s\\n' v2026.9.8
    printf '%s\\n' 'Synthetic tag listing failure' >&2
    exit 23
fi
exec {shlex.quote(GIT)} "$@"
""")
        result, output = self.run_version(VERSION_TAG="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, "")
        self.assertEqual(self.git("tag", "--list"), "")

    def test_invalid_formats_fail_without_outputs_or_tags(self):
        for output_format in (
            "", "{{.Unknown}}", "{{.Major", "bad}}", "{{.Major}}\nunsafe=value",
            "{{.Major}}\runsafe=value",
        ):
            with self.subTest(output_format=output_format):
                result, output = self.run_version(
                    VERSION_OUTPUT_FORMAT=output_format, VERSION_TAG="true",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, "")
                self.assertEqual(self.git("tag", "--list"), "")

    def test_invalid_tag_booleans_fail_without_outputs_or_tags(self):
        for tag in ("", "TRUE", "yes", "1"):
            with self.subTest(tag=tag):
                result, output = self.run_version(VERSION_TAG=tag)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, "")
                self.assertEqual(self.git("tag", "--list"), "")


if __name__ == "__main__":
    unittest.main()
