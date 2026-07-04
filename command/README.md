# Command

Runs a caller-provided command and optionally uploads files as a workflow artifact.

Use this action for reusable workflow hooks where callers need to provide a check, lint, build, or packaging command without repeating artifact upload boilerplate.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: clean-botix/github-actions/command@v2.5.1
    with:
      command: make test
      artifact-name: test-output
      artifact-path: reports/
```
