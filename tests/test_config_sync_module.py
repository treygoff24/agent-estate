"""The config-sync module end to end through bin/estate: install from the starter (or a
remote), doctor, uninstall. Temporary HOME; nothing real is touched."""

import json
import os
import subprocess
from pathlib import Path

from tests.helpers import ROOT, TempHome
from tests.test_config_sync import git

MOD = ROOT / "modules" / "config-sync"


class ConfigSyncModule(TempHome):
    def setUp(self):
        super().setUp()
        self.env = {"ESTATE_PLATFORM": "mac"}
        self.bin = self.tmp / "bin"
        self.code = self.tmp / "code"
        self.repo = self.code / "agent-env"

    def configure(self, remote=""):
        extra = "\n[modules.config-sync]\n" + (f'remote = "{remote}"\n' if remote else "")
        self.write_config(["config-sync"], extra)
        self.cfg_path.write_text(self.cfg_path.read_text().replace(
            "[paths]\n", f'[paths]\nbin = "{self.bin}"\ncode = "{self.code}"\n'))

    def est(self, *args):
        return self.estate(*args, env=self.env)

    def row(self):
        p = self.est("doctor", "--json")
        rows = {r["name"]: r for r in json.loads(p.stdout)["checks"]}
        return rows["config-sync"]

    def commit_all(self, repo=None):
        repo = repo or self.repo
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "change")

    def test_install_from_starter_then_doctor_then_uninstall(self):
        self.configure()
        # a machine that already has some config: its other keys must survive, and its own
        # CLAUDE.md must not be overwritten
        claude = self.home / ".claude"
        claude.mkdir()
        (claude / "settings.json").write_text(json.dumps({"model": "keep-me"}))
        (claude / "CLAUDE.md").write_text("my own rules\n")

        p = self.est("install", "--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("would create", p.stderr + p.stdout)
        self.assertFalse(self.repo.exists() or self.bin.exists())
        self.assertEqual((claude / "CLAUDE.md").read_text(), "my own rules\n")

        p = self.est("install")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("local-edit  .claude/CLAUDE.md", p.stderr)
        self.assertEqual((claude / "CLAUDE.md").read_text(), "my own rules\n")
        link = self.bin / "estate-config-sync"
        self.assertEqual(os.readlink(link), str(MOD / "estate-config-sync"))

        # the checkout: starter + doctrine pack, one commit, clean
        self.assertEqual(git(self.repo, "log", "--format=%s").count("\n"), 1)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertTrue((self.repo / "home/doctrine/shell-footguns.md").is_file())
        # installed where the harnesses read them
        self.assertTrue((claude / "rules/shell-footguns.md").is_file())
        self.assertTrue((claude / "rules/agent-operating-contract.md").is_file())
        doc = self.home / ".config/agent-estate/doctrine"
        self.assertTrue((doc / "no-ceremony.md").is_file())
        self.assertNotIn("<doctrine-dir>", (doc / "house-register.md").read_text())
        settings = json.loads((claude / "settings.json").read_text())
        self.assertEqual(settings["model"], "keep-me")
        self.assertIn("Read(~/.ssh/**)", settings["permissions"]["deny"])
        self.assertIn('approval_policy = "on-request"', (self.home / ".codex/config.toml").read_text())
        self.assertIn("~/.config/agent-estate/doctrine", (self.home / ".codex/AGENTS.md").read_text())

        # second install: idempotent, the local edit is still there
        p = self.est("install")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("unchanged", p.stdout)
        self.assertNotIn("install ", p.stdout.replace("config-sync:", ""))
        self.assertEqual(git(self.repo, "log", "--format=%s").count("\n"), 1)

        # doctor warns about the unharvested edit until it is rescued
        row = self.row()
        self.assertEqual(row["status"], 2, row)
        self.assertIn("1 local edit(s) not in the repo (.claude/CLAUDE.md)", row["summary"])
        p = subprocess.run([str(link), "--harvest", ".claude/CLAUDE.md"], capture_output=True,
                           text=True, env=dict(os.environ, HOME=str(self.home),
                                               ESTATE_STATE=str(self.state)))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.repo / "home/.claude/CLAUDE.md").read_text(), "my own rules\n")
        self.assertEqual(self.row()["status"], 2)  # harvested but not committed yet
        self.commit_all()
        row = self.row()
        self.assertEqual(row["status"], 0, row)

        # retiring a file from the repo retires it from the machine
        (self.repo / "home/doctrine/no-ceremony.md").unlink()
        self.commit_all()
        self.assertEqual(self.row()["status"], 2)  # change waiting
        p = self.est("install")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse((doc / "no-ceremony.md").exists())
        self.assertEqual(self.row()["status"], 0)

        p = self.est("uninstall", "config-sync")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(link.is_symlink())
        self.assertTrue(self.repo.is_dir())  # your configuration is not deleted
        self.assertTrue((claude / "rules/shell-footguns.md").is_file())

    def test_doctor_fails_without_checkout_and_names_the_fix(self):
        self.configure()
        row = self.row()
        self.assertEqual(row["status"], 1)
        self.assertIn("estate install config-sync", row["summary"])

    def test_second_machine_clones_the_remote(self):
        remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
        # machine one: start from the starter, push
        self.configure(remote=str(remote))
        self.assertEqual(self.est("install").returncode, 0)
        git(self.repo, "push", "-q", "origin", "HEAD:main")
        (self.repo / "home/.codex/AGENTS.md").write_text("changed on machine one\n")
        self.commit_all()
        git(self.repo, "push", "-q", "origin", "HEAD:main")

        # machine two: same estate.toml, fresh home
        home2, state2 = self.tmp / "home2", self.tmp / "state2"
        home2.mkdir()
        self.code, self.bin = self.tmp / "code2", self.tmp / "bin2"
        self.state = state2
        os.environ["HOME"] = str(home2)
        self.configure(remote=str(remote))
        p = self.est("install")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((home2 / ".codex/AGENTS.md").read_text(), "changed on machine one\n")
        self.assertEqual(self.row()["status"], 0)

    def test_empty_remote_is_seeded_from_the_starter(self):
        remote = self.tmp / "empty.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
        self.configure(remote=str(remote))
        p = self.est("install")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue((self.repo / "manifest.tsv").is_file())
        self.assertIn(str(remote), git(self.repo, "remote", "-v"))
        self.assertIn("push -u origin HEAD:main", p.stderr)  # tells the person how to push
        self.assertNotIn("remote add", p.stderr)  # origin is already set

    def test_without_a_remote_the_message_says_how_to_add_one(self):
        self.configure()
        p = self.est("install")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("remote add origin <url> && git -C", p.stderr)
        self.assertIn("push -u origin HEAD:main", p.stderr)

    def test_unreachable_remote_fails_without_creating_anything(self):
        self.configure(remote=str(self.tmp / "no-such.git"))
        p = self.est("install")
        self.assertEqual(p.returncode, 1)
        self.assertIn("cannot clone", p.stderr)
        self.assertFalse(self.repo.exists())

    def test_a_non_git_directory_in_the_way_is_refused(self):
        self.configure()
        self.repo.mkdir(parents=True)
        (self.repo / "precious.txt").write_text("x")
        p = self.est("install")
        self.assertEqual(p.returncode, 1)
        self.assertIn("not a git checkout", p.stderr)
        self.assertEqual(os.listdir(self.repo), ["precious.txt"])

    def test_starter_manifest_is_valid_on_both_platforms_and_sources_exist_after_seeding(self):
        import sys
        sys.path.insert(0, str(MOD))
        import config_sync as C
        rows = C.parse_manifest((MOD / "starter/manifest.tsv").read_text())
        self.assertGreaterEqual(len(rows), 6)
        for platform in C.PLATFORMS:
            C.active_rows(rows, platform)
        self.configure()
        self.assertEqual(self.est("install").returncode, 0)
        for row in rows:
            self.assertTrue((self.repo / row.src).exists(), row)
