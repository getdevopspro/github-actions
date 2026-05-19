# Buildx Bake Build

Builds and pushes one platform image by digest, then uploads the digest metadata.

Use this action inside a matrix job after `buildx-bake/prepare`. It downloads the shared metadata artifact, builds the requested `matrix.platform`, pushes by digest, and uploads a per-platform digest artifact for manifest merging.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: getdevopspro/github-actions/buildx-bake/build@v8.3.7
    with:
      registry-password: ${{ secrets.GITHUB_TOKEN }}
      registry-image: ghcr.io/example/project
```
