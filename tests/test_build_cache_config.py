"""Cache-mount configuration checks without Docker or network access."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'buildx-bake/build/cache-config.sh'


class CacheConfigTests(unittest.TestCase):
    def configure(self, mapping='', **overrides):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            env = dict(os.environ, CACHE_MAP=mapping, CACHE_SCOPE='example',
                       BUILD_PLATFORM='linux/arm64', BAKE_TARGET='build',
                       BUILD_FILES_HASH='example-file-hash', GITHUB_OUTPUT=str(output))
            env.update(overrides)
            result = subprocess.run(['bash', str(SCRIPT)], env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                raise ValueError(result.stderr)
            return dict(line.split('=', 1) for line in output.read_text().splitlines())

    def test_discovery_keeps_an_empty_map(self):
        config = self.configure()
        self.assertEqual(config['cache-map'], '')
        self.assertRegex(config['prefix'], r'^cache-mount-v2-example-linux-arm64-[0-9a-f]{64}-$')

    def test_platform_variables_and_numeric_ownership(self):
        mapping = {'cache-mount/compiler': {
            'target': '/home/builder/.cache/compiler',
            'id': 'compiler-${TARGETOS}-${TARGETARCH}-${TARGETVARIANT}',
            'uid': 1000, 'gid': 1000, 'sharing': 'locked',
        }}
        result = self.configure(json.dumps(mapping), BUILD_PLATFORM='linux/arm/v7')
        options = json.loads(result['cache-map'])['cache-mount/compiler']
        self.assertEqual(options['id'], 'compiler-linux-arm-v7')
        self.assertEqual(options['uid'], 1000)
        self.assertEqual(options['gid'], 1000)
        self.assertEqual(options['sharing'], 'locked')

    def test_map_formatting_does_not_invalidate_archives(self):
        first = '{"cache-mount/pip":"/root/.cache/pip","cache-mount/compiler":{"target":"/cache","uid":1000}}'
        second = json.dumps(json.loads(first), sort_keys=True, indent=2)
        self.assertEqual(self.configure(first), self.configure(second))

    def test_incompatible_configuration_has_no_shared_restore_prefix(self):
        baseline = self.configure()['prefix']
        for change in [dict(BUILD_PLATFORM='linux/amd64'), dict(BAKE_TARGET='other'),
                       dict(BUILD_FILES_HASH='changed-file-hash'), dict(CACHE_SCOPE='other'),
                       dict(CACHE_MAP='{"cache-mount/compiler":"/cache"}')]:
            with self.subTest(change=change):
                self.assertNotEqual(baseline, self.configure(**change)['prefix'])
        for uid in (1000, 1001):
            mapping = json.dumps({'cache-mount/compiler': {'target': '/cache', 'uid': uid}})
            if uid == 1000:
                original = self.configure(mapping)['prefix']
            else:
                self.assertNotEqual(original, self.configure(mapping)['prefix'])

    def test_unresolved_variables_fail_instead_of_using_the_wrong_cache(self):
        for variable in ('${USER}', '$USER'):
            with self.subTest(variable=variable), self.assertRaisesRegex(ValueError, 'resolved paths and IDs'):
                self.configure(json.dumps({'cache-mount/compiler': {'target': '/home/'+variable+'/cache'}}))

    def test_archived_paths_stay_inside_the_cache_directory(self):
        for key in ('/tmp/cache', 'cache-mount/../outside', 'cache-mount/..', 'elsewhere'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.configure(json.dumps({key: '/cache'}))


class QemuConfigTests(unittest.TestCase):
    def configure(self, mode='auto', target='linux/arm64', native='linux/aarch64', runner='X64'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, probe = root / 'output', root / 'probe'
            docker = root / 'docker'
            docker.write_text("#!/bin/sh\nprintf called > \"$PROBE_FILE\"\n"
                              "[ \"$FAKE_PLATFORM\" != error ] || exit 1\n"
                              "printf '%s\\n' \"$FAKE_PLATFORM\"\n")
            docker.chmod(0o755)
            env = dict(os.environ, PATH=directory + os.pathsep + os.environ['PATH'],
                       QEMU_MODE=mode, BUILD_PLATFORM=target, FAKE_PLATFORM=native,
                       PROBE_FILE=str(probe), GITHUB_OUTPUT=str(output), RUNNER_ARCH=runner)
            result = subprocess.run(['bash', str(SCRIPT.with_name('qemu-config.sh'))],
                                    env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                raise ValueError(result.stdout + result.stderr)
            return output.read_text().strip() == 'enabled=true', probe.exists()

    def test_native_aliases_and_baseline_variants_skip_emulation(self):
        for target, native in [
            ('linux/amd64', 'linux/x86_64'), ('linux/amd64/v1', 'linux/x86-64'),
            ('linux/arm64', 'linux/aarch64'), ('linux/arm64/v8', 'linux/aarch64'),
            ('linux/arm64/8', 'linux/arm64'), ('linux/arm64/v8.0', 'linux/arm64'),
        ]:
            with self.subTest(target=target, native=native):
                self.assertEqual(self.configure(target=target, native=native), (False, True))

    def test_foreign_architecture_os_and_nonbaseline_variants_keep_emulation(self):
        for target, native in [
            ('linux/arm64', 'linux/amd64'), ('linux/amd64', 'linux/arm64'),
            ('linux/amd64/v3', 'linux/amd64'), ('linux/arm64/v9', 'linux/arm64'),
            ('windows/amd64', 'linux/amd64'), ('linux/arm64', 'linux/unknown'),
        ]:
            with self.subTest(target=target, native=native):
                self.assertEqual(self.configure(target=target, native=native), (True, True))

    def test_daemon_platform_takes_precedence_over_runner_architecture(self):
        self.assertEqual(self.configure(target='linux/amd64', native='linux/amd64', runner='ARM64'),
                         (False, True))

    def test_explicit_modes_do_not_probe_docker(self):
        self.assertEqual(self.configure(mode='true', native='error'), (True, False))
        self.assertEqual(self.configure(mode='false', native='error'), (False, False))

    def test_invalid_mode_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, 'qemu must be auto, true or false'):
            self.configure(mode='yes', native='error')

    def test_daemon_query_failure_is_not_treated_as_native(self):
        with self.assertRaisesRegex(ValueError, 'Unable to inspect the Docker daemon platform'):
            self.configure(native='error')


if __name__ == '__main__':
    unittest.main()
