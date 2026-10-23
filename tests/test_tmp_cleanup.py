"""The one real module, end to end through the CLI, with systemctl and
systemd-tmpfiles faked on PATH (so it runs on a Mac too). Whether real
systemd honours the rendered files is checked by hand on a Linux box."""

import json
import os

from tests.helpers import TempHome

FAKE_SYSTEMCTL = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
case "$*" in
  *is-enabled*|*is-active*) [ -f "$FAKE_TIMER_ON" ] ;;
  *"enable --now"*) touch "$FAKE_TIMER_ON" ;;
esac
"""


class TmpCleanupLinux(TempHome):
    def setUp(self):
        super().setUp()
        fake = self.tmp / "fakebin"
        fake.mkdir()
        for name, body in (("systemctl", FAKE_SYSTEMCTL), ("systemd-tmpfiles", "#!/bin/sh\n")):
            (fake / name).write_text(body)
            (fake / name).chmod(0o755)
        self.log = self.tmp / "systemctl.log"
        self.env = {"ESTATE_PLATFORM": "linux", "PATH": f"{fake}:{os.environ['PATH']}",
                    "FAKE_LOG": str(self.log), "FAKE_TIMER_ON": str(self.tmp / "timer-on")}
        self.label = "com.example.estate.tmp-cleanup"
        self.conf = self.home / ".config/user-tmpfiles.d" / f"{self.label}.conf"
        self.dropin = (self.home / ".config/systemd/user/systemd-tmpfiles-clean.timer.d"
                       / f"{self.label}.conf")

    def run_estate(self, *args):
        return self.estate(*args, env=self.env)

    def test_install_check_drift_uninstall(self):
        self.write_config(["tmp-cleanup"], '\n[modules.tmp-cleanup]\nage = "12h"\n')

        p = self.run_estate("doctor")
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("not installed", p.stdout)

        self.log.unlink(missing_ok=True)
        p = self.run_estate("install", "--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("would write", p.stderr)
        self.assertIn("would run: systemctl --user enable --now", p.stderr)
        self.assertFalse(self.conf.exists() or self.dropin.exists())
        self.assertFalse(self.log.exists())  # dry run never called systemctl

        p = self.run_estate("install")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("e /tmp - - - 12h\n", self.conf.read_text())
        self.assertIn("OnUnitActiveSec=1h", self.dropin.read_text())
        self.assertIn("--user enable --now systemd-tmpfiles-clean.timer", self.log.read_text())
        p = self.run_estate("install")  # idempotent
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

        # check passes; doctor's other rows (systemd user manager, linger) come
        # from the fake systemctl/loginctl and are not what this test is about.
        p = self.run_estate("install", "--dry-run")
        self.assertIn("unchanged:", p.stderr)
        p = self.run_estate("doctor", "--json")
        rows = {r["name"]: r for r in json.loads(p.stdout)["checks"]}
        self.assertEqual(rows["tmp-cleanup"]["status"], 0, rows["tmp-cleanup"])
        self.assertEqual(rows["tmp-cleanup"]["summary"], "/tmp ages out after 12h (hourly sweep)")

        self.write_config(["tmp-cleanup"], '\n[modules.tmp-cleanup]\nage = "2d"\n')
        rows = {r["name"]: r for r in json.loads(self.run_estate("doctor", "--json").stdout)
                ["checks"]}
        self.assertEqual(rows["tmp-cleanup"]["status"], 1)
        self.assertIn("does not match estate.toml", rows["tmp-cleanup"]["summary"])

        p = self.run_estate("uninstall", "tmp-cleanup")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(self.conf.exists() or self.dropin.exists())

    def test_bad_age_refused(self):
        self.write_config(["tmp-cleanup"], '\n[modules.tmp-cleanup]\nage = "forever"\n')
        p = self.run_estate("install")
        self.assertEqual(p.returncode, 1)
        self.assertIn("not an age", p.stderr)
        self.assertFalse(self.conf.exists())

    def test_mac_check_passes_without_systemd(self):
        self.write_config(["tmp-cleanup"])
        p = self.estate("doctor", "--json", env={"ESTATE_PLATFORM": "mac"})
        rows = {r["name"]: r for r in json.loads(p.stdout)["checks"]}
        self.assertEqual(rows["tmp-cleanup"]["status"], 0)
