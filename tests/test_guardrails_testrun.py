"""testrun on both platform paths, with systemd-run and systemctl faked on PATH.
Nothing here touches real systemd, and the Mac path runs the same on any host."""

import json
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests.helpers import ROOT, TempHome

TESTRUN = ROOT / "modules" / "guardrails" / "bin" / "testrun"

# Runs the command after `--` as itself (a real scope does the same), logging the unit
# arguments and remembering the pid so the fake `systemctl stop` can stop it.
FAKE_SYSTEMD_RUN = """#!/usr/bin/env bash
unit=""; args=()
while [ $# -gt 0 ]; do
  [ "$1" = -- ] && { shift; break; }
  case "$1" in --unit=*) unit="${1#--unit=}" ;; esac
  args+=("$1"); shift
done
echo "systemd-run ${args[*]}" >> "$FAKE_LOG"
echo $$ > "$FAKE_DIR/$unit.pid"
exec "$@"
"""
FAKE_SYSTEMCTL = """#!/usr/bin/env bash
echo "systemctl $*" >> "$FAKE_LOG"
case "$*" in
  *show-environment*) [ -f "$FAKE_DIR/nobus" ] && exit 1; exit 0 ;;
  *is-active*) cat "$FAKE_DIR/active" 2>/dev/null || echo inactive; exit 0 ;;
  *" stop "*) unit="${@: -1}"; unit="${unit%.scope}"
     [ -f "$FAKE_DIR/$unit.pid" ] && kill "$(cat "$FAKE_DIR/$unit.pid")" 2>/dev/null; exit 0 ;;
esac
"""


