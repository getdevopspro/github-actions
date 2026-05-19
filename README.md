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

## Common Entry Points

Use versioned references when consuming this repository from another repo:

```yaml
jobs:
  build:
    uses: getdevopspro/github-actions/.github/workflows/build.yml@v8.3.7
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
  - uses: getdevopspro/github-actions/all-green@v8.3.7
```

## Directory Map

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
