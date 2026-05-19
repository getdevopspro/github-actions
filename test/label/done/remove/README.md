# Remove Test Done Label

Removes the test-done label when new commits are pushed to a pull request.

Use this action on `pull_request` synchronize events so manual or external test confirmation is reset whenever the PR contents change.

```yaml
steps:
  - uses: getdevopspro/github-actions/test/label/done/remove@v8.3.7
    with:
      label-needed: test-needed
      label-done: test-done
      test-name: Robot
```
