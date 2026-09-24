# GitHub Actions

Reusable GitHub Actions, workflows, and CI/CD helpers for public use.

This repository centralizes common pull-request, build, release, and testing automation so projects can reference parameterized workflows or composite actions instead of copying the same YAML and shell logic into every repository.

The actions are maintained for GetDevOpsPro projects, but they are intentionally generic enough for other GitHub repositories to reuse when the workflow patterns fit.

## What Is Included

- Reusable workflows in `.github/workflows/` for pull-request creation, build pipelines, release promotion, Go linting, and all-green checks.
- Composite actions for Docker Buildx Bake image builds, multi-architecture manifest publishing, and image tag promotion.
- Release helpers for version calculation, changelog generation, version-file updates, git tagging, and GitHub release updates.
- Pull request and test-label helpers for rerunning jobs and enforcing manual test confirmation labels.
- A generic command runner that can optionally upload command output as an artifact.

## Reusable Workflows

See [.github/workflows/README.md](.github/workflows/README.md) for the reusable workflow catalog.

- [All Green](.github/workflows/README.md#all-green) - wraps the all-green check as a reusable workflow.
- [Build](.github/workflows/README.md#build) - builds and optionally publishes Docker Buildx Bake images.
- [Go Lint](.github/workflows/README.md#go-lint) - runs GolangCI-Lint with a pinned Go toolchain.
- [Create Pull Request](.github/workflows/README.md#create-pull-request) - checks out a target repository, runs a command, and opens or updates a PR.
- [Release](.github/workflows/README.md#release) - calculates a version, updates version files, optionally promotes images, generates a changelog, tags, and publishes a GitHub release.

## Composite Actions

- [All Green](all-green/README.md) - checks that required PR checks have passed.
- [Build Baseline](build/baseline/README.md) - retrieves reference artifacts and commit/run metadata for repository-owned comparisons.
- [Build Report](build/report/README.md) - combines test, lint, and coverage artifacts into an HTML report and job summary, grouped by the producing pre/post steps with fields supplied by artifact content.
- [Buildx Bake](buildx-bake/README.md) - single-job Docker Buildx Bake image build.
- [Buildx Bake Prepare](buildx-bake/prepare/README.md) - creates a platform matrix and Docker metadata artifact.
- [Buildx Bake Build](buildx-bake/build/README.md) - builds and pushes per-platform image digests.
- [Buildx Bake Merge](buildx-bake/merge/README.md) - merges per-platform digests into manifest lists.
- [Buildx Bake Promote](buildx-bake/promote/README.md) - promotes existing image manifests to release tags.
- [Command](command/README.md) - runs a command and optionally uploads artifacts.
- [PR Job Rerun](pr/job-rerun/README.md) - reruns jobs for the latest completed PR workflow run.
- [Release Changelog](release/changelog/README.md) - generates and stages a git-cliff changelog.
- [Release Git Push](release/git-push/README.md) - commits release changes, tags, and pushes.
- [Release Update](release/update/README.md) - creates or updates a GitHub release.
- [Release Version (SemVer)](release/version/semver/README.md) - resolves previous and next semantic versions.
- [Release Version (CalVer)](release/version/calver/README.md) - calculates UTC calendar versions from Git release tags.
- [Test Label Check](test/label/check/README.md) - enforces required manual test labels.
- [Test Done Label Added](test/label/done/added/README.md) - posts confirmation when a test-done label is present.
- [Test Done Label Remove](test/label/done/remove/README.md) - removes test-done when new commits require retesting.
- [Version File](version-file/README.md) - writes a version into common project files.

## Build report migration

When upgrading to a release containing this change, replace direct `build-report`
action references with `build/report`. The old `baseline-artifact` and
`baseline-workflow` action inputs, and their `build-report-` workflow equivalents,
are removed. Existing pinned consumers keep their current behavior until upgraded.

In the reusable Build workflow, set `baseline-enabled: true` and
`baseline-artifact` to retrieve a reference once for pre/post commands. Lookup is
off by default, independent of reporting and coverage. Commands receive
`BASELINE_METADATA` and `BASELINE_PATH`; repository scripts compute comparisons
and include `coverage_comparison` in their JSON. `build/report` renders those
values. Custom workflows can call `build/baseline` directly before their producer.
The caller needs `actions: read` only when baseline retrieval is enabled;
PR comments need `pull-requests: write` only when enabled. Prepare retrieves and
shares enabled baselines in the same job. It inherits caller permissions even
when lookup is disabled. Command and image jobs retain their permissions.
See the [workflow inputs](.github/workflows/README.md#baselines).
See the [baseline example](build/baseline/README.md#usage) and
[comparison contract](build/report/README.md#coverage-comparisons).

## Common Entry Points

Use versioned references when consuming this repository from another repo:

The Build and Release workflows accept `version-strategy: semver` (default) or `calver`. CalVer follows the `usage-syncer/justfile` UTC `YYYY.M.PATCH` release calculation used as the reference for `optimusclean-dev`; see the [CalVer action](release/version/calver/README.md) for tag selection and output formatting.

The former `release/version` composite action moved to `release/version/semver`. Direct action callers must use the new path when upgrading to a release containing this change. In both the action and reusable workflows, rename `version-previous` to `version-semver-previous` and `version-next` to `version-semver-next`; the old input names are no longer accepted. Reusable workflow paths and SemVer defaults are unchanged. Strategy-specific inputs use `version-semver-` or `version-calver-` prefixes, while settings shared by both strategies retain their generic names.

```yaml
jobs:
  build:
    uses: getdevopspro/github-actions/.github/workflows/build.yml@v10.0.2
    secrets:
      registry-password: ${{ secrets.GITHUB_TOKEN }}
    with:
      bake-file: docker-bake.hcl
      bake-target: build
```

Composite actions can also be used directly:

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: getdevopspro/github-actions/all-green@v10.0.2
```

## Directory Map

- `.github/workflows/` - reusable workflow definitions and their catalog README.
- `build/` - baseline artifact retrieval and report collection/rendering with optional PR comments.
- `buildx-bake/` - Docker Buildx Bake actions for prepare, build, merge, promote, and single-job build flows.
- `release/` - release versioning, changelog, git push, and GitHub release update actions.
- `pr/` - pull request workflow helpers, including job reruns.
- `test/label/` - test-required and test-done label automation.
- `command/` - run a command and optionally upload artifacts.
- `version-file/` - update version values in common project files.
- `all-green/` - check that required pull-request checks have passed.

## Maintenance

The repository publishes versioned semantic version tags. Update consumers to a stable tag instead of a moving branch. Internal calls use `$/...` to follow the owning workflow’s commit. The `Makefile` contains the release helpers for updating versioned consumer examples in the root README and tagging releases.

Keep new actions small, parameterized, and reusable. Prefer wrapping well-maintained upstream actions when they cover the need; add custom composite logic here when a shared workflow needs behavior that should stay consistent across repositories.

Run `make test-version` for local version-calculation regression tests. They require Python 3, Bash, Git, and GNU `sort`, and use temporary repositories without contacting external services.

Run `make test-changelog` for changelog initialization and release-note regression tests. These also require `git-cliff` (tested with 2.14.1); set `GIT_CLIFF_BIN` to use a specific binary. Tests use temporary repositories and disable network access.

Run `make test-report` for offline report aggregation and publishing tests. These require Python 3.10 or newer and Node.js with `node:test` support; no GitHub API calls are made.

Run `make test-build-steps` for pre/post matrix naming and configuration tests. These require Python 3.10 or newer and run offline.

For workflow lint, actionlint currently [does not recognize GitHub's `$/` references](https://github.com/rhysd/actionlint/issues/711). Lint a temporary copy with `uses: $/` rewritten to `uses: ./`, preserving the repository layout so local action paths and reusable-workflow inputs are checked. Keep the committed references as `$/`.

The `Build cache` PR check calls the Bake composites from the workflow’s commit with a small two-target fixture on native AMD64 and ARM64 runners. It checks separate target/platform scopes, caller overrides, two warm imports on fresh builders, and source/dependency invalidation after all cold exports complete. It publishes only Actions cache entries and temporary test artifacts. Per-run cache prefixes prevent previous PR runs from warming the cold comparison. Measurements appear in job summaries and the `cache-measurements-*` artifacts; these synthetic timings are not consumer build benchmarks.

The cache fixture also checks mount archives across three fresh builders: create data, restore and update it as a non-root user, then restore the updated data. Layer caching is disabled for these checks. Run `python3 -B -m unittest discover -s tests -p 'test_build_cache_config.py' -v` for the offline configuration checks.

Native fixture jobs exercise automatic QEMU skipping; ARM64-on-AMD64 and native-output/foreign-stage jobs verify automatic and forced emulation. The offline configuration checks cover explicit QEMU modes and platform aliases.
