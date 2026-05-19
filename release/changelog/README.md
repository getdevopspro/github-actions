# Release Changelog

Generates a release changelog with `git-cliff` and stages the output file.

Use this action in release workflows that need a changelog file, a step summary, and an optional artifact generated from the commit range between the previous version and the new version.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: getdevopspro/github-actions/release/changelog@v8.3.7
    with:
      version: v1.2.3
      previous-version: v1.2.2
```
