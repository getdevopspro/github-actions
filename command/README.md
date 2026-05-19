# Command

Runs a caller-provided command and optionally uploads files as a workflow artifact.

Use this action for reusable workflow hooks where callers need to provide a check, lint, build, or packaging command without repeating artifact upload boilerplate.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: getdevopspro/github-actions/command@v8.3.7
    with:
      command: make test
      artifact-name: test-output
      artifact-path: reports/
```
