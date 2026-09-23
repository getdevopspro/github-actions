# Reusable Workflows

These private reusable workflows are intended to be called with `workflow_call` from Clean-Botix OptimusClean repositories or from another workflow in this repository. Use stable versioned references when calling them.

This catalog documents the reusable workflows that exist so far. The repository is also the general home for future custom reusable OptimusClean workflow patterns.

`release.self.yml` is intentionally omitted from this catalog because it is this repository's self-release workflow.

The Build and Release workflows use GitHub.com's `$/` references to load version and report actions from the same repository and commit as the reusable workflow. Callers continue to pin the reusable workflow to a versioned reference. Custom runners need [Actions runner 2.336.0 or newer](https://github.blog/changelog/2026-07-30-reference-same-repository-actions-with-self-repository-syntax/) for this syntax.

## All Green

File: `all-green.yml`

Wraps the `all-green` composite action as a reusable workflow. Use it when a repository wants one final required check that confirms all other required PR checks have passed.

```yaml
jobs:
  all-green:
    uses: clean-botix/github-actions/.github/workflows/all-green.yml@v5.0.1
```

## Build

File: `build.yml`

Calculates a build version, optionally updates version files, runs configurable pre/post commands, builds Docker images with Buildx Bake, and can publish multi-platform images to a registry. Pull request image SHA tags use the PR head commit rather than GitHub's synthetic merge commit.

`version-strategy` accepts `semver` (default) or `calver`. CalVer uses UTC `YYYY.M.PATCH` from Git release tags and preserves this workflow's default `-build` output suffix. `version-semver-previous` and `version-semver-next` apply only to SemVer; `version-output-format` and `version-tag-prefix` apply to both. Strategy-specific inputs use `version-semver-` or `version-calver-` prefixes; there are currently no CalVer-only inputs. Keep the default full-history checkout so all release tags are available. See the [CalVer action](../../release/version/calver/README.md) for the calculation and supported template fields.

```yaml
jobs:
  build:
    uses: clean-botix/github-actions/.github/workflows/build.yml@v5.0.1
    secrets:
      registry-password: ${{ secrets.GITHUB_TOKEN }}
    with:
      bake-file: docker-bake.hcl
      bake-target: build
```

`qemu` defaults to `auto`, skipping setup for a native Docker daemon/target match. Use the strings `'true'` or `'false'` to force or skip setup; force it for foreign execution stages in a native output image.

`cache-mounts` (default `true`), `cache-map` and `dockerfile` are forwarded to the build action. Disable mount persistence when it is unused; provide resolved maps for custom IDs or non-root mounts.

The prepare and image jobs both use `bake-file`. `cache-scope` (default `buildkit`) isolates layer caches by resolved target and platform. `bake-set` forwards newline-separated overrides to the image build; see [Buildx Bake Build](../../buildx-bake/build/README.md) for backend replacement and disabling the cache. Keep image outputs enabled when using this workflow because its merge job requires image digests.

Set `docker-version` or `compose-version` to install a specific Docker CE or Docker Compose release before the Bake prepare and build actions run. Leave them empty to use the runner defaults.

Pre and post command jobs use those same versions by default. Set `pre-docker-version`, `pre-compose-version`, `post-docker-version`, or `post-compose-version` to override them for pre or post jobs.

The Build workflow enables Git LFS downloads during checkout by default. Set `lfs: false` when the caller does not need Git LFS files.

When `lfs` is enabled, the workflow prints the tracked LFS files and fails before image build if any checked-out file is still an unresolved LFS pointer. Image builds use the uploaded source artifact as a local path context, so the hydrated checkout is what gets baked into the image.

### Build reports

