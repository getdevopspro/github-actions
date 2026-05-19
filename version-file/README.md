# Version File

Writes a release version into common project files.

Use this action before committing a release when a workflow needs to update files such as `VERSION`, `Makefile`, `justfile`, `package.json`, `package-lock.json`, scripts, or Helm chart metadata.

```yaml
steps:
  - uses: getdevopspro/github-actions/version-file@v8.3.7
    with:
      version: 1.2.3
      version-makefile: Makefile
```
