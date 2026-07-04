# Reusable Workflows

These private reusable workflows are intended to be called with `workflow_call` from Clean-Botix OptimusClean repositories or from another workflow in this repository. Use stable versioned references when calling them.

This catalog documents the reusable workflows that exist so far. The repository is also the general home for future custom reusable OptimusClean workflow patterns.

`release.self.yml` is intentionally omitted from this catalog because it is this repository's self-release workflow.

## All Green

File: `all-green.yml`

Wraps the `all-green` composite action as a reusable workflow. Use it when a repository wants one final required check that confirms all other required PR checks have passed.

```yaml
jobs:
  all-green:
    uses: clean-botix/github-actions/.github/workflows/all-green.yml@v2.5.1
```

## Build

File: `build.yml`

Calculates a build version, optionally updates version files, runs configurable pre/post commands, builds Docker images with Buildx Bake, and can publish multi-platform images to a registry. Pull request image SHA tags use the PR head commit rather than GitHub's synthetic merge commit.

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

Set `docker-version` or `compose-version` to install a specific Docker CE or Docker Compose release before the Bake prepare and build actions run. Leave them empty to use the runner defaults.

Pre and post command jobs use those same versions by default. Set `pre-docker-version`, `pre-compose-version`, `post-docker-version`, or `post-compose-version` to override them for pre or post jobs.

## Go Lint

File: `golangci-lint.yml`

Runs GolangCI-Lint with a pinned Go setup. Use it for Go repositories that want a shared lint job without maintaining the boilerplate in each repository.

```yaml
jobs:
  lint:
    uses: clean-botix/github-actions/.github/workflows/golangci-lint.yml@v2.5.1
```

## Create Pull Request

File: `pr-create.yml`

Checks out a target repository, optionally installs `just`, runs a caller-provided command, and opens or updates a pull request with the resulting changes.

```yaml
jobs:
  sync:
    uses: clean-botix/github-actions/.github/workflows/pr-create.yml@v2.5.1
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

```yaml
jobs:
  release:
    uses: clean-botix/github-actions/.github/workflows/release.yml@v2.5.1
    secrets:
      checkout-token: ${{ secrets.REPO_TOKEN }}
    with:
      version-makefile: Makefile
      git-add-files: Makefile
      changelog-enabled: true
```

## Notify Slack

File: `notify-slack.yml`

Sends a Slack notification for either an OptimusClean pull request build or a release build. The caller selects `notification-type: pr` or `notification-type: release`, passes the upstream job status, and provides the Slack incoming webhook as a secret.

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

## Robot Test Check

File: `test-robot-check.yml`

Checks OptimusClean pull request labels and fails when robot testing is required but the matching done label is missing. It wraps the shared `clean-botix/github-actions/test/label/check` action with OptimusClean robot-test defaults.

```yaml
jobs:
  robot-test-check:
    uses: clean-botix/github-actions/.github/workflows/test-robot-check.yml@v2.5.1
    secrets:
      token: ${{ secrets.GITHUB_TOKEN }}
```

## Robot Test Label

File: `test-robot-label.yml`

Handles robot-test label events. When the done label is added, it posts confirmation through the shared label action and reruns the configured pull request workflow job so branch protection can re-evaluate the robot-test check.

```yaml
jobs:
  robot-test-label:
    uses: clean-botix/github-actions/.github/workflows/test-robot-label.yml@v2.5.1
    secrets:
      token: ${{ secrets.GITHUB_TOKEN }}
```

## Remove Robot Test

File: `test-robot-remove.yml`

Removes the robot-test done label when new commits are pushed to a pull request, ensuring robot testing is repeated after the PR content changes.

```yaml
jobs:
  robot-test-remove:
    uses: clean-botix/github-actions/.github/workflows/test-robot-remove.yml@v2.5.1
    secrets:
      token: ${{ secrets.GITHUB_TOKEN }}
```