The `Build Report` job calls the [Build Report action](../../build-report/README.md)
after pre/post commands, including failed commands, and exposes `build-report-url`.
Report sections follow each selected pre/post producer and its configured
`*-name`. Artifact `section_title` can override the title; artifact content
supplies the applicable test, lint, and coverage fields. Clean lint results
remain visible; absent fields are omitted. See the action's
[formats and schema](../../build-report/README.md#report-formats-and-sections)
for custom JSON producers and its [warning policy](../../build-report/README.md#results-and-logging).
It produces combined test, lint, and coverage results. It uses
`runner-report-default`, falling back to `runner-default`, and needs Python 3.10+.

`build-report-enabled` is a boolean and defaults to `false`. Set it to `true` to
report on configured pre/post artifacts, including `checks`, `lint`, `test`,
`test-unit`, `test-coverage`, `test-integration`, and `test-e2e`. Set
`build-report-artifacts` to a newline-separated subset of those artifact names
when other pre/post artifacts contain logs or binaries instead of report data.
Neither artifact configuration nor report options enable reporting by themselves.

Prepare passes each selected artifact's pre/post producer ID and `*-name` to the
report action for every available checks, lint, and test step. For example,
`post-test-name: System Test (post-steps)` names that producer's section for JSON
and native results alike. IDs stay stable when names change; pre and post sections
remain distinct. Tests, lint, and coverage in one artifact stay under its producer.
Commands still generate the result files; configuration never supplies results.

Prepare validates artifact configuration before checkout and image builds. For
every pre/post step that declares an artifact name or path, a nonempty command,
valid artifact name, and path are required, even when reporting is disabled.
Command-only steps need no artifact fields. When reporting is enabled, prepare
also requires at least one report artifact, rejects duplicate producer names and
collisions with source/report uploads, and verifies that explicit report names
refer to configured producers and selected step names are nonempty. Selecting a
subset does not bypass validation of other pre/post artifact configurations.

Both pre and post commands upload their configured artifacts, including after
command failures. Prepare checks configuration only; files and report contents
are checked after the producing jobs run.

Every selected artifact must contain supported results. Missing or invalid inputs
fail the report job after it publishes any available results. Publish each result
in one format to avoid counting raw XML and its JSON aggregate twice.

No additional reporting permissions are required when `build-report-enabled`
is `false` (the default), even if optional report inputs are set. When reporting
is enabled, HTML artifacts and job summaries also need no extra `GITHUB_TOKEN`
permissions. Optional features require these caller permissions:

| Caller permission | Required only when |
| --- | --- |
| `pull-requests: write` | `build-report-enabled: true` and `build-report-pr-comment: true`, on `pull_request` events |
| `actions: read` | `build-report-enabled: true` and `build-report-baseline-artifact` is set |

PR comments and coverage comparisons are disabled by default. Baselines come from
the latest successful default-branch run of `build-report-baseline-workflow`
(default `release.yml`). Existing build jobs retain their own `contents: read`
and `packages: write` permissions; reporting adds no access to those jobs.

Example caller enabling both optional features. This assumes an existing
`make coverage` target writes Cobertura XML to `build/coverage.xml`, and
`release.yml` uploads coverage under the same artifact name. Adopt a release
containing this feature before using the example; `v5.0.0` does not contain it.

```yaml
jobs:
  build:
    uses: clean-botix/github-actions/.github/workflows/build.yml@v5.0.1
    permissions:
      contents: read        # Existing Build requirement
      packages: write       # Existing Build requirement
      actions: read         # Enabled coverage baseline
      pull-requests: write  # Enabled PR report comment
    secrets:
      registry-password: ${{ secrets.GITHUB_TOKEN }}
    with:
      post-test-coverage-command: make coverage
      post-test-coverage-artifact-name: coverage-results
      post-test-coverage-artifact-path: build/coverage.xml
      build-report-enabled: true
      build-report-pr-comment: true
      build-report-baseline-artifact: coverage-results
```

Report inputs do not grant permissions; the report job inherits them from its
caller. Every intermediate reusable-workflow calling job must preserve the
required scopes, either by inheriting them or declaring them explicitly. Under
GitHub's [reusable workflow permission rules](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations),
a called workflow cannot restore scopes removed by a caller. Remove optional
scopes from the caller when those features are disabled; changing report inputs
does not change an explicit `permissions` block. Fork and repository policies
may restrict access further. Prepare validates artifact configuration, not live
token access.

When adopting a release containing this feature, remove any existing job that
uploads the same `build-report` artifact. Forward a wrapper workflow's report URL
from `jobs.build.outputs.build-report-url`. Existing JSON producers can keep their
local report-generation commands; repositories with JUnit XML can upload that XML
directly. Test commands that only print results need to export a supported report
and configure its artifact name/path before enabling reporting.

## Go Lint

File: `golangci-lint.yml`

Runs GolangCI-Lint with a pinned Go setup. Use it for Go repositories that want a shared lint job without maintaining the boilerplate in each repository.

```yaml
jobs:
  lint:
    uses: clean-botix/github-actions/.github/workflows/golangci-lint.yml@v5.0.1
```

## Create Pull Request

File: `pr-create.yml`

Checks out a target repository, optionally installs `just`, runs a caller-provided command, and opens or updates a pull request with the resulting changes.

```yaml
jobs:
  sync:
    uses: clean-botix/github-actions/.github/workflows/pr-create.yml@v5.0.1
    secrets:
      token: ${{ secrets.REPO_TOKEN }}
    with:
      repository: example/project
      command: make update
      title: Automated update
```

## Release

File: `release.yml`

Calculates the release version, updates supported version files, optionally downloads build artifacts, can promote container image manifests, optionally generates a changelog, pushes release commits and tags, and can create or update a GitHub release.

With changelog generation and prepend enabled, a missing changelog is initialized from the history reachable from `HEAD`. The workflow's `changelog` output and GitHub release body contain only the current release notes; historical sections are kept in the changelog file. See the [changelog action](../../release/changelog/README.md) for initial-release and range behavior.

`version-strategy` accepts `semver` (default) or `calver`. Both strategies feed the same version-file, image promotion, changelog, tag, and release steps. CalVer defaults to UTC `YYYY.M.PATCH`; `version-semver-previous` and `version-semver-next` are SemVer-only inputs. Keep `fetch-depth: 0` and `fetch-tags: true` for a complete tag history, or provide all tags when disabling checkout. Calculation reads repository contents; this workflow retains its existing `contents: write` and `packages: write` permissions for release and image publication.

```yaml
jobs:
  release:
    uses: clean-botix/github-actions/.github/workflows/release.yml@v5.0.1
    secrets:
      checkout-token: ${{ secrets.REPO_TOKEN }}
    with:
      version-makefile: Makefile
      git-add-files: Makefile
      changelog-enabled: true
```

To opt into CalVer, add `version-strategy: calver` to `with:` above. The same input selects CalVer in the Build workflow. Serialize publication in the calling workflow to prevent concurrent releases from choosing the same version.

## Notify Slack

File: `notify-slack.yml`

Sends a Slack notification for either an OptimusClean pull request build or a release build. The caller selects `notification-type: pr` or `notification-type: release`, passes the upstream job status, and provides the Slack incoming webhook as a secret.

```yaml
jobs:
  notify:
    uses: clean-botix/github-actions/.github/workflows/notify-slack.yml@v5.0.1
    secrets:
      slack-webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
    with:
      notification-type: pr
      job-status: ${{ needs.build.result }}
```

## Robot Test Check

File: `test-robot-check.yml`

Checks OptimusClean pull request labels and fails when robot testing is required but the matching done label is missing. It wraps the shared `clean-botix/github-actions/test/label/check` action with OptimusClean robot-test defaults.

```yaml
jobs:
  robot-test-check:
    uses: clean-botix/github-actions/.github/workflows/test-robot-check.yml@v5.0.1
    secrets:
      token: ${{ secrets.GITHUB_TOKEN }}
```

## Robot Test Label

File: `test-robot-label.yml`

Handles robot-test label events. When the done label is added, it posts confirmation through the shared label action and reruns the configured pull request workflow job so branch protection can re-evaluate the robot-test check.

```yaml
jobs:
  robot-test-label:
    uses: clean-botix/github-actions/.github/workflows/test-robot-label.yml@v5.0.1
    secrets:
      token: ${{ secrets.GITHUB_TOKEN }}
```

## Remove Robot Test

File: `test-robot-remove.yml`

Removes the robot-test done label when new commits are pushed to a pull request, ensuring robot testing is repeated after the PR content changes.

```yaml
jobs:
  robot-test-remove:
    uses: clean-botix/github-actions/.github/workflows/test-robot-remove.yml@v5.0.1
    secrets:
      token: ${{ secrets.GITHUB_TOKEN }}
```
