# Buildx Bake Build

Builds and pushes one platform image by digest, then uploads the digest metadata.

Use this action inside a matrix job after `buildx-bake/prepare`. It downloads the shared metadata artifact, builds the requested `matrix.platform`, pushes by digest, and uploads a per-platform digest artifact for manifest merging.

Set `docker-version` or `compose-version` to install a specific Docker CE or Docker Compose release before disk cleanup and build setup. Leave them empty to use the runner defaults.

The action runs `docker/bake-action` with `source: .`, so Bake uses the downloaded source artifact or checked-out workspace instead of refetching the repository through Docker's default Git context. Repositories that need Git LFS files should hydrate them before this action runs.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: clean-botix/github-actions/buildx-bake/build@v4.0.2
    with:
      registry-password: ${{ secrets.GITHUB_TOKEN }}
      registry-image: ghcr.io/example/project
```

Layer caches use `type=gha,mode=max` with a separate scope for each resolved Bake target and platform: `<cache-scope>-<target>-<platform>`, for example `buildkit-api-linux-arm64`. The prefix defaults to `buildkit`; use a distinct `cache-scope` for independent builds of the same target in one repository. The first build after upgrading populates the new scopes. Export failures remain nonfatal.

`bake-set` accepts newline-separated overrides after the generated defaults. Ordinary argument overrides retain caching. To replace the backend, set both `*.cache-from` and `*.cache-to`; to disable it, set both to an empty value. Existing cache imports in the Bake file are merged with the default import according to Bake's file merge rules. Explicit `bake-set` cache values replace these file defaults.

```yaml
      cache-scope: service
      bake-set: |
        *.args.BUILD_MODE=release
        *.cache-from=
        *.cache-to=
```

The default output pushes by digest. An explicit `bake-set` output (for example `*.output=type=cacheonly`) replaces that default. Cache-only builds do not produce image digests for manifest merging.

Cache mounts persist by default. Set `cache-mounts: false` to skip archive restore/save and cache-dance entirely when the Dockerfile has no useful cache mounts. This does not disable the independent layer cache.

By default, cache-dance discovers mounts in `dockerfile` (default `Dockerfile`). For variable-based IDs or non-root ownership, supply a complete `cache-map` instead. Keys must be archive paths of the form `cache-mount/<name>`; values follow cache-dance's string target or mount-options object format. A nonempty map replaces discovery, so include every mount to persist. An empty JSON object still uses discovery; use `cache-mounts: false` to opt out.

```yaml
      dockerfile: container/Dockerfile
      cache-map: |
        {
          "cache-mount/compiler": {
            "target": "/home/builder/.cache/ccache",
            "id": "compiler-${TARGETARCH}",
            "uid": 1000,
            "gid": 1000,
            "sharing": "locked"
          }
        }
```

Match the Dockerfile's resolved `target`, `id`, ownership and sharing mode. Only the literal `${TARGETOS}`, `${TARGETARCH}` and `${TARGETVARIANT}` placeholders are expanded, using `matrix.platform`; resolve other variables in the caller. Bound compiler-cache size in the Dockerfile (for example, `ENV CCACHE_MAXSIZE=1G`) before persisting it.

Archive compatibility includes `cache-scope`, platform, Bake target, Dockerfile/Bake file contents and the resolved map. Each commit/run/attempt/job gets a new immutable archive, restored from the most recent compatible prefix. This allows source-only rebuilds to save updated compiler/dependency data. The new key namespace starts cold; old archives are left to normal cache eviction. Cache-dance extracts in its post step before the archive action saves and Buildx cleans up.
