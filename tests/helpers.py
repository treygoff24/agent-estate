"""Shared test fixtures. Every test runs against a temporary HOME and config;
nothing touches the real home directory."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
ESTATE = ROOT / "bin" / "estate"

BASE_TOML = textwrap.dedent("""\
    label_prefix = "com.example.estate"

    [user]
    name = "Test User"
    email = "test@example.com"

    [git]
    remote_base = "git@github.com:example"

    [paths]
    state = "{state}"

    [[machines]]
    name = "mac"
    role = "workstation"
    os = "mac"

    [[machines]]
    name = "vps"
    ssh = "vps-alias"
    role = "agents"
    os = "linux"

    [harnesses.claude]

    [modules]
    enabled = {enabled}
    """)


class TempHome(unittest.TestCase):
    """A test case with its own HOME, state dir and config path."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.state = self.tmp / "state"
        self.cfg_path = self.tmp / "estate.toml"
        self._env = dict(os.environ)
        os.environ["HOME"] = str(self.home)
        os.environ["ESTATE_CONFIG"] = str(self.cfg_path)
        for k in ("ESTATE_PLATFORM", "ESTATE_MACHINE", "XDG_CONFIG_HOME"):
            os.environ.pop(k, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        self._tmp.cleanup()

    def write_config(self, enabled=(), extra=""):
        text = BASE_TOML.format(state=self.state, enabled=list(enabled)) + extra
        self.cfg_path.write_text(text)
        return self.cfg_path

    def estate(self, *args, env=None):
        e = dict(os.environ) | (env or {})
        return subprocess.run([sys.executable, str(ESTATE), *args], capture_output=True,
                              text=True, env=e, stdin=subprocess.DEVNULL)


def write_module(modules_dir: Path, name: str, meta: str = "", check: str | None = None,
                 install: str | None = None, platforms='["mac", "linux"]', requires="[]"):
    d = modules_dir / name
    d.mkdir(parents=True)
    (d / "module.toml").write_text(
        f'name = "{name}"\ndescription = "test module {name}"\n'
        f"platforms = {platforms}\nrequires = {requires}\n{meta}")
    for script, body in (("check", check), ("install", install)):
        if body is not None:
            p = d / script
            p.write_text("#!/usr/bin/env bash\n" + body + "\n")
            p.chmod(0o755)
    return d


def python_fixture(tmp: Path):
    """(good, old, log): a dir whose python3 is this (3.11+) interpreter, a dir whose python3 is
    an 'old' one that records any use in `log` and fails, and that log path."""
    good, old = tmp / "goodbin", tmp / "oldbin"
    good.mkdir()
    old.mkdir()
    log = tmp / "old-python-used"
    (good / "python3").symlink_to(sys.executable)
    (old / "python3").write_text(f'#!/bin/sh\necho "$0 $*" >> "{log}"\nexit 1\n')
    (old / "python3").chmod(0o755)
    return good, old, log


def run_launchd_job(plist: Path, path: str, env: dict):
    """Run a plist's ProgramArguments the way launchd would: no environment but what the job and
    the plist's EnvironmentVariables give it, and a minimal PATH (`path`) when the plist sets none."""
    import plistlib
    data = plistlib.loads(plist.read_bytes())
    job_env = {"PATH": path} | env | data.get("EnvironmentVariables", {})
    return subprocess.run(["env", "-i", *[f"{k}={v}" for k, v in job_env.items()],
                           *data["ProgramArguments"]],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)


class PinnedPythonMac:
    """Mixin for a module's test case (a TempHome with `self.env`): its Mac launchd job must run
    under launchd's minimal PATH, where python3 is Apple's old one or missing. Set `module`, the
    state-relative `output` file one run of the job rewrites, and define `prepare()` (config,
    logins). Install runs with a good python3 on PATH; the job then runs with only an old one."""

    module = ""
    output = ""

    def prepare(self):
        raise NotImplementedError

    def _mac_env(self):
        good, old, log = python_fixture(self.tmp)
        macbin = self.tmp / "macbin"
        macbin.mkdir(exist_ok=True)
        (macbin / "launchctl").write_text(
            '#!/bin/sh\nif [ "$1" = bootstrap ]; then touch "$FAKE_MAC_LOADED"; fi\n'
            'if [ "$1" = bootout ]; then rm -f "$FAKE_MAC_LOADED"; fi\n'
            'if [ "$1" = print ] || [ "$1" = list ]; then [ -f "$FAKE_MAC_LOADED" ]; fi\n')
        (macbin / "launchctl").chmod(0o755)
        env = self.env | {"ESTATE_PLATFORM": "mac", "FAKE_MAC_LOADED": str(self.tmp / "mac-loaded"),
                          "PATH": f"{macbin}:{good}:{self.env['PATH']}"}
        return env, old, log

    def _row(self, env):
        p = self.estate("doctor", "--json", env=env)
        return {r["name"]: r for r in json.loads(p.stdout)["checks"]}[self.module]

    def test_mac_job_runs_the_pinned_python_under_a_minimal_path(self):
        self.prepare()
        env, old, log = self._mac_env()
        p = self.estate("install", env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        pin = (self.state / self.module / "python3").read_text().strip()
        self.assertEqual(os.path.realpath(pin), os.path.realpath(sys.executable))
        plist = self.home / "Library/LaunchAgents" / f"com.example.estate.{self.module}.plist"
        shipped = plist.read_text() + "".join(f.read_text() for f in (self.state / self.module).glob("*.sh"))
        self.assertIn(pin, shipped)  # in ProgramArguments, or in the wrapper the job runs
        self.assertIn("/opt/homebrew/bin", plist.read_text())
        self.assertEqual(self._row(env)["status"], 0, self._row(env))
        # the install-time run proves nothing about launchd: remove its output, run the job as
        # launchd would, with an old python3 first on its PATH
        (self.state / self.output).unlink()
        job_env = {k: v for k, v in env.items() if k != "PATH"} | {
            "HOME": str(self.home), "ESTATE_CONFIG": str(self.cfg_path),
            "ESTATE_STATE": str(self.state), "ESTATE_ROOT": str(ROOT)}
        r = run_launchd_job(plist, f"{old}:/usr/bin:/bin", job_env)
        self.assertFalse(log.exists(), f"the old python3 ran: {log.read_text() if log.exists() else ''}")
        self.assertTrue((self.state / self.output).exists(), r.stdout + r.stderr)

    def test_mac_install_without_python_3_11_fails_clearly(self):
        self.prepare()
        env, _, _ = self._mac_env()
        p = self.estate("install", env=env | {"ESTATE_PYTHON_SEARCH": "python3.98 python3.99"})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("3.11", p.stdout + p.stderr)
        self.assertFalse((self.home / "Library/LaunchAgents").exists())

    def test_mac_check_fails_when_the_pinned_python_is_gone(self):
        self.prepare()
        env, _, _ = self._mac_env()
        self.assertEqual(self.estate("install", env=env).returncode, 0)
        (self.state / self.module / "python3").write_text(str(self.tmp / "no-such-python") + "\n")
        row = self._row(env)
        self.assertEqual(row["status"], 1, row)
        self.assertIn("pinned Python", row["summary"])
