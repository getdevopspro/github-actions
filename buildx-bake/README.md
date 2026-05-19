# Buildx Bake

Builds container images with Docker Buildx Bake in a single composite action.

Use this action when one workflow job should set up QEMU and Buildx, generate Docker metadata, log in to a registry, and run `docker/bake-action` with caller-provided tags, labels, targets, and cache settings.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: getdevopspro/github-actions/buildx-bake@v8.3.7
    with:
      meta-tags: type=sha
      registry-password: ${{ secrets.GITHUB_TOKEN }}
```
