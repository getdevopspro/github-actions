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
- [Release Version](release/version/README.md) - resolves previous and next semantic versions.
- [Test Label Check](test/label/check/README.md) - enforces required manual test labels.
- [Test Done Label Added](test/label/done/added/README.md) - posts confirmation when a test-done label is present.
- [Test Done Label Remove](test/label/done/remove/README.md) - removes test-done when new commits require retesting.
- [Version File](version-file/README.md) - writes a version into common project files.

## Common Entry Points

Use versioned references when consuming this repository from another repo:

```yaml
jobs:
  build:
    uses: getdevopspro/github-actions/.github/workflows/build.yml@v8.3.10
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
  - uses: getdevopspro/github-actions/all-green@v8.3.10
```

## Directory Map

- `.github/workflows/` - reusable workflow definitions and their catalog README.
- `buildx-bake/` - Docker Buildx Bake actions for prepare, build, merge, promote, and single-job build flows.
- `release/` - release versioning, changelog, git push, and GitHub release update actions.
- `pr/` - pull request workflow helpers, including job reruns.
- `test/label/` - test-required and test-done label automation.
- `command/` - run a command and optionally upload artifacts.
- `version-file/` - update version values in common project files.
- `all-green/` - check that required pull-request checks have passed.

## Maintenance

The repository publishes versioned semantic version tags. Update consumers to a stable tag instead of a moving branch. The `Makefile` contains the local release helpers used to update workflow references and tag new releases.

Keep new actions small, parameterized, and reusable. Prefer wrapping well-maintained upstream actions when they cover the need; add custom composite logic here when a shared workflow needs behavior that should stay consistent across repositories.
