# Notify Slack - Pull Request

Posts a Slack notification for an OptimusClean pull request build result.

Use this action when a Clean-Botix OptimusClean PR workflow needs to report build status to Slack with repository, author, pull request, commit, workflow run, and optional artifact link context. The Slack webhook URL must be supplied from a secret.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: clean-botix/github-actions/notify/slack/pr@v4.0.0
    with:
      job-status: ${{ job.status }}
      slack-webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
      artifact-link-name: Build Report
      artifact-link-url: ${{ steps.report.outputs.url }}
```
