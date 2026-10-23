"""The post module: install order, harness hooks, bridge, sync row and check statuses.
git, curl, cargo, node, post, systemctl and launchctl are all stubs on PATH that record
their argv; the real tools are never run and the real HOME is never touched."""

import os
import shutil
import stat
from pathlib import Path

from tests.helpers import TempHome

LOG_STUB = '#!/usr/bin/env bash\necho "{name} $*" >> "$FAKE_LOG"\n'
GIT = """#!/usr/bin/env bash
echo "git $*" >> "$FAKE_LOG"
case "$1" in
  clone) dest="${@: -1}"; mkdir -p "$dest/.git"; cp -R "$FAKE_TEMPLATE"/. "$dest"/ ;;
  -C) [ "$3" = rev-parse ] && echo "${FAKE_HEAD:-aaaa111}" ;;
esac
exit 0
"""
POST = """#!/usr/bin/env bash
echo "post $*" >> "$FAKE_LOG"
case "$1" in
  --version) echo "post 0.10.0" ;;
  doctor) exit "${FAKE_DOCTOR_RC:-0}" ;;
esac
exit 0
"""
# the release installer curl "downloads": it puts a post binary in ~/.local/bin
CURL = """#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
out=""; while [ $# -gt 0 ]; do [ "$1" = -o ] && out="$2"; shift; done
printf '#!/bin/sh\\necho "release-installer $*" >> "$FAKE_LOG"\\nmkdir -p "$HOME/.local/bin"\\ncp "$FAKE_POST" "$HOME/.local/bin/post"\\n' > "$out"
[ -z "$FAKE_CURL_FAIL" ] || exit 22
"""
CARGO = """#!/usr/bin/env bash
echo "cargo $*" >> "$FAKE_LOG"
root=""; while [ $# -gt 0 ]; do [ "$1" = --root ] && root="$2"; shift; done
mkdir -p "$root/bin"; cp "$FAKE_POST" "$root/bin/post"
"""
SYSTEMCTL = """#!/usr/bin/env bash
echo "systemctl $*" >> "$FAKE_LOG"
case "$*" in *is-active*post-bridge*) [ -f "$FAKE_BRIDGE_ON" ] ;; esac
"""
LAUNCHCTL = """#!/usr/bin/env bash
echo "launchctl $*" >> "$FAKE_LOG"
case "$1 $2" in "list org.post.bridge") [ -f "$FAKE_BRIDGE_ON" ] ;; esac
"""
BASICS = ["bash", "sh", "env", "python3", "awk", "grep", "find", "cat", "mkdir", "cp", "ln", "rm",
          "mktemp", "dirname", "basename", "sed", "readlink", "cmp", "date", "id", "head", "tr",
          "sort", "uname", "touch", "printf", "cut", "wc", "mv", "chmod", "tee", "xargs", "ls"]
HOOKS = ["install-claude-hooks.mjs", "install-codex-hooks.mjs", "install-cursor-hooks.mjs",
         "install-grok-hooks.mjs", "mail-hook-core.mjs", "pi-mail.mjs"]


def stub(path: Path, body: str):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class PostBase(TempHome):
    platform = "linux"
    machine = "vps"

    def setUp(self):
        super().setUp()
        self.fake = self.tmp / "fakebin"
        self.fake.mkdir()
        self.tools = self.tmp / "tools"      # a PATH holding only the basics, so "no curl" is real
        self.tools.mkdir()
        for name in BASICS:
            real = shutil.which(name)
            if real:
                (self.tools / name).symlink_to(real)
        self.log = self.tmp / "calls.log"
        self.log.touch()
        for name, body in (("git", GIT), ("post-stub", POST), ("curl", CURL), ("cargo", CARGO),
                           ("systemctl", SYSTEMCTL), ("launchctl", LAUNCHCTL)):
            stub(self.fake / name, body)
        stub(self.fake / "node", LOG_STUB.format(name="node"))
        self.template = self.tmp / "template"
        hooks = self.template / "skills/post/hooks"
        hooks.mkdir(parents=True)
        for h in HOOKS:
            (hooks / h).write_text("//\n")
        (self.template / "bridge").mkdir()
        stub(self.template / "bridge/install.sh", LOG_STUB.format(name="bridge-install"))
        self.bridge_on = self.tmp / "bridge-on"
        self.env = {"PATH": f"{self.fake}:{self.tools}", "FAKE_LOG": str(self.log),
                    "FAKE_TEMPLATE": str(self.template), "FAKE_POST": str(self.fake / "post-stub"),
                    "FAKE_BRIDGE_ON": str(self.bridge_on), "ESTATE_PLATFORM": self.platform,
                    "ESTATE_MACHINE": self.machine, "FAKE_CURL_FAIL": "",
                    "CLAUDE_CONFIG_DIR": "", "CODEX_HOME": "", "POST_PARTICIPANT": ""}
        self.checkout = self.home / "Code" / "post"
        self.repos = self.home / ".config/agent-estate/sync-repos.tsv"

    def config(self, extra=""):
        self.write_config(enabled=["post"], extra=extra)

    def install(self, *args, **env):
        return self.estate("install", "post", *args, env=self.env | env)

    def check(self, **env):
        return self.estate("doctor", "--json", env=self.env | env)

    def calls(self):
        return [ln for ln in self.log.read_text().splitlines() if ln]

    def index(self, prefix):
        for i, c in enumerate(self.calls()):
            if c.startswith(prefix):
                return i
        self.fail(f"no call starting {prefix!r} in {self.calls()}")


