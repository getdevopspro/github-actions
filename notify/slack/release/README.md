# Notify Slack - Release

Posts a Slack notification for an OptimusClean release build result.

Use this action when a Clean-Botix OptimusClean release workflow needs to report version, repository, author, branch, commit, workflow run, and optional artifact link context to Slack. The Slack webhook URL must be supplied from a secret.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: clean-botix/github-actions/notify/slack/release@v3.1.1
    with:
      job-status: ${{ job.status }}
      version: 1.2.3
      slack-webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
```
