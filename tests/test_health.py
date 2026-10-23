from datetime import datetime, timedelta, timezone
"""health module, end to end through the CLI and the collector, with systemctl,
launchctl, loginctl and ps faked on PATH. Nothing touches the real home or units."""

import json
import os
import subprocess
import time
from pathlib import Path

from tests.helpers import ROOT, PinnedPythonMac, TempHome

HEALTH = ROOT / "modules" / "health" / "estate-health"

FAKE_SYSTEMCTL = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
case "$*" in
  *is-system-running*) echo running ;;
  *list-units*) cat "$FAKE_FAILED" 2>/dev/null; exit 0 ;;
  *is-enabled*|*is-active*) [ -f "$FAKE_TIMER_ON" ] ;;
  *"enable --now"*) touch "$FAKE_TIMER_ON" ;;
esac
exit 0
"""
FAKE_LOGINCTL = "#!/bin/sh\necho yes\n"
FAKE_PS = "#!/bin/sh\ncat \"$FAKE_PS_OUT\" 2>/dev/null\n"
UNIT = "com.example.estate.health.service"


class HealthBase(TempHome):
    def setUp(self):
        super().setUp()
        fake = self.tmp / "fakebin"
        fake.mkdir()
        for name, body in (("systemctl", FAKE_SYSTEMCTL), ("loginctl", FAKE_LOGINCTL),
                           ("ps", FAKE_PS)):
            (fake / name).write_text(body)
            (fake / name).chmod(0o755)
        self.failed = self.tmp / "failed-units"
        self.ps_out = self.tmp / "ps-out"
        self.proc = self.tmp / "proc"
        self.proc.mkdir()
        (self.proc / "meminfo").write_text("MemTotal: 1000 kB\nMemAvailable: 900 kB\n")
        self.log = self.tmp / "systemctl.log"
        self.env = {"ESTATE_PLATFORM": "linux", "PATH": f"{fake}:{os.environ['PATH']}",
                    "FAKE_LOG": str(self.log), "FAKE_TIMER_ON": str(self.tmp / "timer-on"),
                    "FAKE_FAILED": str(self.failed), "FAKE_PS_OUT": str(self.ps_out),
                    "ESTATE_HEALTH_PROC": str(self.proc)}
        # thresholds high enough that a healthy fake box is ok whatever the real disk says
        self.quiet = ('\n[modules.health]\ndisk_warn = 101\ndisk_crit = 102\n')
        self.hdir = self.state / "health"

    def collect(self, *args):
        e = dict(os.environ) | self.env
        return subprocess.run(["python3", str(HEALTH), *args], capture_output=True, text=True,
                              env=e, stdin=subprocess.DEVNULL)

    def report(self, *args):
        p = self.collect("--json", *args)
        return p, json.loads(p.stdout)

    @staticmethod
    def by_id(r):
        return {c["id"]: c for c in r["checks"]}


class HealthCollector(HealthBase):
    def test_json_shape_and_ok_baseline(self):
        self.write_config(["health"], self.quiet)
        p, r = self.report()
        ids = self.by_id(r)
        self.assertEqual(set(ids), {"disk", "memory", "units", "doctor", "sync",
                                    "runaway_processes", "stale_worktrees"})
        for c in r["checks"]:
            self.assertEqual(set(c), {"id", "severity", "summary", "detail", "fix_hint"})
        self.assertEqual(ids["memory"]["severity"], "ok")
        self.assertEqual(ids["sync"]["severity"], "unknown")  # sync module absent: tolerated
        self.assertEqual({"version", "generated_at", "severity", "attention", "checks",
                          "since_ack"} <= set(r), True)
        # exit code = worst severity (doctor warns about the not-yet-installed health module)
        want = {"ok": 0, "unknown": 0, "warn": 1, "crit": 2}[r["severity"]]
        self.assertEqual(p.returncode, want)
        self.assertTrue((self.hdir / "latest.json").is_file())

    def test_severity_aggregation_and_exit_code(self):
        # disk is crit (threshold 1%): whole report is crit and exit is 2
        self.write_config(["health"], '\n[modules.health]\ndisk_warn = 0.5\ndisk_crit = 1\n')
        p, r = self.report()
        self.assertEqual(self.by_id(r)["disk"]["severity"], "crit")
        self.assertEqual(r["severity"], "crit")
        self.assertEqual(p.returncode, 2)
        self.assertTrue(r["attention"])
        # a warn-only report exits 1: failed unit with this estate's prefix, a foreign one ignored
        self.write_config(["health"], '\n[modules.health]\ndisk_warn = 101\ndisk_crit = 102\n'
                                      'mem_warn = 101\nmem_crit = 102\n')
        self.failed.write_text(f"{UNIT} loaded failed failed estate health\n"
                               "unrelated.service loaded failed failed other\n")
        p, r = self.report()
        u = self.by_id(r)["units"]
        self.assertEqual(u["severity"], "warn")
        self.assertEqual(u["detail"]["failed"], [UNIT])
        self.assertGreaterEqual(p.returncode, 1)
        self.assertEqual(r["severity"], "crit" if self.by_id(r)["doctor"]["severity"] == "crit" else "warn")

    def test_memory_crit_from_proc(self):
        self.write_config(["health"], self.quiet)
        (self.proc / "meminfo").write_text("MemTotal: 1000 kB\nMemAvailable: 20 kB\n")
        _, r = self.report()
        self.assertEqual(self.by_id(r)["memory"]["severity"], "crit")

    def test_runaway_process_reported_not_signalled(self):
        self.write_config(["health"], self.quiet)
        self.ps_out.write_text("  4242  02:10:00  97.5 busy-loop\n  4243  00:01:00  99.0 young\n"
                               "  4244  1-00:00:00  1.0 idle\n")
        _, r = self.report()
        c = self.by_id(r)["runaway_processes"]
        self.assertEqual(c["severity"], "warn")
        self.assertEqual([h["pid"] for h in c["detail"]["processes"]], [4242])

    def test_mac_memory_parses_real_vm_stat_output(self):
        fake = self.tmp / "fakebin"
        (fake / "vm_stat").write_text(
            "#!/bin/sh\ncat <<'X'\n"
            "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
            "Pages free:                               100000.\n"
            "Pages active:                             300000.\n"
            "Pages inactive:                           100000.\n"
            "Pages speculative:                             0.\n"
            "Pages purgeable:                               0.\n"
            "Swapins:                                       0.\n"
            "X\n")
        (fake / "sysctl").write_text("#!/bin/sh\necho 16384000000\n")  # 1,000,000 pages
        for n in ("vm_stat", "sysctl"):
            (fake / n).chmod(0o755)
        self.write_config(["health"], self.quiet)
        self.env["ESTATE_PLATFORM"] = "mac"
        _, r = self.report()
        mem = self.by_id(r)["memory"]
        self.assertNotEqual(mem["severity"], "unknown", mem["summary"])
        self.assertIn("80", mem["summary"])  # 200,000 of 1,000,000 pages available

    def test_sync_state_read_when_present(self):
        # Writes the sync module's real status.json and lets estate-sync --status judge it.
        self.write_config(["health"], self.quiet)
        sync = self.state / "sync"
        sync.mkdir(parents=True)
        def status(ok, hours_ago=1, repos=None):
            finished = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
            (sync / "status.json").write_text(json.dumps(
                {"ok": ok, "finished": finished.isoformat(), "repos": repos or {}, "hooks": []}))
        status(False, repos={"a": {"status": "failed", "reason": "fetch failed"}})
        _, r = self.report()
        self.assertEqual(self.by_id(r)["sync"]["severity"], "warn")
        self.assertIn("a", self.by_id(r)["sync"]["summary"])
        status(True)
        _, r = self.report()
        self.assertEqual(self.by_id(r)["sync"]["severity"], "ok")
        status(True, hours_ago=40)
        _, r = self.report()
        self.assertEqual(self.by_id(r)["sync"]["severity"], "warn")  # too old

    def test_stale_worktree_found(self):
        self.write_config(["health"], self.quiet)
        repo = self.home / "Code" / "proj"
        repo.mkdir(parents=True)
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-C", str(repo)]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "x"], check=True)
        wt = self.home / "Code" / "proj-worktrees" / "feat"
        subprocess.run([*git, "worktree", "add", "-q", str(wt), "-b", "feat"], check=True)
        _, r = self.report()
        self.assertEqual(self.by_id(r)["stale_worktrees"]["severity"], "ok")  # fresh survives
        old = time.time() - 60 * 86400
        gd = repo / ".git" / "worktrees" / "feat"
        for f in gd.rglob("*"):
            if f.is_file():
                os.utime(f, (old, old))
        _, r = self.report()
        c = self.by_id(r)["stale_worktrees"]
        self.assertEqual(c["severity"], "warn")
        self.assertEqual(Path(c["detail"]["worktrees"][0]["path"]).resolve(), wt.resolve())


class HealthAck(HealthBase):
    def test_ack_marks_known_and_new_findings_surface(self):
        self.write_config(["health"], self.quiet)
        self.failed.write_text(f"{UNIT} loaded failed failed x\n")
        _, r = self.report()
        self.assertIn("units", r["since_ack"]["new"])
        self.assertIsNone(r["since_ack"]["acked_at"])

        p = self.collect("ack", "--by", "tester")
        self.assertEqual(p.returncode, 0, p.stderr)
        ack = json.loads((self.hdir / "ack.json").read_text())
        self.assertEqual(ack["by"], "tester")
        self.assertIn("units", ack["known"])

        _, r = self.report()
        self.assertEqual(r["since_ack"]["new"], [])        # known now
        self.assertEqual(r["since_ack"]["acked_by"], "tester")
        self.assertNotIn("units", r["since_ack"]["new"])

        # something new shows up after the ack: only it is new
        self.ps_out.write_text("  4242  02:10:00  97.5 busy-loop\n")
        _, r = self.report()
        self.assertEqual(r["since_ack"]["new"], ["runaway_processes"])

        # the old finding clears: listed as resolved
        self.failed.write_text("")
        _, r = self.report()
        self.assertIn("units", r["since_ack"]["resolved"])

    def test_crit_stays_in_attention_after_ack(self):
        self.write_config(["health"], '\n[modules.health]\ndisk_warn = 0.5\ndisk_crit = 1\n')
        self.collect()
        self.collect("ack")
        _, r = self.report()
        self.assertNotIn("disk", r["since_ack"]["new"])
        self.assertTrue(r["attention"])

    def test_show_without_cache_exits_3_and_quiet_always_zero(self):
        self.write_config(["health"], '\n[modules.health]\ndisk_warn = 0.5\ndisk_crit = 1\n')
        self.assertEqual(self.collect("show").returncode, 3)
        p = self.collect("--quiet")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        p = self.collect("show", "--json")
        self.assertEqual(p.returncode, 2)  # cached report was crit
        self.assertEqual(json.loads(p.stdout)["severity"], "crit")

    def test_collect_is_read_only(self):
        self.write_config(["health"], self.quiet)
        self.collect()
        calls = self.log.read_text() if self.log.exists() else ""
        for verb in ("start", "stop", "restart", "reset-failed", "enable", "disable"):
            self.assertNotIn(verb, calls)


class HealthInstall(PinnedPythonMac, HealthBase):
    module, output = "health", "health/latest.json"

    def prepare(self):
        self.write_config(["health"], self.quiet)

    def setUp(self):
        super().setUp()
        self.label = "com.example.estate.health"
        self.unit_dir = self.home / ".config/systemd/user"

    def estate_run(self, *args):
        return self.estate(*args, env=self.env)

    def test_install_check_stale_uninstall(self):
        self.write_config(["health"])
        p = self.estate_run("doctor", "--json")
        rows = {r["name"]: r for r in json.loads(p.stdout)["checks"]}
        self.assertEqual(rows["health"]["status"], 1)

        p = self.estate_run("install", "--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("would link", p.stderr)
        self.assertFalse((self.unit_dir / f"{self.label}.timer").exists())

        p = self.estate_run("install")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue((self.home / ".local/bin/estate-health").is_symlink())
        self.assertIn("OnCalendar=*-*-* *:07:00", (self.unit_dir / f"{self.label}.timer").read_text())
        self.assertIn(f"{self.home}/.local/bin/estate-health --quiet",
                      (self.unit_dir / f"{self.label}.service").read_text())
        self.assertEqual(self.estate_run("install").returncode, 0)  # idempotent

        rows = {r["name"]: r for r in json.loads(self.estate_run("doctor", "--json").stdout)["checks"]}
        self.assertEqual(rows["health"]["status"], 0, rows["health"])

        # the job stopped running: a three-hour-old report fails the check
        latest = self.state / "health" / "latest.json"
        old = time.time() - 3 * 3600
        os.utime(latest, (old, old))
        rows = {r["name"]: r for r in json.loads(self.estate_run("doctor", "--json").stdout)["checks"]}
        self.assertEqual(rows["health"]["status"], 1)
        self.assertIn("not running", rows["health"]["summary"])

        p = self.estate_run("uninstall", "health")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse((self.unit_dir / f"{self.label}.timer").exists())
        self.assertFalse((self.home / ".local/bin/estate-health").exists())

    def test_the_scheduled_jobs_path_puts_the_key_shims_first(self):
        # the doctor inside the scheduled report warns "keys: add: export PATH=..." unless the
        # shim folder precedes paths.bin on the job's own PATH
        shims = f"{self.home}/.local/bin/estate-shims"
        self.write_config(["health"])
        self.assertEqual(self.estate_run("install").returncode, 0)
        svc = (self.unit_dir / f"{self.label}.service").read_text()
        self.assertIn(f"Environment=PATH={shims}:{self.home}/.local/bin:", svc)
        # a customised shim_dir is followed, and `~` is expanded (a unit cannot expand it)
        self.write_config(["health"], '\n[modules.keys]\nshim_dir = "~/shims"\n')
        self.assertEqual(self.estate_run("install").returncode, 0)
        svc = (self.unit_dir / f"{self.label}.service").read_text()
        self.assertIn(f"Environment=PATH={self.home}/shims:{self.home}/.local/bin:", svc)

    def test_mac_install_renders_plist(self):
        self.write_config(["health"])
        fake = self.tmp / "macbin"
        fake.mkdir()
        (fake / "launchctl").write_text('#!/bin/sh\necho "$*" >> "$FAKE_LOG"\n'
                                        '[ "$1" = print ] && [ -f "$FAKE_LOADED" ]\n'
                                        '[ "$1" = bootstrap ] && touch "$FAKE_LOADED"\nexit 0\n')
        (fake / "launchctl").chmod(0o755)
        env = self.env | {"ESTATE_PLATFORM": "mac", "PATH": f"{fake}:{self.env['PATH']}",
                          "FAKE_LOADED": str(self.tmp / "loaded")}
        plist = self.home / "Library/LaunchAgents" / f"{self.label}.plist"
        p = self.estate("install", env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("<integer>7</integer>", plist.read_text())
        self.assertIn(f"<string>{self.home}/.local/bin/estate-shims:{self.home}/.local/bin:/opt/homebrew/bin",
                      plist.read_text())
        self.assertIn("bootstrap", self.log.read_text())
        rows = {r["name"]: r for r in json.loads(self.estate("doctor", "--json", env=env).stdout)["checks"]}
        self.assertEqual(rows["health"]["status"], 0, rows["health"])
