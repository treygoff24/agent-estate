"""compile-slot-gate admission and rustc-gate, against a temp state dir."""

import json
import os
import subprocess
import sys
import time
import unittest

from tests.helpers import ROOT, TempHome

BIN = ROOT / "modules" / "guardrails" / "bin"
GATE = BIN / "compile-slot-gate"
RUSTC_GATE = BIN / "rustc-gate"

# Holds its slot until the release file appears; touches started.<n> once admitted.
HOLD = "touch {d}/started.{n}; while [ ! -e {d}/release ]; do sleep 0.05; done"


class Slots(TempHome):
    def setUp(self):
        super().setUp()
        self.slots_dir = self.tmp / "slots"
        self.d = self.tmp / "work"
        self.d.mkdir()
        self.env = dict(os.environ) | {
            "COMPILE_SLOTS_STATE_DIR": str(self.slots_dir), "RUSTC_GATE_SLOTS": "2",
            "COMPILE_SLOT_HEADROOM_GB": "100", "TESTRUN_CONFIG": str(self.tmp / "none.json"),
            "HOME": str(self.home)}
        self.procs = []

    def tearDown(self):
        (self.d / "release").touch()
        for p in self.procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        super().tearDown()

    def gate(self, *cmd, env=None, bg=False):
        e = self.env | (env or {})
        argv = [sys.executable, str(GATE), "rustc", "--", *cmd]
        if bg:
            p = subprocess.Popen(argv, env=e, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.procs.append(p)
            return p
        return subprocess.run(argv, env=e, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)

    def hold(self, n, env=None):
        return self.gate("sh", "-c", HOLD.format(d=self.d, n=n), env=env, bg=True)

    def wait_started(self, n, seconds=10):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if (self.d / f"started.{n}").exists():
                return True
            time.sleep(0.05)
        return False

    def snapshot(self):
        return json.loads((self.slots_dir / "state.json").read_text())["rustc"]

    def test_third_compile_waits_for_a_slot_then_runs_with_its_own_exit_code(self):
        a, b = self.hold(1), self.hold(2)
        self.assertTrue(self.wait_started(1) and self.wait_started(2))
        third = self.gate("sh", "-c", "exit 7", bg=True)
        time.sleep(0.6)
        self.assertIsNone(third.poll(), "a third compile ran with both slots taken")
        snap = self.snapshot()
        self.assertEqual((snap["in_use"], snap["total"], snap["queue_depth"]), (2, 2, 1))
        (self.d / "release").touch()
        self.assertEqual(third.wait(timeout=15), 7)
        self.assertEqual((a.wait(timeout=15), b.wait(timeout=15)), (0, 0))

    def test_slot_is_freed_when_a_holder_is_killed(self):
        a, b = self.hold(1), self.hold(2)
        self.assertTrue(self.wait_started(1) and self.wait_started(2))
        a.kill()  # SIGKILL: no cleanup runs; the kernel drops its lock
        a.wait()
        p = self.gate("true")  # admitted at once into the freed slot while b still holds the other
        self.assertEqual(p.returncode, 0, p.stderr)
        (self.d / "release").touch()
        self.assertEqual(b.wait(timeout=15), 0)

    def test_memory_headroom_gates_slots_past_the_base(self):
        env = {"RUSTC_GATE_SLOTS": "3", "RUSTC_GATE_BASE": "1", "RUSTC_GATE_HEADROOM_GB": "12",
               "COMPILE_SLOT_HEADROOM_GB": "5"}
        self.env |= env
        first = self.hold(1)
        self.assertTrue(self.wait_started(1))
        second = self.hold(2)
        time.sleep(0.8)
        self.assertFalse((self.d / "started.2").exists(), "slot 2 opened with 5 GB free (needs 12)")
        second.kill()
        second.wait()
        # 13 GB opens slot 2 (needs 12) but not slot 3 (needs 14)
        self.env["COMPILE_SLOT_HEADROOM_GB"] = "13"
        again = self.hold(2)
        self.assertTrue(self.wait_started(2))
        third = self.hold(3)
        time.sleep(0.8)
        self.assertFalse((self.d / "started.3").exists(), "slot 3 opened with 13 GB free (needs 14)")
        third.kill()
        third.wait()
        (self.d / "release").touch()
        self.assertEqual((first.wait(timeout=15), again.wait(timeout=15)), (0, 0))

    def test_status_reports_totals(self):
        p = subprocess.run([sys.executable, str(GATE), "status"], env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["rustc"]["total"], 2)

    def test_settings_file_supplies_the_slot_count(self):
        (self.tmp / "g.json").write_text(json.dumps({"rustc_slots": 5}))
        env = {k: v for k, v in self.env.items() if k != "RUSTC_GATE_SLOTS"} | {"TESTRUN_CONFIG": str(self.tmp / "g.json")}
        p = subprocess.run([sys.executable, str(GATE), "status"], env=env, capture_output=True, text=True)
        self.assertEqual(json.loads(p.stdout)["rustc"]["total"], 5)


class RustcGate(TempHome):
    def setUp(self):
        super().setUp()
        self.fake = self.tmp / "fake"
        self.fake.mkdir()
        self.env = dict(os.environ) | {
            "COMPILE_SLOTS_STATE_DIR": str(self.tmp / "slots"), "RUSTC_GATE_SLOTS": "2",
            "COMPILE_SLOT_HEADROOM_GB": "100", "TESTRUN_CONFIG": str(self.tmp / "none.json"),
            "HOME": str(self.home), "PATH": f"{self.fake}:{os.environ['PATH']}"}
        self.env.pop("CARGO_INCREMENTAL", None)

    def run_gate(self, *cmd, env=None):
        return subprocess.run([str(RUSTC_GATE), *cmd], env=self.env | (env or {}), capture_output=True,
                              text=True, stdin=subprocess.DEVNULL, timeout=30)

    def test_compiler_runs_through_a_slot(self):
        p = self.run_gate("sh", "-c", "echo compiled; exit 4", env={"RUSTC_GATE_SCCACHE": "0"})
        self.assertEqual((p.returncode, p.stdout.strip()), (4, "compiled"), p.stderr)
        self.assertTrue((self.tmp / "slots" / "state.json").exists(), "the slot helper never ran")

    def test_zero_slots_bypasses_the_helper(self):
        p = self.run_gate("echo", "direct", env={"RUSTC_GATE_SLOTS": "0", "RUSTC_GATE_SCCACHE": "0"})
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "direct"), p.stderr)
        self.assertFalse((self.tmp / "slots").exists())

    def test_goes_through_sccache_when_installed_and_not_when_incremental(self):
        sccache = self.fake / "sccache"
        sccache.write_text('#!/bin/sh\necho "SCCACHE $*"\n')
        sccache.chmod(0o755)
        p = self.run_gate("printf", "x")
        self.assertIn("SCCACHE", p.stdout, p.stderr)
        self.assertIn("printf x", p.stdout)
        p = self.run_gate("printf", "x", env={"CARGO_INCREMENTAL": "1"})
        self.assertEqual(p.stdout, "x")
        p = self.run_gate("printf", "x", env={"RUSTC_GATE_SCCACHE": "0"})
        self.assertEqual(p.stdout, "x")

    @unittest.skipUnless(sys.platform == "darwin", "the nice wrapper applies on macOS only")
    def test_macos_compiles_run_at_nice_19(self):
        p = self.run_gate("sh", "-c", "ps -o ni= -p $$", env={"RUSTC_GATE_SCCACHE": "0"})
        self.assertEqual(p.stdout.strip(), "19", p.stderr)


if __name__ == "__main__":
    unittest.main()
