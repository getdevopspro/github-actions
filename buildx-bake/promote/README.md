# Buildx Bake Promote

Promotes existing image manifests to release tags.

Use this action when a build has already produced immutable manifest digests and a release workflow needs to add semantic tags such as `1.2.3`, `1.2`, `1`, and `latest`.

```yaml
steps:
  - uses: clean-botix/github-actions/buildx-bake/promote@v3.1.0
    with:
      version: 1.2.3
      image-digests: ${{ needs.build.outputs.image-digests }}
      registry-password: ${{ secrets.GITHUB_TOKEN }}
```
