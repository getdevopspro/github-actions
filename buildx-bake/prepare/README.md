# Buildx Bake Prepare

Generates a Docker Buildx Bake platform matrix and stores Docker metadata for later jobs.

Use this action at the start of a split multi-platform image build. Later build jobs can consume the matrix output and download the uploaded `bake-meta` artifact.

Set `docker-version` or `compose-version` to install a specific Docker CE or Docker Compose release before the Bake matrix is generated. Leave them empty to use the runner defaults.

```yaml
steps:
  - uses: actions/checkout@v6
  - id: prepare
    uses: clean-botix/github-actions/buildx-bake/prepare@v3.1.1
    with:
      bake-target: build
      registry-image: ghcr.io/example/project
      meta-tags: type=sha
```
