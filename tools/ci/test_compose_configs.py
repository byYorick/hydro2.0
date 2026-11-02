"""Validate Compose schemas with generated test values, without starting services."""
import os
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
