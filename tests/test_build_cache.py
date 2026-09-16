"""Integration checks for the candidate Bake action; needs Buildx (and CI for warm)."""

import csv
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid


FIXTURE = Path('tests/fixtures/build-cache')
TEMP = Path(os.environ.get('RUNNER_TEMP', '/tmp'))
PLATFORM = os.environ.get('PLATFORM', 'linux/amd64')
PAIR = PLATFORM.replace('/', '-')
PREFIX = os.environ.get('CACHE_SCOPE', 'buildkit')
BAKE = [
    'docker', 'buildx', 'bake',
    '--file', str(FIXTURE / 'docker-bake.hcl'),
    '--file', str(TEMP / 'bake-meta.json'),
    '--file', str(TEMP / 'bake-defaults.json'),
    '--set', f'*.platform={PLATFORM}',
]


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def resolved(*overrides):
    command = BAKE + ['build', '--print']
    for override in overrides:
        command += ['--set', override]
    targets = json.loads(subprocess.check_output(command, text=True, stderr=subprocess.PIPE))['target']
    # Older Buildx versions print CSV entries; newer versions print objects.
    for config in targets.values():
        for key in ('cache-from', 'cache-to', 'output'):
            config[key] = [
                dict(field.split('=', 1) for field in next(csv.reader([entry])))
                if isinstance(entry, str) else entry
                for entry in config.get(key, [])
            ]
    return targets


def check_defaults():
    defaults = resolved()
    check(set(defaults) == {'alpha', 'beta'}, 'Unexpected target selection')
    for target, config in defaults.items():
        scope = f'{PREFIX}-{target}-{PAIR}'
        check(config['cache-from'] == [{'type': 'gha', 'scope': scope}],
              f'{target}: incorrect import scope')
        check(config['cache-to'] == [{
            'type': 'gha', 'scope': scope, 'mode': 'max', 'ignore-error': 'true',
        }], f'{target}: incorrect export scope/settings')
        check(config['output'] == [{
            'type': 'image', 'push-by-digest': 'true',
            'name-canonical': 'true', 'push': 'true',
        }], f'{target}: default digest push changed')

    for pattern in ('alpha', '*'):
        replaced = resolved(
            f'{pattern}.cache-from=type=registry,ref=example.invalid/cache',
            f'{pattern}.cache-to=type=registry,ref=example.invalid/cache,mode=max',
        )
        disabled = resolved(f'{pattern}.cache-from=', f'{pattern}.cache-to=')
        for target in defaults:
            if pattern in (target, '*'):
                for key in ('cache-from', 'cache-to'):
                    values = replaced[target][key]
                    check(len(values) == 1 and values[0]['type'] == 'registry',
                          f'{target}: {key} override accumulated defaults')
                    check(not disabled[target].get(key),
                          f'{target}: {key} was not disabled')
            else:
                check(replaced[target] == defaults[target], 'Override leaked to another target')
                check(disabled[target] == defaults[target], 'Disable leaked to another target')

    output = resolved('*.output=type=cacheonly', '*.args.EXTRA=example')
    for target, config in output.items():
        check(config['output'] == [{'type': 'cacheonly'}], 'Fixture would push an image')
        check(config['cache-to'] == defaults[target]['cache-to'],
              'Unrelated overrides disabled caching')
    print(f'{PAIR}: scope isolation, defaults, replacement and opt-out checks passed')


def instruction_cached(log, marker):
    vertices = re.findall(r'^(#\d+) \[.*\] RUN .*' + re.escape(marker) + r'.*$', log, re.M)
    check(len(set(vertices)) == 1, f'Expected one {marker} instruction; got {vertices}')
    return bool(re.search(r'^' + re.escape(vertices[0]) + r' CACHED$', log, re.M))


def check_warm():
    measurements = []
    source = FIXTURE / 'alpha.txt'
    original = source.read_text()
    try:
        for case in ('warm-1', 'warm-2', 'source-change', 'dependency-change'):
            if case == 'source-change':
                source.write_text(original + 'changed source\n')
            builder = 'cache-fixture-' + uuid.uuid4().hex[:12]
            subprocess.run(['docker', 'buildx', 'create', '--name', builder,
                            '--driver', 'docker-container'], check=True)
            try:
                subprocess.run(['docker', 'buildx', 'inspect', builder, '--bootstrap'], check=True)
                for target in ('alpha', 'beta'):
                    command = BAKE + [
                        target, '--builder', builder, '--progress', 'plain',
                        '--set', '*.output=type=cacheonly', '--set', '*.cache-to=',
                    ]
                    if case == 'dependency-change':
                        command += ['--set', 'alpha.args.DEPENDENCY=2']
                    started = time.monotonic()
                    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, timeout=180)
                    elapsed = round(time.monotonic() - started, 2)
                    print(result.stdout, flush=True)
                    result.check_returncode()
                    dependency = instruction_cached(result.stdout, 'cache-fixture-dependency-')
                    application = instruction_cached(result.stdout, 'cache-fixture-source-')
                    measurements.append({
                        'platform': PLATFORM, 'case': case, 'target': target,
                        'bake_seconds': elapsed, 'dependency_cached': dependency,
                        'source_cached': application,
                    })
                    check(dependency == (case != 'dependency-change' or target == 'beta'),
                          f'{case}/{target}: wrong dependency cache state')
                    check(application == (case.startswith('warm-') or target == 'beta'),
                          f'{case}/{target}: wrong source cache state')
            finally:
                subprocess.run(['docker', 'buildx', 'rm', builder], check=True)
    finally:
        source.write_text(original)
        (TEMP / 'cache-measurements.json').write_text(json.dumps(measurements, indent=2) + '\n')
        if 'GITHUB_STEP_SUMMARY' in os.environ:
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
                summary.write(f'### Layer-cache fixture: {PLATFORM}\n\n')
                summary.write('| Case | Target | Bake seconds | Dependency cached | Source cached |\n')
                summary.write('| --- | --- | ---: | --- | --- |\n')
                for row in measurements:
                    summary.write(f"| {row['case']} | {row['target']} | {row['bake_seconds']} | "
                                  f"{row['dependency_cached']} | {row['source_cached']} |\n")
                summary.write('\nSynthetic fixture timings; fresh builder per case, cache imports only.\n')
    print(f'{PAIR}: two warm passes and source/dependency invalidation checks passed')


if __name__ == '__main__':
    if sys.argv[1:] == ['defaults']:
        check_defaults()
    elif sys.argv[1:] == ['warm']:
        check_warm()
    else:
        sys.exit('Usage: python3 tests/test_build_cache.py defaults|warm')
