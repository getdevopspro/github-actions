# Release Git Push

Commits release changes, creates the release tag, and pushes both to the repository.

Use this action near the end of a release workflow after version files or changelog files have been updated. It can also create and push a tag when there are no file changes to commit. The tag is `version-tag-prefix` (default `v`) followed by `version`; use the same prefix for the version calculation, the changelog and the GitHub release. In the Release workflow, `version-tag-prefix` sets it for every step except the changelog, which uses `changelog-version-prefix`.

```yaml
steps:
  - uses: getdevopspro/github-actions/release/git-push@v12.0.2
    with:
      version: 1.2.3
      git-add-files: CHANGELOG.md Makefile
```
