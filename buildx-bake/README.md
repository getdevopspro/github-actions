# Buildx Bake

Builds container images with Docker Buildx Bake in a single composite action.

Use this action when one workflow job should set up QEMU and Buildx, generate Docker metadata, log in to a registry, and run `docker/bake-action` with caller-provided tags, labels, targets, and cache settings.

Set `docker-version` or `compose-version` to install a specific Docker CE or Docker Compose release before any Bake command runs. Leave them empty to use the runner defaults.

The action runs `docker/bake-action` with `source: .`, so Bake uses the checked-out workspace instead of refetching the repository through Docker's default Git context. Repositories that need Git LFS files should hydrate them during checkout.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: clean-botix/github-actions/buildx-bake@v3.1.1
    with:
      meta-tags: type=sha
      registry-password: ${{ secrets.GITHUB_TOKEN }}
```
