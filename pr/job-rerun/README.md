# PR Job Rerun

Reruns jobs from the latest completed workflow run for the current pull request SHA.

Use this action from a PR-triggered workflow when a label, comment, or manual dispatch should rerun a specific job, all failed jobs, or the whole workflow run without starting duplicate active runs.

```yaml
steps:
  - uses: getdevopspro/github-actions/pr/job-rerun@v8.3.7
    with:
      workflow-id: .github/workflows/pull-request.yml
      job-name: Integration Tests
```
