# AGENTS.md

## Repository Guidance

- Treat this repository as a public library of reusable GitHub Actions, reusable workflows, and CI/CD helpers. Keep actions generic enough for external repositories to adopt, even when a change is motivated by GetDevOpsPro usage.
- Prefer parameterized composite actions and reusable workflows over copying workflow YAML between repositories.
- Keep action and workflow behavior documented in `README.md` when it changes user-facing inputs, outputs, permissions, required secrets, or expected calling patterns.
- Use stable versioned references in examples. When bumping the repository version, run `make release-version VERSION=<version>` so references in `.github/workflows/` and `README.md` stay aligned.
- Prefer wrapping maintained upstream actions when they already provide the needed behavior. Add custom logic here when behavior needs to be shared consistently across repositories.
- Preserve the existing directory layout:
  - `.github/workflows/` for reusable workflows.
  - `<topic>/action.yml` for composite actions.
  - `release/` for release, changelog, versioning, and GitHub release helpers.
  - `buildx-bake/` for Docker Buildx Bake image build and promotion helpers.
  - `test/label/` and `pr/` for pull request automation helpers.

## Action And Workflow Changes

- Keep inputs and outputs explicit, documented, and backward compatible when possible.
- Prefer additive inputs over breaking changes. If a breaking change is unavoidable, document the migration impact in `README.md` or briefly in the commit message..
- Use clear, generic input names unless an input intentionally targets a specific upstream tool.
- Keep default values safe for public repositories. Avoid organization-specific defaults unless they are necessary for this repository itself.
- Do not embed secrets, credentials, private repository names, or private infrastructure details in actions, workflows, tests, or examples.
- Use least-privilege workflow permissions and document any required elevated permissions.
- Avoid logging tokens, secret-derived values, private URLs, or environment dumps.

## Release And Versioning

- `Makefile` is the source for the repository release helper version.
- `make release-version VERSION=<version>` updates versioned references in reusable workflows and README examples, then stages those files.
- `make promote VERSION=<version>` commits, tags, and pushes the release. Do not run it unless the user explicitly asks for a release/push.
- Keep release commits small and conventional commits compatible.

## Validation

- For YAML or workflow changes, prefer running an action/workflow linter if available in the environment.
- For shell embedded in composite actions, keep scripts POSIX-aware or explicitly `bash` when bash features are used; include `set -euo pipefail` for non-trivial shell blocks.
- For release helper changes, run the smallest safe local check that proves the Makefile target updates the expected files without touching external services.
- Do not run workflows, publish releases, push tags, or trigger external CI unless the user explicitly asks.

## Documentation Style

- Keep documentation concise and useful to someone discovering the public repository for the first time.
- Include minimal examples that are safe to copy into another repository.
- Prefer synthetic placeholder values for secrets, owners, repositories, images, and branch names.
