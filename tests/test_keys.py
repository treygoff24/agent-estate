"""Invented credentials only; all subprocesses use an isolated home."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
from tests.helpers import TempHome, ROOT

spec = importlib.util.spec_from_file_location('estate_keys', ROOT / 'modules/keys/keys.py')
keys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(keys)


class KeysTests(TempHome):
    def setUp(self):
        super().setUp()
        self.shims = self.tmp / 'shims'
        self.real = self.tmp / 'bin'
        self.real.mkdir()
        self.secret = self.tmp / 'credentials'
        self.secret.write_text('FIRST_KEY=invented-one\nSECOND_KEY=invented-two\n')
        self.secret.chmod(0o600)
        self.write_config(['keys'], f'''\n[keys]
file = "{self.secret}"
names = ["FIRST_KEY", "SECOND_KEY"]
[modules.keys]
shim_dir = "{self.shims}"
optional = ["SECOND_KEY"]
[modules.keys.tools]
probe = ["FIRST_KEY"]
''')
        self.env = dict(os.environ, ESTATE_STATE=str(self.state), ESTATE_MODULE_DIR=str(ROOT / 'modules/keys'), PATH=str(self.shims) + os.pathsep + str(self.real) + os.pathsep + os.environ['PATH'])

    def run_keys(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'modules/keys/keys.py'), *args], env=self.env, capture_output=True, text=True)

    def test_scrub_inject(self):
        probe = self.real / 'probe'
        probe.write_text('#!' + sys.executable + '\nimport os,json\nprint(json.dumps({k:v for k,v in os.environ.items() if k in ("FIRST_KEY","SECOND_KEY")}))\n')
        probe.chmod(0o755)
        self.assertEqual(self.run_keys('install').returncode, 0)
        env = self.env | {'FIRST_KEY': 'ambient-first', 'SECOND_KEY': 'ambient-second'}
        result = subprocess.run([str(self.shims / 'probe')], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'FIRST_KEY': 'invented-one'})

    def test_permissions(self):
        self.secret.chmod(0o644)
        with self.assertRaises(keys.KeyErrorSafe):
            keys.read_keys(self.secret)

    def test_regeneration(self):
        self.assertEqual(self.run_keys('install', '--dry-run').returncode, 0)
        self.assertFalse(self.shims.exists())
        self.assertEqual(self.run_keys('install').returncode, 0)
        shim = self.shims / 'probe'
        before = shim.stat().st_mtime_ns
        self.assertEqual(self.run_keys('install').returncode, 0)
        self.assertEqual(shim.stat().st_mtime_ns, before)
        shim.write_text('stale')
        self.assertEqual(self.run_keys('install').returncode, 0)
        self.assertIn('exec python3', shim.read_text())

    def test_push_stdin_only(self):
        ssh = self.real / 'ssh'
        capture = self.tmp / 'capture'
        ssh.write_text('#!' + sys.executable + '\nimport json,sys\nfrom pathlib import Path\nPath(' + repr(str(capture)) + ').write_text(json.dumps([sys.argv,sys.stdin.read()]))\n')
        ssh.chmod(0o755)
        result = self.run_keys('push', 'vps')
        self.assertEqual(result.returncode, 0, result.stdout)
        argv, stdin = json.loads(capture.read_text())
        self.assertNotIn('invented-one', str(argv))
        self.assertNotIn('invented-two', str(argv))
        self.assertEqual(json.loads(stdin), {'FIRST_KEY': 'invented-one', 'SECOND_KEY': 'invented-two'})
        self.assertNotIn('invented', result.stdout + result.stderr)

    def test_check_statuses(self):
        self.assertEqual(self.run_keys('check').returncode, 1)
        self.assertEqual(self.run_keys('install').returncode, 0)
        self.assertEqual(self.run_keys('check').returncode, 0)
        self.secret.write_text('FIRST_KEY=invented-one\n')
        self.assertEqual(self.run_keys('check').returncode, 2)
        self.secret.write_text('SECOND_KEY=invented-two\n')
        self.assertEqual(self.run_keys('check').returncode, 1)

    def test_receive(self):
        from io import BytesIO
        class Input:
            buffer = BytesIO(b'{"FIRST_KEY":"invented-new"}')
        with patch.object(sys, 'stdin', Input()):
            keys.receive()
        self.assertEqual(self.secret.read_text(), 'FIRST_KEY=invented-new\n')
        self.assertEqual(self.secret.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    import unittest
    unittest.main()
