"""Restore safety/engine negotiation tests with isolated command doubles.

Real TimescaleDB data round-trip is qualified separately; these tests protect
preflight-before-drop and failure behavior without touching any database.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
RESTORE = ROOT / 'backend/scripts/restore/postgres_restore.sh'
STUB = '''import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name
args=sys.argv[1:]
sql='' if any(a in ['-c','-tc'] for a in args) else sys.stdin.read()
with open(os.environ['QA_CALLS'],'a') as stream:stream.write(json.dumps(dict(name=name,args=args,sql=sql))+'\\n')
if name=='pg_restore':
 if '--list' in args:
  if not Path(args[-1]).read_bytes().startswith(b'valid'):sys.exit(1)
  print('1; 3079 1 EXTENSION - timescaledb' if os.environ.get('QA_ENGINE')=='timescale' else '1; 1259 1 TABLE public example')
 elif os.environ.get('QA_FAIL')=='1':sys.exit(1)
elif name=='psql':print('1')
'''


class RestoreSafetyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = self.root / 'calls.jsonl'
        self.dump = self.root / 'fixture.dump'
        self.dump.write_bytes(b'valid fixture')
        for name in ['pg_restore', 'psql']:
            path = self.root / name
            path.write_text('#!'+sys.executable+'\n'+STUB)
            path.chmod(0o755)

    def run_restore(self, **options):
        env = os.environ | {'PATH': str(self.root)+os.pathsep+os.environ['PATH'],
            'QA_CALLS': str(self.calls), 'FORCE_RESTORE': '1', 'DB_NAME': 'qa_restore_test', **options}
        result = subprocess.run(['bash', str(RESTORE), str(self.dump)], env=env,
                                capture_output=True, text=True, timeout=15)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result, calls

    def test_invalid_archive_never_contacts_target(self):
        self.dump.write_bytes(b'invalid')
        result, calls = self.run_restore()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c['name']=='psql' for c in calls))

    def test_system_database_never_contacts_target(self):
        result, calls = self.run_restore(DB_NAME='postgres')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c['name']=='psql' for c in calls))

    def test_timescale_hooks_surround_restore(self):
        result, calls = self.run_restore(QA_ENGINE='timescale')
        self.assertEqual(result.returncode, 0, result.stderr)
        pre = next(i for i,c in enumerate(calls) if 'SELECT timescaledb_pre_restore();' in c['args'])
        data = next(i for i,c in enumerate(calls) if c['name']=='pg_restore' and '--list' not in c['args'])
        post = next(i for i,c in enumerate(calls) if 'SELECT timescaledb_post_restore();' in c['args'])
        self.assertLess(pre, data)
        self.assertLess(data, post)
        self.assertIn('--exit-on-error', calls[data]['args'])

    def test_partial_timescale_restore_keeps_restoring_mode(self):
        result, calls = self.run_restore(QA_ENGINE='timescale', QA_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any('SELECT timescaledb_pre_restore();' in c['args'] for c in calls))
        self.assertFalse(any('SELECT timescaledb_post_restore();' in c['args'] for c in calls))

    def test_plain_postgres_does_not_require_timescale(self):
        result, calls = self.run_restore(QA_ENGINE='postgres')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any('timescaledb_' in ' '.join(c['args']) for c in calls))

    def test_database_name_is_not_interpolated_into_sql(self):
        name = 'qa_restore"; DROP DATABASE postgres; --'
        result, calls = self.run_restore(DB_NAME=name)
        self.assertEqual(result.returncode, 0, result.stderr)
        for call in calls:
            self.assertNotIn(name, call['sql'])
        self.assertTrue(any('restore_db='+name in c['args'] for c in calls))


if __name__ == '__main__':
    unittest.main(verbosity=2)
