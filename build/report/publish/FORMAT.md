# Report JSON v1

Repositories run tools, classify findings, apply policy, and supply measurements
and comparisons. The publisher validates this interface, renders it, and publishes
the results. It does not run checks, choose thresholds, retrieve baselines, or
calculate comparison deltas. Baseline retrieval is a separate action.

[report.schema.json](report.schema.json) defines every field and allowed value.
[examples/report-v1.json](examples/report-v1.json) is a complete synthetic input
with tests, lint, a tool failure, coverage changes, and shared baseline references.
It deliberately produces a failed report. Missing/invalid artifact errors are
added by the publisher from actual input validation, not supplied by producers.

## Envelope

| Field | Format and meaning |
| --- | --- |
| `schema_version` | Integer `1`. Recommended for new producers; unversioned existing reports remain accepted. Unknown versions fail validation. |
| `section_title` | Optional nonblank display title for the producing step. |
| `sections` | Optional array of `tests`, `lint`, `coverage` (`unit`/`system` are test aliases). Declares completed result types even when empty. |
| `suites`, `system_suites` | Test suite arrays: `name`, `package`; optional nonnegative `tests`, `failures`, `errors`, `skipped`, `time`, and `cases`. Cases require `name`, `classname`, `time`, and `status` (`passed`, `failed`, `error`, `skipped`); `message` and `details` are optional. |
| `lint_packages` | Array of packages with `package` and optional `tools`. Tools require `name` and optionally `files`; see below. |
| `cov_packages` | Array of `package`, `line_rate` (0–1), `lines_covered`, `lines_valid`, and optional `files`. Files require `name` and the same measurements. Optional `html_dir`/`html_path` links are cleared when exported to another runner. |
| `outcome` | Optional producer result: `status` (`passed`, `failed`, `error`, `skipped`) and optional `message`. Repository policy failures use `failed`; an incomplete tool run can use `error`. |
| `issues` | Optional array of reported tool failures, policy failures, or notices; see below. |
| `baselines` | Optional array of reusable provenance records, independent of coverage. |
| `comparisons` | Optional array of repository-calculated measurement comparisons. |
| `report_sections` | Normalized sections with `id`, `title`, `kinds` (`tests`, `lint`, `coverage`) and any result/metadata fields above except `schema_version`, `section_title`, `sections`, or nested `report_sections`. |

At least one result array, normalized section array, or metadata field is required.
Unknown fields and malformed values fail validation. Empty metadata does not
establish completed checks. Counts are integers; durations and measurements are
finite numbers. Case results establish minimum suite counts. Covered lines cannot
exceed executable lines.

## Lint severity

Each `files` entry requires `name` and `status`: `passed`, `failed`, `warning`, or
`information`. Optional `message` and `details` are text. For accurate diagnostic
counts, provide `diagnostics`, an array of:

| Field | Format |
| --- | --- |
| `severity` | Required: `error`, `warning`, or `information`. |
| `message` | Required string; multiple lines still represent one diagnostic. |
| `rule` | Optional rule identifier string. |
| `line`, `column` | Optional positive, one-based integers. |

When diagnostics are nonempty, the file status must match its highest severity:
error → `failed`, warning → `warning`, information → `information`. Structured
diagnostics are counted individually. Entries without diagnostics are labeled as
reported checks; the publisher never infers diagnostic counts from message lines.
Mixed formats keep these counts separate. Counts describe emitted findings, not
the number of source files scanned.

Native Pyright preserves all three severities. Its error summary must agree with
emitted errors; warning/information totals may exceed emitted findings when
Pyright filters output. Native Ruff violations and ament lint failures are errors.
Repositories that classify Ruff findings differently can produce this JSON format.

## Outcomes and issues

`outcome` records repository policy. It can add a blocking result without
inventing a test or lint diagnostic. A `passed`/`skipped` outcome never hides
reported test errors, lint errors, or tool/policy failures. When several inputs
belong to one producer, the strongest outcome wins (`error`, `failed`, `passed`,
`skipped`); messages are retained.

Each issue requires `kind`, `severity`, and a nonblank `message`:

| Kind | Severity | Additional fields | Effect |
| --- | --- | --- | --- |
| `tool` | `error` | Required `tool` name; optional integer `exit_code` and text `details` | Blocking tool execution failure |
| `policy` | `error` | Optional `tool`, `exit_code`, `details` | Blocking repository policy failure |
| `notice` | `warning` or `information` | Optional `tool`, `exit_code`, `details` | Visible, nonblocking notice |

Reported failures appear separately from publisher input errors. Failed tests,
lint errors, failed/error outcomes, and tool/policy issues block the action.
Missing selected artifacts, invalid reports, and download errors also block it,
after publishing available results. Warnings and information alone do not block.
Tool exit codes are evidence; the producer must explicitly classify failures.

## Baselines and comparisons

Each baseline requires a local `id` (letters/digits/`_`/`.`/`-`, starting with a
letter or digit) and `status`: `exact`, `approximate`, or `unavailable`.

| Baseline field | Format |
| --- | --- |
| `sha`, `run_url` | Required for exact/approximate: 40 lowercase hex characters and an HTTPS run URL. |
| `requested_sha` | Optional requested commit, same SHA format. |
| `distance` | Optional nonnegative first-parent distance; `1` identifies a parent. Approximate remains approximate. |
| `artifact_name`, `created_at` | Optional nonblank provenance strings; timestamps appear in HTML. |
| `reason` | Required when unavailable; optional explanatory text otherwise. |

Top-level baseline IDs are shared within that JSON document. Normalized sections
may define their own local IDs; local definitions take precedence. Duplicate IDs
within one scope are invalid. References cannot cross input files. Normalization
assigns stable IDs from provenance and updates references; identical provenance
is shown once as B1, B2, etc. Different producers can safely reuse local names.

Each comparison requires nonblank `name` and `status` (`available`/`unavailable`):

| Comparison field | Format |
| --- | --- |
| `baseline_id` | Required for available comparisons; references an available baseline. Optional for unavailable comparisons, but must resolve when present. |
| `current`, `previous`, `delta` | Required finite numbers when available. Supplied values are rendered without recalculation. |
| `unit`, `delta_unit` | Required strings when available, e.g. `%` and `pp`, or `tests` and `tests`. |
| `details` | Optional text describing the measurement scope. |
| `reason` | Required when unavailable; omit `delta` in this case. |

Coverage and comparisons are neutral measurements. Increases display `↑ +2.3 pp`,
decreases `↓ −0.4 pp`, unchanged values `→ 0.0 pp (unchanged)`. Nonzero changes
that would round to zero keep their direction (`↑ +<0.1 pp`). Unavailable values
use a reason, never fabricated zeroes. Unavailable baselines/comparisons warn;
approximate baselines carry a notice. None impose a threshold or fail a check.
A repository that requires a baseline or rejects a decrease must supply a failed
outcome or policy issue.

Existing `coverage_comparison` remains supported with its
[legacy fields](README.md#coverage-comparisons); its provenance now appears in
the separate Baselines section. Prefer `baselines`/`comparisons` for new producers.

## Repository commands

Keep ordinary unit-test commands lightweight. A repository-owned `unit-test-cov`
command explicitly enables coverage. A repository-owned `ci-unit-test` command
runs the intended checks and exports supported artifacts, including partial
results and tool failures before propagating failure. These are recommended
repository conventions, not commands supplied or invoked by this action.
Local and CI paths should use the same result fields and severity classification.
Upload one representation of each result to avoid double counting.
