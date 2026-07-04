# Clean-Botix GitHub Actions

Private custom reusable GitHub Actions, workflows, and CI/CD helpers for the Clean-Botix OptimusClean project.

This repository centralizes OptimusClean GitHub automation so Clean-Botix repositories can reuse parameterized workflows and composite actions instead of duplicating CI/CD YAML and scripts. It includes shared pull-request, build, release, testing, Slack notification, and robot-test automation patterns.

## What Is Included

- Reusable workflows in `.github/workflows/` for pull-request creation, build pipelines, release promotion, Go linting, all-green checks, Slack notifications, and robot-test label automation.
- Composite actions for Docker Buildx Bake image builds, multi-architecture manifest publishing, and image tag promotion.
- Release helpers for version calculation, changelog generation, version-file updates, git tagging, and GitHub release updates.
- Pull request and test-label helpers for rerunning jobs and enforcing manual test confirmation labels.
- Slack notification helpers for pull request and release workflow results.
- A generic command runner that can optionally upload command output as an artifact.

## Reusable Workflows

See [.github/workflows/README.md](.github/workflows/README.md) for the reusable workflow catalog.

- [All Green](.github/workflows/README.md#all-green) - wraps the all-green check as a reusable workflow.
- [Build](.github/workflows/README.md#build) - builds and optionally publishes Docker Buildx Bake images.
- [Go Lint](.github/workflows/README.md#go-lint) - runs GolangCI-Lint with a pinned Go toolchain.
- [Create Pull Request](.github/workflows/README.md#create-pull-request) - checks out a target repository, runs a command, and opens or updates a PR.
- [Release](.github/workflows/README.md#release) - calculates a version, updates version files, optionally promotes images, generates a changelog, tags, and publishes a GitHub release.
- [Notify Slack](.github/workflows/README.md#notify-slack) - sends pull request or release Slack notifications.
- [Robot Test Check](.github/workflows/README.md#robot-test-check) - fails when robot testing is required but not marked complete.
- [Robot Test Label](.github/workflows/README.md#robot-test-label) - reacts to robot-test labels and reruns the check workflow job.
- [Remove Robot Test](.github/workflows/README.md#remove-robot-test) - removes robot-test completion when new commits require retesting.

## Composite Actions

- [All Green](all-green/README.md) - checks that required PR checks have passed.
- [Buildx Bake](buildx-bake/README.md) - single-job Docker Buildx Bake image build.
- [Buildx Bake Prepare](buildx-bake/prepare/README.md) - creates a platform matrix and Docker metadata artifact.
- [Buildx Bake Build](buildx-bake/build/README.md) - builds and pushes per-platform image digests.
- [Buildx Bake Merge](buildx-bake/merge/README.md) - merges per-platform digests into manifest lists.
- [Buildx Bake Promote](buildx-bake/promote/README.md) - promotes existing image manifests to release tags.
- [Command](command/README.md) - runs a command and optionally uploads artifacts.
- [Notify Slack - Pull Request](notify/slack/pr/README.md) - posts a Slack message for pull request build results.
- [Notify Slack - Release](notify/slack/release/README.md) - posts a Slack message for release build results.
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

Use versioned references when consuming this repository from Clean-Botix OptimusClean repositories.

```yaml
jobs:
  build:
    uses: clean-botix/github-actions/.github/workflows/build.yml@v2.5.1
    secrets:
      registry-password: ${{ secrets.GITHUB_TOKEN }}
    with:
      bake-file: docker-bake.hcl
      bake-target: build
```

Slack notifications can be consumed through the reusable workflow:

```yaml
jobs:
  notify:
    uses: clean-botix/github-actions/.github/workflows/notify-slack.yml@v2.5.1
    secrets:
      slack-webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
    with:
      notification-type: pr
      job-status: ${{ needs.build.result }}
```

Composite actions can also be used directly:

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: clean-botix/github-actions/all-green@v2.5.1
```

## Directory Map

- `.github/workflows/` - reusable workflow definitions and their catalog README.
- `buildx-bake/` - Docker Buildx Bake actions for prepare, build, merge, promote, and single-job build flows.
- `release/` - release versioning, changelog, git push, and GitHub release update actions.
- `pr/` - pull request workflow helpers, including job reruns.
- `test/label/` - test-required and test-done label automation.
- `notify/slack/` - Slack notification actions for pull request and release workflows.
- `command/` - run a command and optionally upload artifacts.
- `version-file/` - update version values in common project files.
- `all-green/` - check that required pull-request checks have passed.

## Maintenance

The repository publishes versioned semantic version tags for internal consumers. Update Clean-Botix OptimusClean consumers to a stable tag instead of a moving branch. Run `make release-version VERSION=<version>` when bumping this repository so local `clean-botix/github-actions` references in workflows and README files stay aligned.

Keep new actions and workflows small, parameterized, and documented around OptimusClean project needs. Do not place webhook URLs, tokens, private repository identifiers, internal channel names, or operational secrets in examples or committed files.
