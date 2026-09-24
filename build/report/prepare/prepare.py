"""Prepare build command matrices and report artifact selection."""

import json
import os
import secrets


STEP_KINDS = ("checks", "lint", "test", "test-unit", "test-coverage", "test-integration", "test-e2e")
STEP_FIELDS = (
    "name", "command", "runner", "docker-login", "qemu-install", "artifact-name",
    "artifact-path", "artifact-overwrite", "artifact-if-no-files-found", "artifact-retention-days",
)


def step_matrix(inputs, phase):
    matrix = []
    for kind in STEP_KINDS:
        prefix = f"{phase}-{kind}"
        if not inputs.get(f"{prefix}-command", ""):
            continue
        step = {}
        for field in STEP_FIELDS:
            value = inputs.get(f"{prefix}-{field}", "")
            step[field] = value if isinstance(value, str) else json.dumps(value)
        for tool in ("docker", "compose"):
            step[f"{tool}-version"] = inputs.get(f"{phase}-{tool}-version") or inputs.get(f"{tool}-version", "")
        matrix.append(step)
    return matrix


def prepare_inputs(inputs):
    if not isinstance(inputs, dict):
        raise ValueError("build-inputs must be a JSON object")
    enabled = inputs.get('build-report-enabled', False)
    producers = {}
    errors = []
    prefixes = dict.fromkeys(
        key.rsplit('-artifact-', 1)[0] for key in inputs
        if key.startswith(('pre-', 'post-')) and key.endswith(('-artifact-name', '-artifact-path'))
    )
    for prefix in prefixes:
        name = inputs.get(f'{prefix}-artifact-name', '').strip()
        path = inputs.get(f'{prefix}-artifact-path', '').strip()
        if not (name or path):
            continue
        missing = [key for key in ('command', 'artifact-name', 'artifact-path')
                   if not inputs.get(f'{prefix}-{key}', '').strip()]
        if missing:
            errors.append(f'{prefix}: artifact upload requires ' + ', '.join(f'{prefix}-{key}' for key in missing))
            continue
        if name in ('.', '..') or any(c in name for c in '\\/:*?"<>|\r\n'):
            errors.append(f'{prefix}-artifact-name must be a valid single artifact name')
            continue
        if enabled and name in producers:
            errors.append(f'{prefix} and {producers[name]} must use distinct artifact names for reporting')
        producers[name] = prefix

    names = []
    if enabled:
        explicit = inputs.get('build-report-artifacts', '')
        names = list(dict.fromkeys(name.strip() for name in explicit.splitlines() if name.strip())) or list(producers)
        if not names:
            errors.append('build-report-enabled=true requires at least one pre/post artifact with a command and path')
        if any(name not in producers for name in names):
            errors.append('build-report-artifacts must reference configured pre/post artifact names')
        reserved = {'build-report', inputs.get('source-artifact-name', '')}
        if any(name in reserved for name in producers):
            errors.append('Pre/post artifact names must not conflict with the source or build-report artifact')
    if inputs.get('baseline-enabled', False):
        artifact = inputs.get('baseline-artifact', '')
        if not artifact.strip() or artifact in ('.', '..') or any(c in artifact for c in '\\/:*?"<>|\r\n'):
            errors.append('baseline-enabled=true requires a valid baseline-artifact name')
        if not inputs.get('baseline-workflow', 'release.yml').strip():
            errors.append('baseline-enabled=true requires baseline-workflow')
        if not any(value.strip() for key, value in inputs.items()
                   if key.startswith(('pre-', 'post-')) and key.endswith('-command')):
            errors.append('baseline-enabled=true requires at least one pre/post command')
        bundle_name = 'build-baseline-' + inputs.get('source-artifact-name', 'source-code')
        if bundle_name in producers:
            errors.append('Pre/post artifact names must not conflict with the baseline bundle')
    if errors:
        raise ValueError('\n'.join(errors))
    sections = {}
    for name in names:
        prefix = producers[name]
        title = inputs.get(f'{prefix}-name', prefix)
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f'{prefix}-name must be nonempty for reporting')
        sections[name] = {'id': prefix, 'title': title}
    outputs = {"artifacts": "\n".join(names), "artifact-sections": json.dumps(sections)}
    for phase in ("pre", "post"):
        matrix = step_matrix(inputs, phase)
        outputs[f"{phase}-step-matrix"] = json.dumps(matrix, ensure_ascii=False, separators=(",", ":"))
        outputs[f"{phase}-step-names"] = json.dumps([step["name"] for step in matrix], ensure_ascii=False)
    return outputs


def main():
    try:
        outputs = prepare_inputs(json.loads(os.environ["BUILD_INPUTS"]))
    except ValueError as error:
        raise SystemExit(str(error)) from None
    delimiter = "prepare_" + secrets.token_hex(16)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in outputs.items():
            output.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


if __name__ == "__main__":
    main()
