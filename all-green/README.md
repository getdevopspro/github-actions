# All Green

Checks that all required pull-request checks have passed.

Use this action as a final PR gate after the repository has configured its required checks. It wraps `wechuli/allcheckspassed` with polling disabled, so it reports the current state instead of waiting: a check that has not completed (queued, waiting or running) fails the gate, and a check that has not been created yet is not seen. By default it evaluates every check on the commit except the advisory `copilot-pull-request-reviewer` check, because a Copilot review still in progress would otherwise fail the gate.

Inputs take comma-separated JavaScript regexes, unanchored and case-sensitive; use `^...$` for exact names. Patterns cannot contain commas, and a value starting with `[` or `{` is read as allcheckspassed's JSON form, so start such a pattern with `^`:

- `checks-include`: evaluate only matching checks. Empty or `-1` evaluates every check; any other value, even whitespace, makes `checks-exclude` ignored.
- `checks-exclude`: ignore matching checks. Set `-1` to ignore none.
- `fail-on-missing-checks`: fail when a `checks-include` pattern matches no check. Enable it with `checks-include`, since a check that has not been created yet would otherwise pass with only a warning.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: getdevopspro/github-actions/all-green@v13.0.0
```

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: getdevopspro/github-actions/all-green@v13.0.0
    with:
      checks-include: '^Lint$,^Unit Tests$'
      fail-on-missing-checks: true
```
