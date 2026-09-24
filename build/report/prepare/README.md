# Build Report Prepare

Validates Build workflow inputs and prepares pre/post command configurations,
display-name matrices, and report artifact selection. Call it once in Prepare,
before checkout. It needs Python 3.10 or newer and no repository checkout,
network access, or token permissions.

The reusable [Build workflow](../../../.github/workflows/README.md#build) calls
it with its typed inputs, including workflow defaults:

```yaml
- name: Prepare build inputs
  id: prepare_report
  uses: $/build/report/prepare
  with:
    build-inputs: ${{ toJSON(inputs) }}
```

This internal reference follows the workflow commit. External callers must use
`getdevopspro/github-actions/build/report/prepare` at a release containing it.
Pass boolean and numeric inputs as JSON booleans and numbers.

`pre-step-matrix` and `post-step-matrix` contain enabled command configurations.
Their `*-step-names` outputs preserve the same order, including duplicate names.
Empty phases return `[]`. Configuration values retain the string representation
expected by command jobs, including `true`/`false` flags and retention days.

`artifacts` lists the selected report artifacts, one per line; `artifact-sections`
maps them to producer IDs and configured titles. Reporting still requires
`build-report-enabled: true`. The [Publish action](../publish/README.md) consumes
these outputs after the producing jobs finish.

Invalid artifact or enabled-baseline configuration fails before any outputs are
written, including when reporting is disabled. Preparation reads inputs only;
the producing jobs create result files, and publishing checks their contents.

Run `make test-build-steps` and `make test-report` for offline preparation tests.
