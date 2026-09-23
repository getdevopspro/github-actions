# Release Changelog

Generates a release changelog with `git-cliff` and stages the output file.

Use this action in release workflows that need a changelog file, release notes, a step summary, and an optional artifact.

With `prepend: 'true'` (the default), release notes cover `previous-version..HEAD`. If the changelog file is missing, the action generates it separately from all history reachable from the resolved `HEAD` commit, retaining historical release sections. Existing changelogs keep their prior contents and receive only the new release entries. A dangling symlink is not treated as a missing file.

The `content` output, step summary, and uploaded artifact contain the current release notes, even when the changelog file is initialized with older history. The reusable Release workflow uses this `content` as the GitHub release body. The generated changelog file is staged for committing.

When `previous-version` is `0.0.0` and that ref does not exist, the action treats the release as the first release. It warns in the workflow log, includes the first commit by passing the resolved `HEAD` SHA to git-cliff, and disables prepend for that run. Its initial changelog and release notes cover the same history. Explicit `prepend: 'false'` otherwise retains the `previous-version..version` range and overwrites the changelog; both refs must exist.

Checkout must include the required history and tags. Configuration filters and additional git-cliff arguments still apply to both the changelog and the release notes.

```yaml
steps:
  - uses: actions/checkout@v6
    with:
      fetch-depth: 0
  - uses: clean-botix/github-actions/release/changelog@v5.0.1
    with:
      version: v1.2.3
      previous-version: v1.2.2
```
