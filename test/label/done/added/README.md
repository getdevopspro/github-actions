# Test Done Label Added

Posts a confirmation comment when the test-done label is present on a pull request.

Use this action from label-related PR workflows to give reviewers a visible confirmation that manual or external testing has been marked complete.

```yaml
steps:
  - uses: getdevopspro/github-actions/test/label/done/added@v8.3.7
    with:
      label-done: test-done
      test-name: Robot
```
