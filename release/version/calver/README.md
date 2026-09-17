# Release Version (CalVer)

Calculates the next calendar release version from the checked-out repository's Git release tags. Use it for calendar-based releases in the reusable Build and Release workflows or directly before version-file updates, changelog generation, and tagging.

```yaml
permissions:
  contents: read

steps:
  - uses: actions/checkout@v6
    with:
      fetch-depth: 0
  - id: version
    uses: clean-botix/github-actions/release/version/calver@v5.0.0
```

The calculation follows the `version` and `next-version` recipes in `usage-syncer/justfile`, which are the reference for the `optimusclean-dev` CalVer convention:

- Read the year and month in UTC and emit `YYYY.M.PATCH`, without leading zeroes in the month or patch.
- Select tags matching the literal `version-tag-prefix` followed by a digit (default `v[0-9]*`), strip the prefix, and take the latest using `sort -V`. Set the prefix to `''` for unprefixed release tags.
- If that release belongs to the current UTC year and month, increment its patch. Otherwise, start at `0`.
- Keep release candidates in a separate tag namespace, as in the justfile: `2026.8.8-rc1` has no `v` prefix and does not affect release calculation. An existing SemVer release such as `v3.1.1` can be the previous release when switching to CalVer; the first calendar version starts at patch `0`.

For example, the latest tag `v2026.8.7` produces `2026.8.8` in August 2026 and `2026.9.0` in September. A repository with no matching release tags starts at patch `0`. The `previous-version` output is the selected tag including its prefix, or `0.0.0` for an initial release, so it can be passed to the changelog action. Tag-list failures stop the action, and a current-month tag with a nonnumeric patch is rejected before arithmetic.

`version-output-format` supports the three literal fields `{{.Major}}` (year), `{{.Minor}}` (month), and `{{.Patch}}` (patch), plus fixed text such as `-build`. It does not evaluate Go template expressions. The reusable Build workflow keeps its default `-build` suffix; Release defaults to the plain version. SemVer-only `version-semver-previous` and `version-semver-next` workflow inputs do not affect CalVer. The current CalVer inputs are shared version settings; any CalVer-only inputs use the `version-calver-` prefix.

The runner needs Bash, Git, and GNU `sort` (`sort -V`); the workflows' default Ubuntu runners provide them. Checkout must include all relevant tags; this action does not fetch them. Calculation only reads Git and needs `contents: read`. `version-tag: 'true'` creates a local tag without overwriting or pushing an existing tag. A separate publishing step needs `contents: write`. Serialize release publication in the caller to avoid simultaneous releases calculating the same version.
