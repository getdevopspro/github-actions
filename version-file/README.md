# Version File

Writes a release version into common project files.

Use this action before committing a release when a workflow needs to update files such as `VERSION`, `galaxy.yml`, `Makefile`, `justfile`, `package.json`, `package-lock.json`, scripts, or Helm chart metadata.

Each supplied target runs in a separate named step; unset targets are skipped. Multiple targets can be updated in one action call. Existing text formats use Bash, and Galaxy metadata uses an inline Python step.

| Input | Update |
| --- | --- |
| `version-galaxy` | Update the collection's version scalar; see the requirements below. |
| `version-file` | Replace the entire file with the version and a newline; create it if missing. |
| `version-makefile` | Replace lines starting with `VERSION ` with `VERSION ?= <version>`. |
| `version-justfile` | Replace lines starting with `version ` with `version := "<version>"`. |
| `version-package` | Update lines containing `"version":`, preserving indentation and emitting a trailing comma. |
| `version-package-lock` | Update quoted version fields on lines 1–15; skip a missing lockfile. |
| `version-script` | Replace lines starting with `VERSION=`. |
| `version-chart` | Update `version:` in `charts/<input>/Chart.yaml` and `tag:` matches in its `values.yaml`. |

The text substitutions keep their existing matching rules, including nested matching JSON version lines. Files without a matching line remain unchanged. Missing files fail except for `version-file` creation and the optional package lockfile. Steps run in the order above and stop on failure.

```yaml
steps:
  - uses: getdevopspro/github-actions/version-file@v8.3.7
    with:
      version: 1.2.3
      version-makefile: Makefile
```

For an Ansible collection, use these inputs with a release containing `version-galaxy`:

```yaml
with:
  version: 2026.9.0
  version-galaxy: galaxy.yml
```

`version-galaxy` uses `shell: python3 {0}` and requires Python 3 with no additional packages. It updates one unindented, single-line `version` scalar at the top level, preserving other metadata, quotes, comments, spacing, and line endings. Missing files, missing or duplicate version fields, and unsupported scalar formats fail without changing the file.

Pass a SemVer-compatible value without a `v` prefix, such as `2026.9.0` or `2026.9.0-rc.1`; zero-padded core or numeric prerelease components are rejected. The plain `version-file` input replaces an entire file, so use `version-galaxy` for collection metadata instead. The action does not build or publish the collection.

Run `make test-version` for version calculation and the [version-file test suite](../tests/test_version_file.py), which covers every supported file format.
