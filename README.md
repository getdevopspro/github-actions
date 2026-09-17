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
- [Release Version (SemVer)](release/version/semver/README.md) - resolves previous and next semantic versions.
- [Release Version (CalVer)](release/version/calver/README.md) - calculates UTC calendar versions from Git release tags.
- [Test Label Check](test/label/check/README.md) - enforces required manual test labels.
- [Test Done Label Added](test/label/done/added/README.md) - posts confirmation when a test-done label is present.
- [Test Done Label Remove](test/label/done/remove/README.md) - removes test-done when new commits require retesting.
- [Version File](version-file/README.md) - writes a version into common project files.

## Common Entry Points

Use versioned references when consuming this repository from Clean-Botix OptimusClean repositories.

The Build and Release workflows accept `version-strategy: semver` (default) or `calver`. CalVer follows the `usage-syncer/justfile` UTC `YYYY.M.PATCH` release calculation used as the reference for `optimusclean-dev`; see the [CalVer action](release/version/calver/README.md) for tag selection and output formatting.

The former `release/version` composite action moved to `release/version/semver`. Direct action callers must use the new path when upgrading to a release containing this change. In both the action and reusable workflows, rename `version-previous` to `version-semver-previous` and `version-next` to `version-semver-next`; the old input names are no longer accepted. Reusable workflow paths and SemVer defaults are unchanged. Strategy-specific inputs use `version-semver-` or `version-calver-` prefixes, while settings shared by both strategies retain their generic names.

```yaml
jobs:
  build:
    uses: clean-botix/github-actions/.github/workflows/build.yml@v4.0.2
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
    uses: clean-botix/github-actions/.github/workflows/notify-slack.yml@v4.0.2
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
  - uses: clean-botix/github-actions/all-green@v4.0.2
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

Run `make test-version` for local version-calculation regression tests. They require Python 3, Bash, Git, and GNU `sort`, and use temporary repositories without contacting external services.

Run `make test-changelog` for changelog initialization and release-note regression tests. These also require `git-cliff` (tested with 2.14.1); set `GIT_CLIFF_BIN` to use a specific binary. Tests use temporary repositories and disable network access.

For workflow lint, actionlint currently [does not recognize GitHub's `$/` references](https://github.com/rhysd/actionlint/issues/711). Until supported, use `actionlint -ignore 'specifying action "\$/release/version/(semver|calver)" in invalid format because ref is missing'` and verify those two action paths locally.

The `Build cache` PR check calls the checked-out Bake composites with a small two-target fixture on native AMD64 and ARM64 runners. It checks separate target/platform scopes, caller overrides, two warm imports on fresh builders, and source/dependency invalidation after all cold exports complete. It publishes only Actions cache entries and temporary test artifacts. Per-run cache prefixes prevent previous PR runs from warming the cold comparison. Measurements appear in job summaries and the `cache-measurements-*` artifacts; these synthetic timings are not consumer build benchmarks.

The cache fixture also checks mount archives across three fresh builders: create data, restore and update it as a non-root user, then restore the updated data. Layer caching is disabled for these checks. Run `python3 -B -m unittest discover -s tests -p 'test_build_cache_config.py' -v` for the offline configuration checks.

Native fixture jobs exercise automatic QEMU skipping; ARM64-on-AMD64 and native-output/foreign-stage jobs verify automatic and forced emulation. The offline configuration checks cover explicit QEMU modes and platform aliases.
