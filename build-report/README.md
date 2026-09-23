# Build Report

Combines uploaded test, lint, and coverage results into one HTML artifact and a
GitHub job summary. Use it after the jobs that produce those results, including
when those jobs fail. It reads existing results without rebuilding or rerunning
tests. The runner needs Python 3.10 or newer; no consumer checkout is required.

## Usage

The shared [Build workflow](../.github/workflows/README.md#build) calls this action
when `build-report-enabled: true` is set; reporting is disabled by default.
Prepare validates all configured pre/post artifact uploads before checkout.
Other workflows can call the action directly:

```yaml
jobs:
  report:
    name: Build Report
    needs: tests
    if: ${{ !cancelled() }}
    runs-on: ubuntu-24.04
    permissions: {}
    steps:
      - uses: clean-botix/github-actions/build-report@v5.0.0
        with:
          artifact-names: |
            unit-test-results
            lint-results
```

This action is unreleased. Adopt a release containing it and update the example
reference before use; `v5.0.0` does not contain it.

`artifact-names` lists exact names from the current workflow run, one per line.
Each artifact must contain at least one supported report. Downloads stay separate
to avoid overwriting files with the same name. Both ordinary artifact uploads and
the `.tar` archives produced by the shared Command action are supported.

The action uploads `build_report.html` as the `build-report` artifact and returns
`artifact-url` and `artifact-id`. Override `artifact-name` for multiple independent
reports in one run. Failed tests or lint, missing reports, invalid report data, or
download errors fail the action after available results have been published.
Image-build failures remain the responsibility of the producing jobs.

## Report formats

- Build-report JSON with `suites`, `system_suites`, `lint_packages`, and
  `cov_packages` sections. Existing producers can keep this format.
- JUnit and Google Test XML. `system_tests.xml` populates the system-test section;
  other test XML populates the unit-test section.
- Ament lint `*.xunit.xml`, Ruff JSON, and Pyright JSON.
- Cobertura coverage XML, including reports with aggregate coverage only.

Upload each result once: including both its raw XML and an aggregated JSON copy
would count it twice. Coverage is informational; a decrease against the optional
baseline is displayed but does not fail the action.

## Optional publishing

Set `pr-comment: 'true'` to create or update the marked build-report comment on
pull requests. The calling job must grant `pull-requests: write`. Duplicate report
comments are removed when updating. Leave comments disabled for workflows with
read-only tokens.

Set `baseline-artifact` to compare coverage with that artifact from the latest
successful run of `baseline-workflow` (default `release.yml`) on the repository's
default branch. This requires `actions: read`. An absent, expired, or invalid
baseline omits the comparison without failing the current report.

The default token is `github.token`; `github-token` overrides it for those optional
operations. Current-run artifact downloads, HTML uploads, and the job summary
need no additional GitHub token permissions.

In the shared Build workflow, `build-report-enabled: false` skips this action and
requires no additional reporting permissions, even if optional report inputs are
set. With reporting enabled, `pull-requests: write` is needed only for
`build-report-pr-comment: true` on pull requests; `actions: read` is needed only
when `build-report-baseline-artifact` is set. The report job inherits caller
permissions. Every intermediate reusable-workflow calling job must preserve the
required scopes by inheriting or explicitly granting them; a called workflow
cannot restore scopes removed by a caller. See the [caller example](../.github/workflows/README.md#build-reports).

Run `make test-report` for offline artifact, parser, failure, and comment tests.
