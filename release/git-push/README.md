# Release Git Push

Commits release changes, creates the release tag, and pushes both to the repository.

Use this action near the end of a release workflow after version files or changelog files have been updated. It can also create and push a tag when there are no file changes to commit.

```yaml
steps:
  - uses: getdevopspro/github-actions/release/git-push@v8.3.7
    with:
      version: 1.2.3
      git-add-files: CHANGELOG.md Makefile
```
