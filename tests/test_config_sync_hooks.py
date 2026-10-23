"""Wiring the guardrails footgun hook through config-sync's starter: `estate install
config-sync` copies the hook fragments out of modules/guardrails/settings into the new agent-env
repo, and applying them merges hooks per command, so a person's own hooks survive. Temporary
HOME; nothing real is touched."""

import json
import sys
import tempfile
from pathlib import Path

from tests.helpers import ROOT, TempHome
from tests.test_config_sync import git

MOD = ROOT / "modules" / "config-sync"
GUARD = ROOT / "modules" / "guardrails" / "settings"
sys.path.insert(0, str(MOD))
import config_sync as C  # noqa: E402


def commands(settings, event="PreToolUse"):
    return [h["command"] for g in settings.get("hooks", {}).get(event, []) for h in g["hooks"]]


class SeedHooks(TempHome):
    """The init-time copy, called directly."""

    def seed(self, hook_bin=""):
        repo = self.tmp / "agent-env"
        repo.mkdir()
        C.seed(repo, MOD / "starter", ROOT / "doctrine", GUARD, hook_bin)
        return repo

    def test_fragments_are_merged_into_the_starter_files(self):
        repo = self.seed()
        claude = json.loads((repo / "home/.claude/settings.json").read_text())
        self.assertEqual(commands(claude), ["~/.local/bin/footgun-hook"])
        # the starter's own keys are still there
        self.assertIn("Read(~/.ssh/**)", claude["permissions"]["deny"])
        codex = json.loads((repo / "home/.codex/hooks.json").read_text())
        self.assertEqual(commands(codex), ["~/.local/bin/footgun-hook"])
        self.assertEqual(codex["hooks"]["PreToolUse"][0]["matcher"], "^Bash$")

    def test_custom_bin_directory_is_written_into_the_hook_command(self):
        repo = self.seed("~/bin")
        claude = json.loads((repo / "home/.claude/settings.json").read_text())
        self.assertEqual(commands(claude), ["~/bin/footgun-hook"])
        # the default spelling (with or without a trailing slash) changes nothing
        again = self.tmp / "again"
        again.mkdir()
        C.seed(again, MOD / "starter", ROOT / "doctrine", GUARD, "~/.local/bin/")
        self.assertEqual(commands(json.loads((again / "home/.claude/settings.json").read_text())),
                         ["~/.local/bin/footgun-hook"])

    def test_a_missing_fragment_is_refused(self):
        empty = Path(tempfile.mkdtemp(dir=self.tmp))
        with self.assertRaises(C.SyncError) as cm:
            (self.tmp / "x").mkdir()
            C.seed(self.tmp / "x", MOD / "starter", ROOT / "doctrine", empty)
        self.assertIn("claude.json", str(cm.exception))

    def test_every_manifest_source_exists_after_seeding(self):
        repo = self.seed()
        for row in C.parse_manifest((repo / "manifest.tsv").read_text()):
            self.assertTrue((repo / row.src).exists(), row)


class HookWiringEndToEnd(TempHome):
    def setUp(self):
        super().setUp()
        self.bin = self.home / ".local" / "bin"  # the default, so the hook path stays "~/..."
        self.code = self.tmp / "code"
        self.repo = self.code / "agent-env"
        self.write_config(["guardrails", "config-sync"],
                          "\n[harnesses.codex]\n")
        text = self.cfg_path.read_text().replace(
            "[paths]\n", f'[paths]\nbin = "{self.bin}"\ncode = "{self.code}"\n')
        self.cfg_path.write_text(text)
        # CLAUDE_CONFIG_DIR / CODEX_HOME in the developer's shell would redirect the doctor check
        self.env = {"ESTATE_PLATFORM": "mac", "CLAUDE_CONFIG_DIR": "", "CODEX_HOME": ""}

    def rows(self):
        p = self.estate("doctor", "--json", env=self.env)
        return {r["name"]: r for r in json.loads(p.stdout)["checks"]}

    def test_install_wires_the_hook_keeps_other_hooks_and_is_idempotent(self):
        claude, codex = self.home / ".claude", self.home / ".codex"
        claude.mkdir()
        codex.mkdir()
        mine = {"type": "command", "command": "~/mine.sh"}
        (claude / "settings.json").write_text(json.dumps({
            "model": "keep-me",
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [mine]}],
                      "Stop": [{"hooks": [{"type": "command", "command": "~/stop.sh"}]}]}}))
        (codex / "hooks.json").write_text(json.dumps({
            "hooks": {"PreToolUse": [{"matcher": "^Bash$", "hooks": [mine]}]}}))

        p = self.estate("install", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

        settings = json.loads((claude / "settings.json").read_text())
        self.assertEqual(settings["model"], "keep-me")
        self.assertEqual(commands(settings, "Stop"), ["~/stop.sh"])
        # Both hooks are on Bash; the person's survives next to ours, each exactly once.
        self.assertEqual(sorted(commands(settings)), ["~/.local/bin/footgun-hook", "~/mine.sh"])
        hooks = json.loads((codex / "hooks.json").read_text())
        self.assertEqual(sorted(commands(hooks)), ["~/.local/bin/footgun-hook", "~/mine.sh"])

        # a second install, and an apply from the repo, change nothing
        before = {f: f.read_bytes() for f in (claude / "settings.json", codex / "hooks.json")}
        p = self.estate("install", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for f, data in before.items():
            self.assertEqual(f.read_bytes(), data, f)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

        # and doctor agrees: the guardrails row no longer warns about a missing hook
        rows = self.rows()
        self.assertEqual(rows["guardrails"]["status"], 0, rows["guardrails"])
        self.assertEqual(rows["config-sync"]["status"], 0, rows["config-sync"])

    def test_guardrails_warns_until_the_hook_is_in_settings(self):
        # Guards the test above: the guardrails row really does depend on the hook being
        # present in the harness settings, so "status 0" is not vacuous.
        self.assertEqual(self.estate("install", "guardrails", env=self.env).returncode, 0)
        row = self.rows()["guardrails"]
        self.assertEqual(row["status"], 2, row)
        self.assertIn("footgun hook is not in the settings", row["summary"])

    def test_a_non_default_bin_directory_is_used_in_the_hook_command(self):
        self.bin = self.home / "tools"
        text = self.cfg_path.read_text().replace(
            f'bin = "{self.home / ".local" / "bin"}"', f'bin = "{self.bin}"')
        self.cfg_path.write_text(text)
        p = self.estate("install", "config-sync", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        settings = json.loads((self.home / ".claude/settings.json").read_text())
        self.assertEqual(commands(settings), ["~/tools/footgun-hook"])
