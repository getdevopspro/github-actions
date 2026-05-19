# Test Label Check

Fails a pull request when a test-needed label is present but the matching test-done label is missing.

Use this action as a required PR check for workflows where manual or external validation must be confirmed with labels before merge.

```yaml
steps:
  - uses: getdevopspro/github-actions/test/label/check@v8.3.7
    with:
      label-needed: test-needed
      label-done: test-done
      test-name: Robot
```
