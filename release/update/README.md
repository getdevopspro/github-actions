# Release Update

Creates or updates a GitHub release for an existing tag.

Use this action when release notes, artifacts, draft status, prerelease status, or latest-release status should be managed from a workflow.

```yaml
steps:
  - uses: clean-botix/github-actions/release/update@v2.5.1
    with:
      tag: v1.2.3
      body: ${{ steps.changelog.outputs.content }}
```
