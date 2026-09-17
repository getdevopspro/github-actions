# Buildx Bake Merge

Merges per-platform image digests into multi-platform manifest lists.

Use this action after all platform build jobs complete. It downloads the `bake-meta` and `digests-*` artifacts, creates manifest lists with `docker buildx imagetools`, and outputs the merged image digests.

```yaml
steps:
  - uses: clean-botix/github-actions/buildx-bake/merge@v5.0.0
    with:
      registry-password: ${{ secrets.GITHUB_TOKEN }}
```
