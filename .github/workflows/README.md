# Reusable Workflows

These workflows are intended to be called with `workflow_call` from another repository or from another workflow in this repository. Use versioned references such as `@v8.3.7` when calling them from external repositories.

`release.self.yml` is intentionally omitted from this catalog because it is this repository's self-release workflow.

## All Green

File: `all-green.yml`

Wraps the `all-green` composite action as a reusable workflow. Use it when a repository wants one final required check that confirms all other required PR checks have passed.

```yaml
jobs:
  all-green:
    uses: getdevopspro/github-actions/.github/workflows/all-green.yml@v8.3.7
```

## Build

File: `build.yml`

Calculates a build version, optionally updates version files, runs configurable pre/post commands, builds Docker images with Buildx Bake, and can publish multi-platform images to a registry.

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

## Go Lint

File: `golangci-lint.yml`

Runs GolangCI-Lint with a pinned Go setup. Use it for Go repositories that want a shared lint job without maintaining the boilerplate in each repository.

```yaml
jobs:
  lint:
    uses: getdevopspro/github-actions/.github/workflows/golangci-lint.yml@v8.3.7
```

## Create Pull Request

File: `pr-create.yml`

Checks out a target repository, optionally installs `just`, runs a caller-provided command, and opens or updates a pull request with the resulting changes.

```yaml
jobs:
  sync:
    uses: getdevopspro/github-actions/.github/workflows/pr-create.yml@v8.3.7
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
    uses: getdevopspro/github-actions/.github/workflows/release.yml@v8.3.7
    secrets:
      checkout-token: ${{ secrets.REPO_TOKEN }}
    with:
      version-makefile: Makefile
      git-add-files: Makefile
      changelog-enabled: true
```
