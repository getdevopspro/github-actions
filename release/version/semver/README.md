# Release Version (SemVer)

Calculates the next release version and exposes the previous version.

Use this action when a workflow needs shared version detection and semantic version calculation before updating files, tagging, building images, or generating a changelog.

```yaml
steps:
  - id: version
    uses: clean-botix/github-actions/release/version/semver@v5.0.1
    with:
      version-semver-previous: auto
      version-semver-next: auto
```

This action moved from `release/version` to `release/version/semver`. Update direct callers when adopting a release that includes the new path, and rename `version-previous` to `version-semver-previous` and `version-next` to `version-semver-next`. Outputs, defaults, and SemVer calculation are unchanged. The reusable Build and Release workflows use these same input names and default to this action through `version-strategy: semver`.
