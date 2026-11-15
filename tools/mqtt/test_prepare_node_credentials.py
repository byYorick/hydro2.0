import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prepare_node_credentials import prepare, read_private_json


class CredentialsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inventory = [{'username': 'node_A', 'node_uid': 'nd-A', 'hardware_id': 'hw-A'},
                          {'username': 'node_B', 'node_uid': 'nd-B', 'hardware_id': 'hw-B'}]
        self.services = {'history_logger': 'h'*40, 'mqtt_bridge': 'b'*40}

    def test_real_hashing_stable_credentials_and_targeted_rotation(self):
        first = self.root/'first'
        prepare(self.inventory, self.services, first)
        previous = read_private_json(first/'node_credentials.json')
        self.assertEqual(first.stat().st_mode & 0o777, 0o700)
        for name in ['node_credentials.json', 'node_passwords.json', 'passwords']:
            self.assertEqual((first/name).stat().st_mode & 0o777, 0o600)
        hashed = (first/'passwords').read_text()
        for secret in list(self.services.values()) + [x['password'] for x in previous.values()]:
            self.assertNotIn(secret, hashed)
        self.assertEqual(len(hashed.splitlines()), 4)
        second = self.root/'second'
        prepare(self.inventory, self.services, second, previous=previous)
        self.assertEqual(read_private_json(second/'node_credentials.json'), previous)
        third = self.root/'third'
        prepare(self.inventory, self.services, third, previous=previous, rotate=['nd-A'])
        rotated = read_private_json(third/'node_credentials.json')
        self.assertNotEqual(rotated['nd-A']['password'], previous['nd-A']['password'])
        self.assertEqual(rotated['nd-B'], previous['nd-B'])

    def test_invalid_rotation_and_duplicate_service_secrets_rejected(self):
        for services, rotate in [(self.services, ['absent']), ({'history_logger':'x'*40,'mqtt_bridge':'x'*40}, [])]:
            with self.assertRaises(ValueError):
                prepare(self.inventory, services, self.root/'invalid', rotate=rotate)
        self.assertFalse((self.root/'invalid').exists())

    def test_failure_removes_all_staged_secrets(self):
        with patch('prepare_node_credentials.subprocess.run') as run:
            run.return_value.returncode = 1
            with self.assertRaises(RuntimeError):
                prepare(self.inventory, self.services, self.root/'failed')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_public_secret_file_rejected(self):
        path = self.root/'secret.json'
        path.write_text(json.dumps(self.services))
        path.chmod(0o644)
        with self.assertRaises(ValueError): read_private_json(path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