class Base(TempHome):
    def setUp(self):
        super().setUp()
        self.fake = self.tmp / "fake"
        self.fake.mkdir()
        self.log = self.tmp / "calls.log"
        for name, body in (("systemd-run", FAKE_SYSTEMD_RUN), ("systemctl", FAKE_SYSTEMCTL)):
            (self.fake / name).write_text(body)
            (self.fake / name).chmod(0o755)
        self.env = {"PATH": f"{self.fake}:{os.environ['PATH']}", "FAKE_LOG": str(self.log),
                    "FAKE_DIR": str(self.fake), "TESTRUN_STATE_DIR": str(self.tmp / "tr-state"),
                    "TESTRUN_CONFIG": str(self.tmp / "guardrails.json"),
                    "TESTRUN_PRESSURE_GAP": "0", "TESTRUN_POLL_SECS": "0.05", "HOME": str(self.home)}
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.terminate()  # testrun stops its own unit or process group on SIGTERM
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
        super().tearDown()

    def run_tr(self, *args, platform, env=None, timeout=30):
        e = dict(os.environ) | self.env | {"TESTRUN_PLATFORM": platform} | (env or {})
        return subprocess.run([sys.executable, str(TESTRUN), *args], capture_output=True, text=True,
                              env=e, stdin=subprocess.DEVNULL, timeout=timeout)

    def start_tr(self, *args, platform, env=None):
        e = dict(os.environ) | self.env | {"TESTRUN_PLATFORM": platform} | (env or {})
        p = subprocess.Popen([sys.executable, str(TESTRUN), *args], env=e, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.procs.append(p)
        return p

    def wait_for(self, path, seconds=10):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if Path(path).exists():
                return
            time.sleep(0.05)
        self.fail(f"{path} never appeared")


class Linux(Base):
    def test_runs_in_a_named_scope_in_the_configured_slice(self):
        (self.tmp / "guardrails.json").write_text(json.dumps({"slice": "com.example.estate.guardrails.slice"}))
        p = self.run_tr("myrepo", "unit", "--", "sh", "-c", "echo out; exit 3", platform="linux")
        self.assertEqual(p.returncode, 3, p.stderr)  # the command's own exit code
        self.assertIn("out", p.stdout)
        call = [l for l in self.log.read_text().splitlines() if l.startswith("systemd-run")][0]
        for part in ("--user", "--scope", "--unit=myrepo-unit",
                     "--slice=com.example.estate.guardrails.slice", "RuntimeMaxSec=600"):
            self.assertIn(part, call)

    def test_default_time_limit_follows_the_kind(self):
        self.run_tr("r", "gate-full", "--", "true", platform="linux")
        self.run_tr("r", "mut-sweep", "--", "true", platform="linux")
        self.run_tr("r", "unit", "--max", "42", "--", "true", platform="linux")
        calls = "\n".join(l for l in self.log.read_text().splitlines() if l.startswith("systemd-run"))
        for limit in ("RuntimeMaxSec=1800", "RuntimeMaxSec=7200", "RuntimeMaxSec=42"):
            self.assertIn(limit, calls)

    def test_second_run_of_the_same_name_is_refused_while_one_is_live(self):
        first = self.start_tr("dup", "unit", "--", "sleep", "30", platform="linux")
        self.wait_for(self.fake / "dup-unit.pid")
        marker = self.tmp / "second-ran"
        second = self.run_tr("dup", "unit", "--", "touch", str(marker), platform="linux")
        self.assertEqual(second.returncode, 75, second.stderr)
        self.assertIn("already running", second.stderr)
        self.assertFalse(marker.exists())
        # a different kind of the same repo is not a duplicate
        self.assertEqual(self.run_tr("dup", "other", "--", "true", platform="linux").returncode, 0)
        # stopping the first frees the name
        first.send_signal(signal.SIGTERM)
        first.wait(timeout=10)
        self.assertEqual(self.run_tr("dup", "unit", "--", "true", platform="linux").returncode, 0)

    def test_live_unit_without_a_lock_is_also_refused(self):
        # A testrun killed with SIGKILL leaves the unit up and drops the lock.
        (self.fake / "active").write_text("active\n")
        marker = self.tmp / "ran"
        p = self.run_tr("ghost", "unit", "--", "touch", str(marker), platform="linux")
        self.assertEqual(p.returncode, 75, p.stderr)
        self.assertFalse(marker.exists())

    def test_no_user_bus_refuses_rather_than_running_unwrapped(self):
        (self.fake / "nobus").write_text("")
        marker = self.tmp / "ran"
        p = self.run_tr("r", "unit", "--", "touch", str(marker), platform="linux")
        self.assertEqual(p.returncode, 69, p.stderr)
        self.assertFalse(marker.exists())

    def test_time_limit_exit_code(self):
        p = self.run_tr("r", "unit", "--max", "1", "--", "sh", "-c", "sleep 2; exit 143", platform="linux")
        self.assertEqual(p.returncode, 124, p.stderr)
        self.assertIn("time limit", p.stderr)

    def test_usage_errors(self):
        for args in (["Bad_Repo", "unit", "--", "true"], ["r", "unit", "true"], ["r", "unit", "--"],
                     ["r", "unit", "--max", "0", "--", "true"], ["r"]):
            self.assertEqual(self.run_tr(*args, platform="linux").returncode, 64, args)

    def test_list_shows_live_runs(self):
        self.start_tr("listed", "unit", "--", "sleep", "30", platform="linux")
        self.wait_for(self.fake / "listed-unit.pid")
        time.sleep(0.2)
        out = self.run_tr("--list", platform="linux").stdout
        self.assertIn("listed-unit", out)


class Mac(Base):
    def setUp(self):
        super().setUp()
        # No systemd on the Mac: the fakes must never be called.
        for name in ("systemd-run", "systemctl"):
            (self.fake / name).write_text("#!/bin/sh\necho CALLED >> \"$FAKE_LOG\"\nexit 99\n")

    def test_runs_niced_at_19_without_touching_systemd(self):
        p = self.run_tr("r", "unit", "--", "sh", "-c", "ps -o ni= -p $$", platform="mac")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "19")
        self.assertFalse(self.log.exists(), "the Mac path called systemd")

    def test_exit_code_passes_through(self):
        self.assertEqual(self.run_tr("r", "unit", "--", "sh", "-c", "exit 5", platform="mac").returncode, 5)

    def test_second_run_of_the_same_name_is_refused(self):
        self.start_tr("dup", "unit", "--", "sleep", "30", platform="mac")
        end = time.monotonic() + 10
        while time.monotonic() < end and "dup-unit" not in self.run_tr("--list", platform="mac").stdout:
            time.sleep(0.1)
        marker = self.tmp / "ran"
        p = self.run_tr("dup", "unit", "--", "touch", str(marker), platform="mac")
        self.assertEqual(p.returncode, 75, p.stderr)
        self.assertFalse(marker.exists())

    def test_group_dies_with_the_run(self):
        pidfile = self.tmp / "bg.pid"
        p = self.run_tr("r", "unit", "--", "sh", "-c", f"sleep 60 & echo $! > {pidfile}", platform="mac")
        self.assertEqual(p.returncode, 0, p.stderr)
        pid = int(pidfile.read_text())
        end = time.monotonic() + 5
        alive = True
        while alive and time.monotonic() < end:
            try:
                os.kill(pid, 0)
                time.sleep(0.05)
            except ProcessLookupError:
                alive = False
        self.assertFalse(alive, "the background process outlived the run")

    def test_time_limit_kills_and_exits_124(self):
        t = time.monotonic()
        p = self.run_tr("r", "unit", "--max", "1", "--", "sleep", "30", platform="mac")
        self.assertEqual(p.returncode, 124, p.stderr)
        self.assertLess(time.monotonic() - t, 15)

    def test_critical_memory_pressure_blocks_admission_but_warn_does_not(self):
        level = self.tmp / "level"
        marker = self.tmp / "ran"
        level.write_text("4\n")
        env = {"TESTRUN_PRESSURE_FILE": str(level)}
        p = self.run_tr("r", "unit", "--wait-max", "1", "--", "touch", str(marker), platform="mac", env=env)
        self.assertEqual(p.returncode, 75, p.stderr)
        self.assertFalse(marker.exists())
        level.write_text("2\n")  # warn happens routinely during a big build: never blocks
        p = self.run_tr("r", "unit", "--wait-max", "1", "--", "touch", str(marker), platform="mac", env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
