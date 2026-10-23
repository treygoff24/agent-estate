"""The guardrails module end to end through bin/estate, with systemctl faked on PATH
(so it runs on a Mac too). Whether real systemd honours the slice is checked by hand."""

import json
import os
import stat

from tests.helpers import ROOT, TempHome

FAKE_SYSTEMCTL = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
"""
MOD = ROOT / "modules" / "guardrails"


class Guardrails(TempHome):
    def setUp(self):
        super().setUp()
        fake = self.tmp / "fakebin"
        fake.mkdir()
        for name in ("systemctl", "systemd-run"):
            (fake / name).write_text(FAKE_SYSTEMCTL)
            (fake / name).chmod(0o755)
        self.log = self.tmp / "systemctl.log"
        self.bin = self.home / ".local" / "bin"
        self.env = {"ESTATE_PLATFORM": "linux", "PATH": f"{fake}:{os.environ['PATH']}",
                    "FAKE_LOG": str(self.log), "CLAUDE_CONFIG_DIR": "", "CODEX_HOME": ""}
        self.slice = self.home / ".config/systemd/user/com.example.estate.guardrails.slice"
        self.claude = self.home / ".claude" / "settings.json"

    def run_estate(self, *args, env=None):
        return self.estate(*args, env=self.env | (env or {}))

    def row(self):
        p = self.run_estate("doctor", "--json")
        return {r["name"]: r for r in json.loads(p.stdout)["checks"]}["guardrails"]

    def test_install_check_drift_uninstall_on_linux(self):
        self.write_config(["guardrails"], '\n[modules.guardrails]\nmemory_max = "6G"\ncpu_weight = 50\n')
        self.assertEqual(self.row()["status"], 1)  # nothing installed yet

        p = self.run_estate("install", "--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("would write", p.stderr)
        self.assertFalse(self.bin.exists())

        p = self.run_estate("install")
        self.assertEqual(p.returncode, 0, p.stderr)
        for tool in ("testrun", "footgun-hook"):
            mode = (self.bin / tool).stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR, tool)
            self.assertEqual((self.bin / tool).read_bytes(), (MOD / "bin" / tool).read_bytes())
        self.assertFalse((self.bin / "compile-slot-gate").exists(), "compile slots are off by default")
        text = self.slice.read_text()
        self.assertIn("MemoryMax=6G", text)
        self.assertIn("CPUWeight=50", text)
        self.assertIn("daemon-reload", self.log.read_text())
        conf = json.loads((self.home / ".config/agent-estate/guardrails.json").read_text())
        self.assertEqual(conf["slice"], "com.example.estate.guardrails.slice")

        again = self.run_estate("install")  # idempotent: nothing rewritten
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn("wrote:", again.stderr)

        # installed, but the hook is not in the harness settings yet: warn, not fail
        row = self.row()
        self.assertEqual(row["status"], 2, row)
        self.assertIn("claude", row["summary"])
        self.claude.parent.mkdir(parents=True)
        self.claude.write_text((MOD / "settings" / "claude.json").read_text())
        row = self.row()
        self.assertEqual(row["status"], 0, row)

        # drift: a tool edited by hand, then a setting changed in estate.toml
        (self.bin / "testrun").write_text("#!/bin/sh\n")
        self.assertEqual(self.row()["status"], 1)
        self.run_estate("install")
        self.assertEqual(self.row()["status"], 0)
        self.write_config(["guardrails"], '\n[modules.guardrails]\nmemory_max = "7G"\ncpu_weight = 50\n')
        row = self.row()
        self.assertEqual(row["status"], 1)
        self.assertIn("does not match estate.toml", row["summary"])

        p = self.run_estate("uninstall", "guardrails")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse((self.bin / "testrun").exists() or self.slice.exists())

    def test_mac_install_has_no_slice_and_compile_slots_are_opt_in(self):
        self.write_config(["guardrails"], '\n[modules.guardrails]\ncompile_slots = true\n')
        p = self.run_estate("install", env={"ESTATE_PLATFORM": "mac"})
        self.assertEqual(p.returncode, 0, p.stderr)
        for tool in ("testrun", "footgun-hook", "compile-slot-gate", "rustc-gate"):
            self.assertTrue(os.access(self.bin / tool, os.X_OK), tool)
        self.assertFalse(self.slice.exists())
        self.assertNotIn("slice", json.loads((self.home / ".config/agent-estate/guardrails.json").read_text()))
        self.assertNotIn("daemon-reload", self.log.read_text() if self.log.exists() else "")
        (self.bin / "rustc-gate").unlink()
        self.assertEqual(self.row_for("mac")["status"], 1)

    def row_for(self, platform):
        p = self.run_estate("doctor", "--json", env={"ESTATE_PLATFORM": platform})
        return {r["name"]: r for r in json.loads(p.stdout)["checks"]}["guardrails"]

    def test_refuse_unwrapped_tests_false_writes_the_skip_file(self):
        self.write_config(["guardrails"], '\n[modules.guardrails]\nrefuse_unwrapped_tests = false\n')
        self.assertEqual(self.run_estate("install").returncode, 0)
        skip = self.home / ".config/agent-estate/footgun-skip-guardrails"
        self.assertIn("heavy-test-unwrapped", skip.read_text())
        self.write_config(["guardrails"], "")
        self.run_estate("install")
        self.assertFalse(skip.exists())

    def test_bad_settings_are_refused(self):
        self.write_config(["guardrails"], '\n[modules.guardrails]\nmemory_high = "lots"\n')
        p = self.run_estate("install")
        self.assertEqual(p.returncode, 1)
        self.assertIn("memory_high", p.stderr)
        self.assertFalse(self.bin.exists())

    def test_settings_fragments_are_valid_hook_config(self):
        for name in ("claude.json", "codex-hooks.json"):
            data = json.loads((MOD / "settings" / name).read_text())
            entry = data["hooks"]["PreToolUse"][0]
            self.assertIn("Bash", entry["matcher"])
            self.assertTrue(entry["hooks"][0]["command"].endswith("/footgun-hook"))
