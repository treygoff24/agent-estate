"""cleanup module: age-gated deletion, report-only orphans, events, install/check.
systemctl, loginctl and ps are faked on PATH; nothing touches the real home."""

import json
import os
import re
import subprocess
import time
from pathlib import Path

from tests.helpers import ROOT, PinnedPythonMac, TempHome

CLEANUP = ROOT / "modules" / "cleanup" / "estate-cleanup"
FAKE_SYSTEMCTL = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
case "$*" in
  *is-system-running*) echo running ;;
  *is-enabled*|*is-active*) [ -f "$FAKE_TIMER_ON" ] ;;
  *"enable --now"*) touch "$FAKE_TIMER_ON" ;;
esac
exit 0
"""
DAY = 86400


def age(path, days):
    """Make a file or a whole tree look `days` old."""
    t = time.time() - days * DAY
    p = Path(path)
    items = [p, *p.rglob("*")] if p.is_dir() else [p]
    for i in items:
        os.utime(i, (t, t), follow_symlinks=False)
    if p.is_dir():
        os.utime(p, (t, t))


class CleanupBase(TempHome):
    def setUp(self):
        super().setUp()
        fake = self.tmp / "fakebin"
        fake.mkdir()
        for name, body in (("systemctl", FAKE_SYSTEMCTL), ("loginctl", "#!/bin/sh\necho yes\n"),
                           ("ps", '#!/bin/sh\ncat "$FAKE_PS_OUT" 2>/dev/null\n')):
            (fake / name).write_text(body)
            (fake / name).chmod(0o755)
        self.ps_out = self.tmp / "ps-out"
        self.proc = self.tmp / "proc"
        self.proc.mkdir()
        self.log = self.tmp / "systemctl.log"
        self.env = {"ESTATE_PLATFORM": "linux", "PATH": f"{fake}:{os.environ['PATH']}",
                    "FAKE_LOG": str(self.log), "FAKE_TIMER_ON": str(self.tmp / "timer-on"),
                    "FAKE_PS_OUT": str(self.ps_out), "ESTATE_CLEANUP_PROC": str(self.proc)}
        self.code = self.home / "Code"
        self.code.mkdir()
        self.write_config(["cleanup"])

    def run_cleanup(self, *args):
        e = dict(os.environ) | self.env
        return subprocess.run(["python3", str(CLEANUP), *args], capture_output=True, text=True,
                              env=e, stdin=subprocess.DEVNULL)

    def events(self):
        out = []
        for f in sorted((self.state / "cleanup").glob("events-*.jsonl")):
            out += [json.loads(ln) for ln in f.read_text().splitlines()]
        return out

    def kinds(self, kind):
        return [e for e in self.events() if e["kind"] == kind]

    def mkproject(self, name, files=("Cargo.toml",), build="target"):
        proj = self.code / name
        proj.mkdir()
        for f in files:
            (proj / f).write_text("x")
        (proj / build).mkdir()
        (proj / build / "artifact.o").write_text("y" * 1000)
        return proj


class CleanupSweeps(CleanupBase):
    def test_only_old_matching_caches_are_removed(self):
        old = self.mkproject("old")
        fresh = self.mkproject("fresh")
        no_manifest = self.mkproject("plain", files=())     # target/ with no Cargo.toml
        node = self.mkproject("web", files=("package.json",), build="node_modules")
        for p in (old / "target", node / "node_modules", no_manifest / "target", fresh / "target"):
            age(p, 60)
        (fresh / "target" / "artifact.o").write_text("touched just now")   # live build output

        p = self.run_cleanup("run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse((old / "target").exists())
        self.assertFalse((node / "node_modules").exists())
        self.assertTrue((fresh / "target").exists(), "a recently modified cache must survive")
        self.assertTrue((no_manifest / "target").exists(), "no manifest beside it: not provably a cache")
        deleted = {e["path"] for e in self.kinds("deleted")}
        self.assertEqual(deleted, {str(old / "target"), str(node / "node_modules")})
        self.assertTrue(all(e["bytes"] >= 1000 for e in self.kinds("deleted")))

    def test_dry_run_deletes_nothing_but_says_what_it_would(self):
        old = self.mkproject("old")
        age(old / "target", 60)
        p = self.run_cleanup("run", "--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((old / "target" / "artifact.o").exists())
        self.assertEqual(len(self.kinds("would-delete")), 1)
        self.assertEqual(self.kinds("deleted"), [])
        self.assertFalse((self.state / "cleanup" / "last-run.json").exists())

    def test_symlinked_cache_is_never_followed(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "precious").write_text("keep")
        proj = self.code / "linked"
        proj.mkdir()
        (proj / "Cargo.toml").write_text("x")
        (proj / "target").symlink_to(outside)
        age(outside, 90)
        self.run_cleanup("run")
        self.assertTrue((outside / "precious").exists())

    def test_logs_age_gated_under_state_and_extra_dirs(self):
        extra = self.tmp / "extra-logs"
        extra.mkdir()
        self.write_config(["cleanup"], f'\n[modules.cleanup]\nlog_dirs = ["{extra}"]\n')
        sub = self.state / "sync"
        sub.mkdir(parents=True)
        files = {sub / "old.log": 40, sub / "old.log.1": 40, sub / "new.log": 1,
                 sub / "keep.txt": 400, extra / "old.log": 40, extra / "new.log": 0}
        for f, d in files.items():
            f.write_text("x")
            age(f, d)
        self.run_cleanup("run")
        for f in (sub / "old.log", sub / "old.log.1", extra / "old.log"):
            self.assertFalse(f.exists(), f)
        for f in (sub / "new.log", sub / "keep.txt", extra / "new.log"):
            self.assertTrue(f.exists(), f)

    def test_own_old_event_files_rotate(self):
        d = self.state / "cleanup"
        d.mkdir(parents=True)
        (d / "events-20200101.jsonl").write_text("{}\n")
        age(d / "events-20200101.jsonl", 200)
        self.run_cleanup("run")
        self.assertFalse((d / "events-20200101.jsonl").exists())
        self.assertTrue(list(d.glob("events-2*.jsonl")))   # today's file is there

    def test_bad_age_refused_before_deleting(self):
        old = self.mkproject("old")
        age(old / "target", 60)
        self.write_config(["cleanup"], '\n[modules.cleanup]\ncache_age = "soon"\n')
        p = self.run_cleanup("run")
        self.assertNotEqual(p.returncode, 0)
        self.assertTrue((old / "target").exists())


class CleanupWorktrees(CleanupBase):
    def setUp(self):
        super().setUp()
        self.repo = self.code / "proj"
        self.repo.mkdir()
        self.git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-C", str(self.repo)]
        subprocess.run([*self.git, "init", "-q"], check=True)
        subprocess.run([*self.git, "commit", "-q", "--allow-empty", "-m", "x"], check=True)
        self.scratch = self.code / "proj-worktrees"

    def add(self, name, parent=None):
        wt = (parent or self.scratch) / name
        subprocess.run([*self.git, "worktree", "add", "-q", str(wt), "-b", name], check=True)
        return wt

    def make_old(self, wt, days=30):
        gd = self.repo / ".git" / "worktrees" / wt.name
        age(gd, days)
        age(wt, days)

    def test_only_stale_clean_scratch_worktrees_go(self):
        stale = self.add("stale")
        dirty = self.add("dirty")
        fresh = self.add("fresh")
        elsewhere = self.add("elsewhere", parent=self.code / "not-scratch-shaped")
        (dirty / "notes.txt").write_text("uncommitted work")
        for wt in (stale, dirty, elsewhere):
            self.make_old(wt)
        # the dirty file is new, so age it back too: dirtiness, not recency, must keep it
        age(dirty / "notes.txt", 30)
        self.make_old(dirty)

        p = self.run_cleanup("run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(stale.exists())
        self.assertTrue(dirty.exists(), "uncommitted work must survive")
        self.assertTrue(fresh.exists(), "a fresh worktree must survive")
        self.assertTrue(elsewhere.exists(), "not in a scratch location")
        self.assertEqual([Path(e["path"]).resolve() for e in self.kinds("deleted")], [stale.resolve()])
        self.assertTrue(any(e["reason"] == "dirty" for e in self.kinds("kept")))
        branches = subprocess.run([*self.git, "branch", "--list", "stale"], capture_output=True,
                                  text=True).stdout
        self.assertIn("stale", branches, "the branch is kept")

    def test_missing_worktree_record_is_pruned_and_dry_run_is_inert(self):
        gone = self.add("gone")
        subprocess.run(["rm", "-rf", str(gone)], check=True)
        self.run_cleanup("run", "--dry-run")
        self.assertIn("gone", (self.repo / ".git" / "worktrees").iterdir().__next__().name)
        self.assertEqual(len(self.kinds("would-prune")), 1)
        self.run_cleanup("run")
        self.assertFalse((self.repo / ".git" / "worktrees" / "gone").exists())
        self.assertEqual(len(self.kinds("pruned")), 1)


class CleanupOrphans(CleanupBase):
    def test_orphans_are_reported_and_never_signalled(self):
        victim = subprocess.Popen(["sleep", "60"])
        self.addCleanup(lambda: (victim.terminate(), victim.wait()))
        pid = victim.pid
        (self.proc / str(pid)).mkdir()
        (self.proc / str(pid) / "cwd").symlink_to("/gone/worktree (deleted)")
        self.ps_out.write_text(
            f"  {pid}     1  08:00:00   0.1 leaked-server\n"
            "  9001     1  08:00:00   0.1 daemon-with-a-real-cwd\n"     # no reason: not reported
            "  9002     1  00:30:00  99.0 young-spinner\n"               # too young
            "  9003  4000  09:00:00  99.0 has-a-parent\n"                # has an owner
            "  9004     1  1-02:00:00 95.0 old-spinner\n")
        p = self.run_cleanup("run")
        self.assertEqual(p.returncode, 0, p.stderr)
        orphans = {e["pid"]: e for e in self.kinds("orphan")}
        self.assertEqual(set(orphans), {pid, 9004})
        self.assertEqual(orphans[pid]["reasons"], ["deleted-cwd"])
        self.assertEqual(orphans[9004]["reasons"], ["runaway-cpu"])
        self.assertIsNone(victim.poll(), "the reported process must still be running")
        self.assertEqual(len(self.kinds("census")), 1)

    def test_source_contains_no_signalling(self):
        src = CLEANUP.read_text()
        self.assertIsNone(re.search(r"os\.kill|os\.killpg|signal\.|\bpkill\b|\"kill\"|'kill'|SIGTERM|SIGKILL", src))


class CleanupInstall(PinnedPythonMac, CleanupBase):
    module, output = "cleanup", "cleanup/last-run.json"

    def prepare(self):
        self.write_config(["cleanup"])

    def test_install_check_stale_uninstall(self):
        label = "com.example.estate.cleanup"
        unit_dir = self.home / ".config/systemd/user"

        def row():
            p = self.estate("doctor", "--json", env=self.env)
            return {r["name"]: r for r in json.loads(p.stdout)["checks"]}["cleanup"]

        self.assertEqual(row()["status"], 1)
        p = self.estate("install", "--dry-run", env=self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse((unit_dir / f"{label}.timer").exists())
        p = self.estate("install", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("00,06,12,18:17", (unit_dir / f"{label}.timer").read_text())
        self.assertTrue((self.home / ".local/bin/estate-cleanup").is_symlink())
        self.assertEqual(self.estate("install", env=self.env).returncode, 0)
        self.assertEqual(row()["status"], 0, row())

        last = self.state / "cleanup" / "last-run.json"
        old = time.time() - 15 * 3600
        os.utime(last, (old, old))
        self.assertEqual(row()["status"], 1)
        self.assertIn("not running", row()["summary"])

        self.assertEqual(self.estate("uninstall", "cleanup", env=self.env).returncode, 0)
        self.assertFalse((unit_dir / f"{label}.timer").exists())
        self.assertTrue(list((self.state / "cleanup").glob("events-*.jsonl")), "events are kept")
