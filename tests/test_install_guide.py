"""The install guide and the example config stay true to the code (the private-marker scan in
scripts/gate.sh covers personal data): estate.example.toml passes
`estate config check` verbatim (and with every commented example uncommented), enables exactly
the built modules, and INSTALL.md / README.md name every module, link to real files, and use real
`estate` subcommands. Temporary HOME; nothing real is touched."""

import re
import sys
import tomllib
from pathlib import Path

from tests.helpers import ROOT, TempHome

sys.path.insert(0, str(ROOT / "lib"))
from estate import modules as M  # noqa: E402

EXAMPLE = ROOT / "estate.example.toml"
INSTALL = ROOT / "INSTALL.md"
README = ROOT / "README.md"
MODULES = ROOT / "modules"


def built():
    return sorted(d.name for d in MODULES.iterdir()
                  if (d / "module.toml").is_file() and (d / "install").is_file()
                  and (d / "check").is_file())


def stubs():
    return sorted(d.name for d in MODULES.iterdir()
                  if (d / "module.toml").is_file() and d.name not in built())


def uncommented_settings(text):
    """The example with every commented-out `[table]` and `key = value` line switched on."""
    marker = "# Per-module settings"
    head, _, tail = text.partition(marker)
    out = []
    for line in tail.splitlines():
        m = re.match(r"^# ((?:[A-Za-z_][\w-]*\s*=\s*.+)|(?:\[[^\]]+\]))\s*$", line)
        out.append(m.group(1) if m else line)
    return head + marker + "\n".join(out)


class ExampleConfig(TempHome):
    def check(self, text):
        self.cfg_path.write_text(text)
        return self.estate("config", "check")

    def test_copied_verbatim_it_passes_config_check(self):
        p = self.check(EXAMPLE.read_text())
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(p.stdout.startswith("ok:"), p.stdout)

    def test_every_commented_setting_example_is_a_real_setting(self):
        text = uncommented_settings(EXAMPLE.read_text())
        # the precondition: the rewrite turned something on, in several modules' tables
        tables = set(re.findall(r"^\[modules\.([\w.-]+)\]", text, re.M))
        self.assertGreaterEqual(len(tables), 7, tables)
        p = self.check(text)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        loaded = tomllib.loads(text)
        self.assertEqual(loaded["modules"]["sync"]["hooks"], ["estate-config-sync apply --pull", "skillherd sync"])
        self.assertIn("refresh_login", loaded["modules"]["usage"])

    def test_a_misspelled_commented_setting_is_caught(self):
        # Guards the test above: it does fail when a commented example names a setting that
        # does not exist.
        text = uncommented_settings(EXAMPLE.read_text()).replace("refresh_login", "refresh_logins")
        p = self.check(text)
        self.assertEqual(p.returncode, 1)
        self.assertIn("refresh_logins", p.stderr)

    def test_enabled_is_exactly_the_built_modules(self):
        enabled = tomllib.loads(EXAMPLE.read_text())["modules"]["enabled"]
        self.assertEqual(sorted(enabled), built())
        self.assertIn("post", enabled)
        self.assertIn("skills", enabled)

    def test_stubs_are_listed_only_as_coming_soon_comments(self):
        text = EXAMPLE.read_text()
        for name in stubs():
            self.assertRegex(text, rf'# "{name}",\s+# coming soon: .*not built yet', name)


class Guide(TempHome):
    def setUp(self):
        super().setUp()
        self.text = INSTALL.read_text()

    def test_every_built_module_is_explained_and_every_stub_is_marked_coming_soon(self):
        self.assertGreater(len(built()), 8)
        for name in built():
            self.assertTrue(f"| `{name}` |" in self.text, f"{name}: no row in the module table")
            self.assertRegex(self.text, rf"\*\*[^*\n]*(?<![\w-]){re.escape(name)}(?![\w-])[^*\n]*\*\*",
                             f"{name}: no paragraph of its own in section 5")
        for name in stubs():
            self.assertIn(f"| `{name}` |", self.text)
            line = next(ln for ln in self.text.splitlines() if ln.startswith(f"| `{name}` |"))
            self.assertIn("Coming soon: module not built yet", line, name)
            self.assertRegex(self.text, rf"\*\*{name}\*\*[^\n]*coming soon: module not built yet",
                             name)

    def test_the_sections_are_in_the_documented_order(self):
        heads = re.findall(r"^## (\d+)\. ", self.text, re.M)
        self.assertEqual(heads, [str(i) for i in range(10)])

    def test_relative_links_resolve(self):
        for doc in (INSTALL, README):
            for target in re.findall(r"\]\(([^)#\s]+)\)", doc.read_text()):
                if re.match(r"[a-z]+:", target):
                    continue
                self.assertTrue((ROOT / target).exists(), f"{doc.name} links to {target}")

    def test_commands_use_real_estate_subcommands(self):
        found = re.findall(r"^\s*(?:ssh vps '~/\.local/bin/)?estate (\S+)(?: (\S+))?", self.text, re.M)
        self.assertGreaterEqual(len(found), 5)
        known = {"config", "install", "uninstall", "doctor", "list", "render", "label", "--help"}
        for sub, arg in found:
            self.assertIn(sub, known, sub)
            if sub == "config":
                self.assertIn(arg.strip("'\""), {"check", "get", "path"})

    def test_named_commands_exist(self):
        # Commands the guide tells the agent to run that modules install or ship.
        shipped = {
            "estate-config-sync": MODULES / "config-sync" / "estate-config-sync",
            "estate-sync": MODULES / "sync" / "estate-sync",
            "estate-health": MODULES / "health" / "estate-health",
            "estate-cleanup": MODULES / "cleanup" / "estate-cleanup",
            "estate-show": MODULES / "show" / "estate-show",
            "post": MODULES / "post" / "install",
            "skill": MODULES / "skills" / "install",
            "testrun": MODULES / "guardrails" / "bin" / "testrun",
            "footgun-hook": MODULES / "guardrails" / "bin" / "footgun-hook",
        }
        for name, path in shipped.items():
            self.assertTrue(name in self.text, name)
            self.assertTrue(path.is_file(), path)

    def test_the_documented_settings_exist(self):
        known = M.discover()
        for name, key in [("baseline", "public_ssh"), ("baseline", "backups"),
                          ("baseline", "backup_repo"), ("baseline", "agent_user"),
                          ("sync", "hooks"), ("config-sync", "remote"),
                          ("usage", "refresh_login"), ("guardrails", "compile_slots"),
                          ("keys", "tools"), ("cleanup", "worktree_age"),
                          ("post", "bridge"), ("post", "relay_url"), ("post", "hooks"),
                          ("post", "install_method"), ("skills", "pool"),
                          ("skills", "pool_remote"), ("skills", "checkout")]:
            self.assertIn(key, known[name]["defaults"], (name, key))

    def test_the_hook_flags_in_the_root_command_match_the_script(self):
        script = (MODULES / "baseline" / "root-setup.sh").read_text()
        cmd = next(ln for ln in self.text.splitlines() if "root-setup.sh --agent-user" in ln
                   and "--dry-run" not in ln)
        for flag in re.findall(r"(--[a-z-]+)", cmd):
            self.assertIn(flag, script, flag)
