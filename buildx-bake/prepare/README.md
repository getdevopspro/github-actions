# Buildx Bake Prepare

Generates a Docker Buildx Bake platform matrix and stores Docker metadata for later jobs.

Use this action at the start of a split multi-platform image build. Later build jobs can consume the matrix output and download the uploaded `bake-meta` artifact.

```yaml
steps:
  - uses: actions/checkout@v6
  - id: prepare
    uses: getdevopspro/github-actions/buildx-bake/prepare@v8.3.7
    with:
      bake-target: build
      registry-image: ghcr.io/example/project
      meta-tags: type=sha
```
