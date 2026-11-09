"""Validate Compose schemas with generated test values, without starting services."""
import os
import json
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FILES = [
    'backend/docker-compose.dev.yml', 'backend/docker-compose.dev.win.yml',
    'backend/docker-compose.ci.yml', 'backend/docker-compose.prod.yml',
    'tests/e2e/docker-compose.e2e.yml', 'infra/hil/docker-compose.hil.yml',
]


class ComposeConfigsTest(unittest.TestCase):
    def test_compose_schemas_and_interpolation(self):
        env = os.environ.copy()
        # Do not use deployed credentials or the repository's local .env files.
        for name in FILES:
            for key in re.findall(r'\$\{([A-Z][A-Z0-9_]*):\?', (ROOT / name).read_text()):
                env[key] = secrets.token_hex(32)
        with tempfile.NamedTemporaryFile() as empty_env:
            for name in FILES:
                with self.subTest(compose=name):
                    result = subprocess.run([
                        'docker', 'compose', '--env-file', empty_env.name,
                        '-f', str(ROOT / name), 'config', '--quiet',
                    ], env=env, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_application_backup_sources_are_read_only_without_docker_socket(self):
        env = os.environ.copy()
        files = ['backend/docker-compose.dev.yml', 'backend/docker-compose.prod.yml']
        for name in files:
            for key in re.findall(r'\$\{([A-Z][A-Z0-9_]*):\?', (ROOT / name).read_text()):
                env[key] = secrets.token_hex(32)
        with tempfile.NamedTemporaryFile() as empty_env:
            for name in files:
                with self.subTest(compose=name):
                    result = subprocess.run([
                        'docker', 'compose', '--env-file', empty_env.name,
                        '-f', str(ROOT / name), 'config', '--format', 'json',
                    ], env=env, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    laravel = json.loads(result.stdout)['services']['laravel']
                    mounts = {volume['target']: volume for volume in laravel['volumes']}
                    for target in ['/scripts/backup', '/backup-sources/services',
                                   '/backup-sources/configs', '/backup-sources/compose.env',
                                   '/backup-sources/docker-compose.yml']:
                        self.assertIn(target, mounts)
                        self.assertTrue(mounts[target]['read_only'])
                    self.assertNotIn('/var/run/docker.sock', mounts)
                    self.assertEqual(laravel['environment']['BACKUP_SOURCE_ROOT'], '/backup-sources')


if __name__ == '__main__':
    unittest.main(verbosity=2)
