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
      - uses: clean-botix/github-actions/build-report@v5.0.1
        with:
          artifact-names: |
            unit-test-results
            lint-results
```

`artifact-names` lists exact names from the current workflow run, one per line.
Each artifact must contain at least one supported report. Downloads stay separate
to avoid overwriting files with the same name. Both ordinary artifact uploads and
the `.tar` archives produced by the shared Command action are supported.

The action uploads `build_report.html` as the `build-report` artifact and returns
`artifact-url` and `artifact-id`. Override `artifact-name` for multiple independent
reports in one run. Failed tests or lint, missing reports, invalid report data, or
download errors fail the action after available results have been published.
Image-build failures remain the responsibility of the producing jobs.

## Report formats and sections

The shared Build workflow creates report sections for selected pre/post artifact
producers: `pre-checks`, `pre-lint`, `pre-test`, `pre-test-unit`,
`pre-test-coverage`, `pre-test-integration`, `pre-test-e2e`, and their `post-`
equivalents. The section ID is the producer key; its title is the corresponding
`*-name`, including the workflow's default name. For example,
`post-test-name: System Test (post-steps)` names that producer's section.

Names affect presentation only. Artifact content determines the fields and
results; configuring a command never invents report data. HTML, job summaries,
and PR comments omit fields that are absent from the selected artifacts.
Tests, lint, and coverage from one producer stay in the same section; mixed
content has typed subsections in HTML and labeled details in summaries.
Legacy JSON keys and filenames do not override the producer's title.

| Content | Reported fields |
| --- | --- |
| JUnit or Google Test XML, including `system_tests.xml` | Tests |
| Ament lint `*.xunit.xml`, Ruff JSON, Pyright JSON | Lint |
| Cobertura XML, including aggregate-only reports | Coverage |
| Build-report JSON | Supplied test, lint, and coverage fields |

A clean Ruff `[]` or Pyright `{"generalDiagnostics": []}` supplies lint results
with zero issues, without establishing how many files were checked. Missing
selected artifacts fail; they are never treated as clean reports.

### Section names

Direct action callers can supply an optional `artifact-sections` JSON map:

```yaml
artifact-names: contract-results
artifact-sections: >-
  {"contract-results": {"id": "contract", "title": "Contract checks"}}
```

Without a mapping, each artifact has its own section named after the artifact.
Keys must reference selected artifacts. IDs start with a letter or digit and
contain only letters, digits, `_`, `.`, or `-`; titles must be nonempty.
The action validates this metadata before downloading artifacts. Matching IDs
combine results; different IDs remain separate even if their titles match.
All mappings for an ID must specify the same default title.

JSON result objects can override the title with `section_title`:

```json
{
  "section_title": "API contracts",
  "suites": [{"name": "API", "package": "example", "tests": 2}]
}
```

The title applies to all supported files in that producer's artifacts, including
native XML, lint, and coverage. Precedence is `section_title`, then the producing
step's `*-name` (or direct action mapping), then the artifact name. The producer
ID remains unchanged. Conflicting explicit titles for one ID fail the action
after publishing available results. A title-only file is invalid: metadata must
accompany result content. Native results can use the workflow name directly.

### Build-report JSON

Custom producers must follow [report.schema.json](report.schema.json). The action
checks required fields, types, allowed statuses, finite nonnegative counts and
durations, and coverage rates from 0 to 1. Covered lines cannot exceed executable
lines. Unknown fields are rejected. Test-case results establish minimum suite
counts so omitted totals cannot hide failures.

Existing `suites` and `system_suites` arrays both supply tests; `lint_packages`
supplies lint results and `cov_packages` supplies coverage. These keys describe
values, not section titles. Empty arrays alongside populated arrays are omitted.
A single supplied array identifies its result type even when empty.

For producers that always write all four arrays, use `sections` to identify
result types that completed with zero findings:

```json
{
  "sections": ["lint"],
  "suites": [],
  "system_suites": [],
  "lint_packages": [],
  "cov_packages": []
}
```

Allowed values are `tests`, `lint`, and `coverage`; `unit` and `system` remain
accepted aliases for tests. This metadata records field presence, not display
names, and cannot hide populated results or failures. Multiple empty arrays
without metadata are ambiguous and produce a warning instead of invented fields.

The generated `build_report.json` stores normalized `report_sections` with stable
IDs, titles, result `kinds`, and values. It follows the same schema and can be
read as a coverage baseline or result input. When used as a new producer's input,
its values are combined under that producer; only a top-level `section_title`
overrides the new title.

Upload each result once: including raw XML and its aggregated JSON copy would
count it twice. Coverage is informational; a decrease against the optional
baseline does not fail the action.

## Results and logging

The action publishes available results before failing for test/lint failures,
missing selected artifacts, download errors, or malformed reports. Producing
jobs remain responsible for running checks and propagating their exit codes.

Warnings appear in action annotations and the report for zero collected tests,
ambiguous empty JSON, coverage with no executable lines, and an unusable requested
baseline. These conditions do not change the action's exit code, but the report
shows warnings instead of an unconditional pass. Omitted sections, clean lint,
and ordinary coverage changes do not produce warnings. Coverage comparisons are
informational, including decreases.

## Optional publishing

Set `pr-comment: 'true'` to create or update the marked build-report comment on
pull requests. The calling job must grant `pull-requests: write`. Duplicate report
comments are removed when updating. Leave comments disabled for workflows with
read-only tokens.

Set `baseline-artifact` to compare coverage with that artifact from the latest
successful run of `baseline-workflow` (default `release.yml`) on the repository's
default branch. This requires `actions: read`. An absent, expired, or invalid
baseline omits the comparison without failing the current report.
The baseline is an aggregate coverage report. With several coverage-producing
sections, comparison is omitted with a warning because the aggregate cannot be
attributed to one producer.

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
