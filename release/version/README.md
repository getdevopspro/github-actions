# Release Version

Calculates the next release version and exposes the previous version.

Use this action when a workflow needs shared version detection and semantic version calculation before updating files, tagging, building images, or generating a changelog.

```yaml
steps:
  - id: version
    uses: getdevopspro/github-actions/release/version@v8.3.7
    with:
      version-previous: auto
      version-next: auto
```