class Install(PostBase):
    def test_release_install_runs_in_order_with_hooks_for_each_harness(self):
        self.config('\n[harnesses.codex]\n')
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        order = [self.index(x) for x in ("git clone https://github.com/treygoff24/post", "curl ",
                                         "release-installer --no-modify-path", "post doctor --fix --brief",
                                         "node ")]
        self.assertEqual(order, sorted(order), self.calls())
        nodes = [c for c in self.calls() if c.startswith("node ")]
        self.assertEqual(len(nodes), 2, nodes)
        self.assertIn("install-claude-hooks.mjs " + str(self.home / ".claude/settings.json"), nodes[0])
        self.assertIn("install-codex-hooks.mjs " + str(self.home / ".codex/hooks.json"), nodes[1])
        self.assertFalse([c for c in self.calls() if c.startswith("cargo")])
        self.assertFalse([c for c in self.calls() if c.startswith("bridge-install")])

    def test_without_curl_it_builds_from_the_checkout_with_cargo(self):
        (self.tools / "curl").unlink(missing_ok=True)
        (self.fake / "curl").unlink()
        self.config()
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        cargo = self.calls()[self.index("cargo")]
        self.assertIn(f"install --locked --force --path {self.checkout} --bin post", cargo)
        self.assertTrue((self.home / ".local/bin/post").is_symlink())
        self.assertLess(self.index("cargo"), self.index("post doctor --fix"))

    def test_failed_release_falls_back_to_cargo_but_release_only_does_not(self):
        self.config()
        p = self.install(FAKE_CURL_FAIL="1")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue([c for c in self.calls() if c.startswith("cargo")])
        shutil.rmtree(self.checkout)
        self.log.write_text("")
        (self.state / "post" / "installed").unlink()
        (self.home / ".local/bin/post").unlink()
        self.config('\n[modules.post]\ninstall_method = "release"\n')
        p = self.install(FAKE_CURL_FAIL="1")
        self.assertEqual(p.returncode, 1)
        self.assertFalse([c for c in self.calls() if c.startswith("cargo")])

    def test_second_run_installs_nothing_again(self):
        self.config()
        self.assertEqual(self.install().returncode, 0)
        self.log.write_text("")
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        calls = self.calls()
        for gone in ("git clone", "curl", "cargo", "release-installer"):
            self.assertFalse([c for c in calls if c.startswith(gone)], (gone, calls))
        rows = [ln for ln in self.repos.read_text().splitlines() if ln.startswith("post\t")]
        self.assertEqual(len(rows), 1, rows)

    def test_a_moved_checkout_reinstalls(self):
        self.config()
        self.assertEqual(self.install().returncode, 0)
        self.log.write_text("")
        self.assertEqual(self.install(FAKE_HEAD="bbbb222").returncode, 0)
        self.assertTrue([c for c in self.calls() if c.startswith("curl")], self.calls())

    def test_only_the_harnesses_in_the_config_get_hooks(self):
        self.config('\n[harnesses.pi]\n')   # claude (base) + pi, no codex
        self.assertEqual(self.install().returncode, 0)
        nodes = " ".join(c for c in self.calls() if c.startswith("node "))
        self.assertIn("install-claude-hooks", nodes)
        self.assertNotIn("codex", nodes)
        self.assertTrue((self.home / ".pi/agent/extensions/post-mail/index.js").is_file())

    def test_hooks_false_skips_them_and_missing_node_is_a_note_not_an_error(self):
        self.config('\n[modules.post]\nhooks = false\n')
        self.assertEqual(self.install().returncode, 0)
        self.assertFalse([c for c in self.calls() if c.startswith("node ")])
        (self.fake / "node").unlink()
        self.config()
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("node is not installed", p.stderr)

    def test_sync_row_points_at_the_checkout(self):
        self.config()
        self.assertEqual(self.install().returncode, 0)
        row = next(ln for ln in self.repos.read_text().splitlines() if ln.startswith("post\t"))
        _, path, cmd = row.split("\t")
        self.assertEqual(path, str(self.checkout))
        self.assertTrue(cmd.endswith("install post"), cmd)

    def test_dry_run_changes_nothing(self):
        self.config()
        p = self.install("--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(self.checkout.exists())
        self.assertFalse(self.repos.exists())
        self.assertFalse([c for c in self.calls() if not c.startswith("git ") or " clone" in c])


class Bridge(PostBase):
    def relay(self, extra=""):
        (self.home / ".ssh").mkdir(exist_ok=True)
        (self.home / ".ssh/post-relay").write_text("x")
        self.config('\n[modules.post]\nbridge = true\nrelay_url = "ssh://git@git.example.com/you/relay.git"\n' + extra)

    def test_off_by_default(self):
        self.config()
        self.assertEqual(self.install().returncode, 0)
        self.assertFalse([c for c in self.calls() if c.startswith("bridge-install")])

    def test_enabled_runs_the_bridge_installer_with_this_machines_name(self):
        self.relay('bridge_interval = "30s"\n')
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        call = self.calls()[self.index("bridge-install")]
        self.assertIn("--repo-url ssh://git@git.example.com/you/relay.git --host vps", call)
        self.assertIn(f"--ssh-key {self.home}/.ssh/post-relay", call)
        self.assertIn("--interval 30s", call)
        cfg = (self.state / "post/bridge-config.json").read_text()
        self.assertIn('"host": "vps"', cfg)
        self.assertIn('"channels": null', cfg)
        self.assertIn('{"v": 1, "hosts": ["mac", "vps"]}', p.stderr)
        self.assertLess(self.index("post doctor --fix"), self.index("bridge-install"))

    def test_enabled_without_a_relay_or_key_fails_before_changing_anything(self):
        self.config('\n[modules.post]\nbridge = true\n')
        p = self.install()
        self.assertEqual(p.returncode, 1)
        self.assertIn("relay_url is required", p.stderr)
        self.relay()
        (self.home / ".ssh/post-relay").unlink()
        p = self.install()
        self.assertEqual(p.returncode, 1)
        self.assertIn("relay key", p.stderr)
        self.assertFalse([c for c in self.calls() if c.startswith("bridge-install")])


class Check(PostBase):
    def installed(self, extra=""):
        self.config(extra)
        self.assertEqual(self.install().returncode, 0)
        # the stub hook installers write nothing, so put the marker the real ones leave
        (self.home / ".claude").mkdir(exist_ok=True)
        (self.home / ".claude/settings.json").write_text('{"hooks": "post-claude-mail"}')

    def row(self, **env):
        import json
        p = self.check(**env)
        rows = json.loads(p.stdout)
        rows = rows["checks"] if isinstance(rows, dict) else rows
        return next(r for r in rows if r["name"] == "post")

    def test_ok(self):
        self.installed()
        r = self.row()
        self.assertEqual(r["status"], 0, r)

    def test_missing_post_fails(self):
        self.installed()
        (self.home / ".local/bin/post").unlink()
        self.assertEqual(self.row()["status"], 1)

    def test_doctor_findings_warn_and_a_crash_fails(self):
        self.installed()
        self.assertEqual(self.row(FAKE_DOCTOR_RC="1")["status"], 2)
        self.assertEqual(self.row(FAKE_DOCTOR_RC="3")["status"], 1)

    def test_a_missing_hook_for_a_listed_harness_warns(self):
        self.installed()
        (self.home / ".claude/settings.json").write_text("{}")
        r = self.row()
        self.assertEqual(r["status"], 2, r)
        self.assertIn("claude", r["summary"])

    def test_bridge_must_be_running_when_enabled_linux_and_mac(self):
        (self.home / ".ssh").mkdir()
        (self.home / ".ssh/post-relay").write_text("x")
        self.installed('\n[modules.post]\nbridge = true\nrelay_url = "ssh://git@git.example.com/you/relay.git"\n')
        self.assertEqual(self.row()["status"], 1)
        self.bridge_on.touch()
        self.assertEqual(self.row()["status"], 0)
        self.bridge_on.unlink()
        self.assertEqual(self.row(ESTATE_PLATFORM="mac", ESTATE_MACHINE="mac")["status"], 1)
        self.bridge_on.touch()
        self.assertEqual(self.row(ESTATE_PLATFORM="mac", ESTATE_MACHINE="mac")["status"], 0)
