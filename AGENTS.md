# AGENTS.md

## Repository Guidance

- Treat this repository as the private Clean-Botix custom reusable GitHub Actions library for the OptimusClean project.
- Optimize changes for internal OptimusClean repositories and Clean-Botix operational conventions. Do not frame this repository as a public action catalog.
- Prefer parameterized composite actions and reusable workflows over copying workflow YAML between repositories.
- Keep reusable workflow and composite action behavior, required permissions, inputs, outputs, and secrets documented when they change.
- Every reusable workflow in `.github/workflows/` must be briefly documented in `.github/workflows/README.md`, except self-maintenance workflows such as `release.self.yml`.
- Every composite action must have a `README.md` in the same directory as its `action.yml`; include a short purpose statement, when to use it, and a minimal safe example.
- Link new action and reusable workflow documentation from the root `README.md`.
- Use stable versioned references in examples. When bumping the repository version, run `make release-version VERSION=<version>` so local references in `.github/workflows/` and `README.md` files stay aligned.
- Prefer wrapping maintained upstream actions when they already provide the needed behavior. Add custom logic here when behavior needs to be shared consistently across OptimusClean repositories.
- Preserve the existing directory layout:
  - `.github/workflows/` for reusable workflows.
  - `<topic>/action.yml` for composite actions.
  - `release/` for release, changelog, versioning, and GitHub release helpers.
  - `buildx-bake/` for Docker Buildx Bake image build and promotion helpers.
  - `test/label/` and `pr/` for pull request automation helpers.
  - `notify/slack/` for Slack notification helpers.

## Action And Workflow Changes

- Keep inputs and outputs explicit, documented, and backward compatible when possible.
- Prefer additive inputs over breaking changes. If a breaking change is unavoidable, document the migration impact in `README.md` or briefly in the commit message.
- Use clear, generic input names unless an input intentionally targets a specific integration, GitHub pull request labels, or a known upstream action contract.
- Keep default values safe for private Clean-Botix OptimusClean repositories. Avoid unrelated organization-specific defaults; OptimusClean-specific defaults are appropriate when they match the workflow's purpose.
- Do not embed secrets, webhook URLs, credentials, private repository names, private channel names, or private infrastructure details in actions, workflows, tests, or examples.
- Use least-privilege workflow permissions and document any required elevated permissions.
- Avoid logging tokens, webhook URLs, secret-derived values, private URLs, or environment dumps.
- For shell embedded in composite actions, keep scripts POSIX-aware or explicitly `bash` when bash features are used; include `set -euo pipefail` for non-trivial shell blocks.

## Release And Versioning

- `Makefile` is the source for the repository release helper version.
- `make release-version VERSION=<version>` updates versioned `clean-botix/github-actions` references in reusable workflows and README files, then stages those files.
- `make promote VERSION=<version>` commits, tags, and pushes the release. Do not run it unless the user explicitly asks for a release/push.
- Keep release commits small and Conventional Commits compatible.

## Validation

- For YAML or workflow changes, prefer running an action/workflow linter if available in the environment.
- For release helper changes, run the smallest safe local check that proves the Makefile target updates the expected files without touching external services.
- Do not send notifications, run workflows, publish releases, push tags, or trigger external CI unless the user explicitly asks.

## Documentation Style

- Keep documentation concise and useful to Clean-Botix OptimusClean maintainers who need to consume or modify the shared CI assets.
- Include minimal examples that are safe to copy into another OptimusClean repository.
- Use synthetic placeholders for secrets, channels, artifact URLs, repositories, and branch names; never include real Clean-Botix operational identifiers unless they are already public repository slugs needed for `uses:` references.
- For per-action READMEs, avoid duplicating the full input table unless it adds clarity; `action.yml` remains the authoritative schema.
