"""Exercise backup artifacts and failure reporting with disposable source files."""
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'backend/scripts/backup'


class BackupContractsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hydro backup ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.laravel = self.root / 'laravel'
        self.services = self.root / 'services'
        self.mqtt = self.services / 'mqtt-bridge'
        for path in [self.laravel, self.mqtt, self.services / 'automation-engine',
                     self.services / 'history-logger', self.root / 'bin']:
            path.mkdir(parents=True, exist_ok=True)
        (self.laravel / '.env').write_text('APP_KEY=stale-key\n')
        (self.laravel / 'composer.lock').write_text('{}')
        for name in ['mosquitto.dev.conf', 'mosquitto.prod.conf', 'passwords.txt', 'acl']:
            (self.mqtt / name).write_text('fixture')
        (self.mqtt / 'certs').mkdir()
        (self.mqtt / 'certs/server.key').write_text('fixture-key')
        (self.root / 'compose.env').write_text('APP_KEY=active-key\n')
        (self.root / 'compose.yml').write_text('services: {}\n')
        pg_dump = self.root / 'bin/pg_dump'
        pg_dump.write_text('''#!/bin/sh
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-f" ]; then shift; printf 'PGDMP-fixture' > "$1"; exit 0; fi
  shift
done
exit 1
''')
        pg_dump.chmod(0o700)
        self.env = {
            **os.environ, 'PATH': f'{self.root / "bin"}:{os.environ["PATH"]}',
            'BACKUP_DIR': str(self.root / 'backups'), 'LARAVEL_DIR': str(self.laravel),
            'SERVICES_DIR': str(self.services), 'MQTT_CONFIG_DIR': str(self.mqtt),
            'CONFIGS_DIR': str(self.root / 'configs'), 'SKIP_DOCKER': '1',
            'SKIP_MQTT': '0', 'ACTIVE_APP_KEY': 'active-key',
            'DEPLOY_ENV_FILE': str(self.root / 'compose.env'),
            'DEPLOY_COMPOSE_FILE': str(self.root / 'compose.yml'),
        }

    def run_backup(self, name='full_backup.sh'):
        return subprocess.run(['bash', str(SCRIPTS / name)], env=self.env,
                              text=True, capture_output=True, timeout=30)

    def manifest(self):
        return json.loads(next((self.root / 'backups/full').glob('*/manifest.json')).read_text())

    def test_application_backup_artifacts_and_private_permissions(self):
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = self.manifest()
        self.assertEqual(manifest['scope'], 'application')
        self.assertEqual(manifest['failed_count'], 0)
        self.assertEqual(manifest['success_count'], 4)
        self.assertEqual(manifest['skipped_count'], 1)
        components = {c['component']: c for c in manifest['components']}
        self.assertEqual(components['docker']['status'], 'skipped')
        with zipfile.ZipFile(components['mqtt']['file']) as archive:
            self.assertTrue({'mqtt-bridge/passwords.txt', 'mqtt-bridge/acl',
                             'mqtt-bridge/mosquitto.prod.conf', 'mqtt-bridge/certs/server.key'}
                            <= set(archive.namelist()))
        with zipfile.ZipFile(components['laravel']['file']) as archive:
            self.assertEqual(archive.read('.env'), b'APP_KEY=active-key\n')
        with zipfile.ZipFile(components['python']['file']) as archive:
            self.assertIn('deployment/compose.env', archive.namelist())
            self.assertIn('deployment/docker-compose.yml', archive.namelist())
        for component in components.values():
            if component['status'] == 'success':
                path = Path(component['file'])
                self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0)

    def test_missing_mqtt_credentials_fails_instead_of_reporting_complete_backup(self):
        (self.mqtt / 'passwords.txt').unlink()
        result = self.run_backup()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.manifest()['failed_components'], ['mqtt'])

    def test_explicit_mqtt_skip_is_visible_in_manifest(self):
        self.env['SKIP_MQTT'] = '1'
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = self.manifest()
        self.assertEqual(manifest['scope'], 'partial_application')
        self.assertEqual(manifest['skipped_count'], 2)

    def test_missing_deployment_environment_is_a_failed_component(self):
        (self.root / 'compose.env').unlink()
        result = self.run_backup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('python', self.manifest()['failed_components'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
