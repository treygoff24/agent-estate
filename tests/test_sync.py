"""The sync module: repo table against local bare remotes, hooks, status file,
rendered units and check statuses. systemctl and launchctl are faked on PATH."""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from tests.helpers import ROOT, TempHome

SYNC = ROOT / "modules" / "sync" / "estate-sync"
FAKE_SYSTEMCTL = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
case "$*" in
  *is-enabled*|*is-active*) [ -f "$FAKE_LOADED" ] ;;
  *"enable --now"*) touch "$FAKE_LOADED" ;;
  *"disable --now"*) rm -f "$FAKE_LOADED" ;;
esac
"""
FAKE_LAUNCHCTL = """#!/usr/bin/env bash
echo "launchctl $*" >> "$FAKE_LOG"
case "$1" in
  list) [ -f "$FAKE_LOADED" ] ;;
  bootstrap) touch "$FAKE_LOADED" ;;
  bootout) rm -f "$FAKE_LOADED" ;;
esac
"""
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def git(cwd, *args):
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                       env=os.environ | GIT_ENV)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


class SyncBase(TempHome):
    def setUp(self):
        super().setUp()
        self.remotes = self.tmp / "remotes"
        self.code = self.tmp / "code"
        self.bin = self.tmp / "bin"
        self.remotes.mkdir()
        fake = self.tmp / "fakebin"
        fake.mkdir()
        for name, body in (("systemctl", FAKE_SYSTEMCTL), ("launchctl", FAKE_LAUNCHCTL)):
            (fake / name).write_text(body)
            (fake / name).chmod(0o755)
        self.log = self.tmp / "fake.log"
        self.loaded = self.tmp / "loaded"
        self.env = {"PATH": f"{fake}:{os.environ['PATH']}", "FAKE_LOG": str(self.log),
                    "FAKE_LOADED": str(self.loaded), "ESTATE_PLATFORM": "linux"} | GIT_ENV
        self.table = self.tmp / "repos.tsv"
        self.status_file = self.state / "sync" / "status.json"

    def config(self, extra=""):
        self.write_config(["sync"], extra)
        text = self.cfg_path.read_text()
        text = text.replace('remote_base = "git@github.com:example"',
                            f'remote_base = "{self.remotes}"')
        text = text.replace("[paths]\n", f'[paths]\ncode = "{self.code}"\nbin = "{self.bin}"\n')
        text += f'\n[modules.sync]\nrepos_file = "{self.table}"\n' if "[modules.sync]" not in extra else ""
        if "[modules.sync]" in extra:
            text = text.replace("[modules.sync]\n", f'[modules.sync]\nrepos_file = "{self.table}"\n')
        self.cfg_path.write_text(text)

    def make_remote(self, name, files=None):
        """A bare remote with one commit; returns a scratch clone to push more from."""
        bare = self.remotes / f"{name}.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
        work = self.tmp / "work" / name
        subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True,
                       capture_output=True)
        self.commit(work, "a.txt", "one")
        return work

    def commit(self, work, fname, text):
        (work / fname).write_text(text)
        git(work, "add", fname)
        git(work, "commit", "-q", "-m", f"edit {fname}")
        git(work, "push", "-q", "origin", "HEAD:main")

    def sync(self, **env):
        return subprocess.run([str(SYNC)], capture_output=True, text=True,
                              env=os.environ | self.env | env, stdin=subprocess.DEVNULL)

    def status(self):
        return json.loads(self.status_file.read_text())


class RepoTable(SyncBase):
    def test_clone_missing_then_fast_forward(self):
        work = self.make_remote("alpha")
        self.table.write_text("# comment\nalpha\n")
        self.config()
        p = self.sync()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.code / "alpha" / "a.txt").read_text(), "one")
        self.assertEqual(self.status()["repos"]["alpha"]["status"], "ok")
        self.assertEqual(self.status()["repos"]["alpha"]["reason"], "cloned")

        self.commit(work, "a.txt", "two")
        p = self.sync()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.code / "alpha" / "a.txt").read_text(), "two")

        p = self.sync()
        self.assertEqual(self.status()["repos"]["alpha"]["reason"], "up to date")

    def test_dirty_checkout_skipped_untouched(self):
        work = self.make_remote("alpha")
        self.table.write_text("alpha\n")
        self.config()
        self.sync()
        mine = self.code / "alpha" / "a.txt"
        mine.write_text("my unsaved edit")
        self.commit(work, "a.txt", "two")
        head = git(self.code / "alpha", "rev-parse", "HEAD")
        p = self.sync()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        r = self.status()["repos"]["alpha"]
        self.assertEqual(r["status"], "skipped")
        self.assertIn("uncommitted", r["reason"])
        self.assertEqual(mine.read_text(), "my unsaved edit")
        self.assertEqual(git(self.code / "alpha", "rev-parse", "HEAD"), head)

    def test_diverged_checkout_skipped(self):
        work = self.make_remote("alpha")
        self.table.write_text("alpha\n")
        self.config()
        self.sync()
        local = self.code / "alpha"
        (local / "b.txt").write_text("local")
        git(local, "add", "b.txt")
        git(local, "commit", "-q", "-m", "local")
        head = git(local, "rev-parse", "HEAD")
        self.commit(work, "a.txt", "two")
        self.sync()
        r = self.status()["repos"]["alpha"]
        self.assertEqual(r["status"], "skipped")
        self.assertIn("diverged", r["reason"])
        self.assertEqual(git(local, "rev-parse", "HEAD"), head)

    def test_install_runs_only_on_change(self):
        work = self.make_remote("alpha")
        marks = self.tmp / "marks"
        self.table.write_text(
            f'alpha\t-\techo "$ESTATE_SYNC_NAME $ESTATE_SYNC_BEFORE" >> {marks}\n')
        self.config()
        self.sync()  # fresh clone counts as a change
        self.assertEqual(len(marks.read_text().splitlines()), 1)
        self.sync()  # nothing new
        self.assertEqual(len(marks.read_text().splitlines()), 1)
        self.commit(work, "a.txt", "two")
        self.sync()
        lines = marks.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[1].split()[1], git(work, "rev-parse", "HEAD~1"))

    def test_install_failure_and_defer(self):
        work = self.make_remote("alpha")
        self.make_remote("beta")
        self.table.write_text("alpha\t-\texit 3\nbeta\t-\texit 75\n")
        self.config()
        p = self.sync()
        self.assertEqual(p.returncode, 1)
        st = self.status()
        self.assertEqual(st["repos"]["alpha"]["status"], "failed")
        self.assertEqual(st["repos"]["beta"]["status"], "skipped")
        self.assertFalse(st["ok"])
        # failed/deferred installs retry next run even though HEAD did not move
        self.table.write_text("alpha\t-\ttrue\nbeta\t-\ttrue\n")
        p = self.sync()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(self.status()["ok"])
        del work

    def test_clone_failure_is_failed_and_others_continue(self):
        self.make_remote("beta")
        self.table.write_text("ghost\nbeta\n")
        self.config()
        p = self.sync()
        self.assertEqual(p.returncode, 1)
        st = self.status()
        self.assertEqual(st["repos"]["ghost"]["status"], "failed")
        self.assertEqual(st["repos"]["beta"]["status"], "ok")


class Hooks(SyncBase):
    def test_order_and_failure_propagation(self):
        order = self.tmp / "order"
        self.table.write_text("")
        self.config(f'\n[modules.sync]\nhooks = ["echo one >> {order}", "exit 4", '
                    f'"echo three >> {order}"]\n')
        p = self.sync()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(order.read_text().split(), ["one", "three"])  # a failure does not stop later hooks
        hooks = self.status()["hooks"]
        self.assertEqual([h["status"] for h in hooks], ["ok", "failed", "ok"])
        self.assertFalse(self.status()["ok"])

    def test_hooks_run_after_repos(self):
        self.make_remote("alpha")
        self.table.write_text("alpha\n")
        self.config(f'\n[modules.sync]\nhooks = ["test -f {self.code}/alpha/a.txt"]\n')
        p = self.sync()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


class Module(SyncBase):
    def estate_run(self, *args):
        return self.estate(*args, env=self.env)

    def rendered(self, kind):
        label = "com.example.estate.sync"
        return {"service": self.home / f".config/systemd/user/{label}.service",
                "timer": self.home / f".config/systemd/user/{label}.timer",
                "plist": self.home / f"Library/LaunchAgents/{label}.plist"}[kind]

    def test_linux_install_check_uninstall(self):
        self.config('\n[modules.sync]\nhour = 5\nminute = 30\n')
        p = self.estate_run("install", "--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(self.rendered("timer").exists())
        self.assertFalse(self.log.exists())

        p = self.estate_run("install")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        timer = self.rendered("timer").read_text()
        self.assertIn("OnCalendar=*-*-* 5:30:00", timer)
        self.assertIn("Unit=com.example.estate.sync.service", timer)
        self.assertIn(f"ExecStart={self.bin}/estate-sync", self.rendered("service").read_text())
        self.assertTrue((self.bin / "estate-sync").is_symlink())
        self.assertTrue(self.table.exists())
        self.assertEqual(self.estate_run("install").returncode, 0)  # idempotent

        # never run yet -> fail
        row = self.check_row()
        self.assertEqual(row["status"], 1, row)
        self.assertIn("no sync has run", row["summary"])

        self.make_remote("alpha")
        self.table.write_text("alpha\n")
        self.assertEqual(self.sync().returncode, 0)
        row = self.check_row()
        self.assertEqual(row["status"], 0, row)
        self.assertIn("daily at 05:30", row["summary"])

        # skipped repo -> warn
        (self.code / "alpha" / "a.txt").write_text("dirty")
        self.sync()
        row = self.check_row()
        self.assertEqual(row["status"], 2, row)
        self.assertIn("alpha", row["summary"])

        # failed run -> fail
        self.table.write_text("ghost\n")
        self.sync()
        self.assertEqual(self.check_row()["status"], 1)

        # stale -> fail
        self.table.write_text("")
        self.sync()
        st = self.status()
        st["finished"] = (datetime.now(timezone.utc) - timedelta(hours=40)).isoformat()
        self.status_file.write_text(json.dumps(st))
        row = self.check_row()
        self.assertEqual(row["status"], 1)
        self.assertIn("40h ago", row["summary"])

        # timer not loaded -> fail
        self.loaded.unlink()
        row = self.check_row()
        self.assertEqual(row["status"], 1)
        self.assertIn("not enabled", row["summary"])

        # drift from estate.toml -> fail
        self.estate_run("install")
        self.config('\n[modules.sync]\nhour = 6\n')
        self.assertIn("does not match", self.check_row()["summary"])

        p = self.estate_run("uninstall", "sync")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(self.rendered("timer").exists() or self.rendered("service").exists())
        self.assertFalse((self.bin / "estate-sync").exists())

    def check_row(self):
        p = self.estate_run("doctor", "--json")
        return {r["name"]: r for r in json.loads(p.stdout)["checks"]}["sync"]

    def test_mac_plist(self):
        self.env["ESTATE_PLATFORM"] = "mac"
        self.config()
        p = self.estate_run("install")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        plist = self.rendered("plist").read_text()
        self.assertIn("<string>com.example.estate.sync</string>", plist)
        self.assertIn("<key>Hour</key>\n    <integer>4</integer>", plist)
        self.assertIn(f"<string>{self.bin}/estate-sync</string>", plist)
        self.assertIn("launchctl bootstrap", self.log.read_text())
        self.make_remote("alpha")
        self.table.write_text("alpha\n")
        self.sync()
        row = self.check_row()
        self.assertEqual(row["status"], 0, row)
        self.assertEqual(self.estate_run("uninstall", "sync").returncode, 0)
        self.assertFalse(self.rendered("plist").exists())

    def test_bad_hour_refused(self):
        self.config('\n[modules.sync]\nhour = 25\n')
        p = self.estate_run("install")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("modules.sync.hour", p.stderr + p.stdout)
