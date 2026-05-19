# All Green

Checks that all required pull-request checks have passed.

Use this action as a final PR gate after the repository has configured its required checks. It wraps `wechuli/allcheckspassed` with polling disabled, so it reports the current state instead of waiting.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: getdevopspro/github-actions/all-green@v8.3.7
```
