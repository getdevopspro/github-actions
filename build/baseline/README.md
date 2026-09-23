# Build Baseline

Finds the reference commit for an existing checkout and downloads a named artifact
from its workflow run. Use it before a repository script compares coverage or
other measurements. It does not parse reports, calculate changes, or enforce
thresholds. Resolving a checkout requires Git; artifact lookup requires
`actions: read`. Checkout separately needs `contents: read`.

## Usage

Use a release containing the new `build/baseline` path. The repository supplies
`scripts/build-report`, which reads the metadata and artifact, generates current
results, computes comparisons, and writes report JSON. The command below shows
that script's expected interface; it is not supplied by this action.

```yaml
permissions:
  contents: read
  actions: read
steps:
  - uses: actions/checkout@v6
    with:
      fetch-depth: 0
  - uses: getdevopspro/github-actions/build/baseline@v9.1.0
    id: baseline
    with:
      artifact-name: unit-test-results
      workflow: release.yml
      allow-ancestor: 'true'
  - name: Produce report data
    env:
      BASELINE_METADATA: ${{ steps.baseline.outputs.metadata-file }}
    run: ./scripts/build-report --baseline-metadata "$BASELINE_METADATA" --output build/results.json
  - uses: actions/upload-artifact@v7
    with:
      name: results
      path: build/results.json
  - uses: getdevopspro/github-actions/build/report@v9.1.0
    with:
      artifact-names: results
```

The versioned references above must be updated to the release containing this
migration; existing v9.1.0 consumers retain the old paths and behavior.

`working-directory` defaults to the caller's checkout. `path` optionally sets a
new output directory; an existing path fails to prevent mixing stale results.
Otherwise each invocation creates a unique directory under the runner temp path.
Artifact files remain data: never execute scripts downloaded from a baseline.

### Reusable Build workflow

The [Build workflow](../../.github/workflows/README.md#baselines) calls this action
when `baseline-enabled: true`. Prepare resolves the reference using its existing
checkout, then a separate job retrieves the artifact once and shares it with
pre/post commands. Reporting and coverage configuration do not enable lookup.

For custom workflows needing the same split, `resolve-only: 'true'` returns only
the `reference` output (`{"branch":"main","commits":["<40-character SHA>"]}`). It
uses local Git without API calls, artifact inputs, downloads, or metadata files.
Pass that JSON through a job output to a second invocation's `reference` input,
along with `artifact-name`. That invocation needs `actions: read` but no checkout.
Use the reference from the same workflow run; an empty commit list stays
unavailable and never falls back to another checkout.

## Selection

- PR merge checkout: the merge's first parent, the target revision actually tested.
- PR head checkout: its merge base with the target branch.
- Branch push: the event's `before` SHA, including multi-commit and force pushes.
- Manual/scheduled branch run: the tested revision's first parent.
- New branches, unsupported events, or mismatched checkouts: unavailable.

The action reuses local Git history; it neither fetches history nor calls the
commit-history API. Shallow checkouts retain raw commit parents or push event metadata for exact
lookups, but cannot supply missing merge bases or ancestors.

Selection first queries the exact reference SHA on the target/pushed branch.
Only completed successful runs qualify by default. `run-conclusion: any` also
allows failed or cancelled runs with an available artifact, useful when comparing
failed test results. Current runs and pull-request runs are excluded.

`allow-ancestor: 'true'` enables fallback only when no eligible exact run exists.
It searches up to 100 first-parent commits and 100 recent branch runs, chooses the
nearest eligible ancestor, and marks the result approximate. At the same commit,
the newest eligible run wins. Missing/expired artifacts on the selected run do
not cause a silent fallback to an older run.

## Outputs and logging

`status` is `exact`, `approximate`, or `unavailable`. The `path` output is the
absolute downloaded artifact directory; it is empty unless the download succeeded.
`requested-sha`, `sha`, `run-id`, and `run-url` expose provenance. `metadata-file` always exists
after a completed lookup, including an unavailable result:

```json
{
  "status": "exact",
  "requested_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "run_id": 42,
  "run_url": "https://github.com/example/project/actions/runs/42",
  "created_at": "2026-01-01T00:00:00Z",
  "path": "artifacts"
}
```

The JSON `path` is relative to the metadata file's directory so the bundle can
move between runners. Resolve it against that directory before reading files;
preserve the `metadata.json` and `artifacts/` layout when transferring them.

An unavailable result includes `reason` and an empty `path`. Download failure can
retain the selected run in metadata for diagnosis; consumers must check `status`
before reading artifacts. No reference revision logs informationally. A requested
reference with no usable run/artifact, API failure, or download failure warns
without failing the action. Ancestor fallback emits a notice. Invalid inputs and
an existing output directory fail immediately.

Repository scripts own measurement scope, compatible tool/configuration checks,
comparison arithmetic, missing-data handling, and threshold enforcement. For
coverage, emit the optional [report comparison fields](../report/README.md#coverage-comparisons).
Other comparisons require their own producer and report contract; this action
only supplies the baseline artifact and provenance.

Run `make test-report` for offline Git revision, API selection, download outcome,
and report tests.
