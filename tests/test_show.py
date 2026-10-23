"""show module: argument handling, TTL bookkeeping and install/check, with tailscale and
systemctl faked on PATH. Nothing touches the real tailnet, home or units."""

import json
import os
import socket
import subprocess
import time
from pathlib import Path

from tests.helpers import ROOT, TempHome

SHOW = ROOT / "modules" / "show" / "estate-show"
STATUS = json.dumps({"BackendState": "Running",
                     "Self": {"DNSName": "vps.example.ts.net.", "HostName": "vps"}})
FAKE_TAILSCALE = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_TS_LOG"
case "$*" in
  "status --json") echo "$FAKE_TS_STATUS" ;;
  "serve status --json") echo "${FAKE_TS_SERVE:-{\\}}" ;;
  serve*) [ -z "$FAKE_TS_FAIL" ] || { echo "access denied: not the operator" >&2; exit 1; } ;;
esac
exit 0
"""
FAKE_SYSTEMCTL = """#!/usr/bin/env bash
case "$*" in
  *is-enabled*|*is-active*) [ -f "$FAKE_TIMER_ON" ] ;;
  *"enable --now"*) touch "$FAKE_TIMER_ON" ;;
esac
exit 0
"""


class ShowBase(TempHome):
    def setUp(self):
        super().setUp()
        fake = self.tmp / "fakebin"
        fake.mkdir()
        for name, body in (("tailscale", FAKE_TAILSCALE), ("systemctl", FAKE_SYSTEMCTL)):
            (fake / name).write_text(body)
            (fake / name).chmod(0o755)
        self.ts_log = self.tmp / "ts.log"
        self.env = {"ESTATE_PLATFORM": "linux", "PATH": f"{fake}:{os.environ['PATH']}",
                    "FAKE_TS_LOG": str(self.ts_log), "FAKE_TS_STATUS": STATUS,
                    "FAKE_TIMER_ON": str(self.tmp / "timer-on")}
        self.set_tailnet()
        self.page = self.tmp / "report.html"
        self.page.write_text("<h1>hi</h1>")

    def set_tailnet(self, tailnet="example.ts.net"):
        """Rewrite the config with (or without) the top-level tailnet key."""
        self.write_config(["show"])
        if tailnet:
            self.cfg_path.write_text(f'tailnet = "{tailnet}"\n' + self.cfg_path.read_text())

    def show(self, *args, env=None):
        e = dict(os.environ) | self.env | (env or {})
        return subprocess.run(["python3", str(SHOW), *args], capture_output=True, text=True,
                              env=e, stdin=subprocess.DEVNULL)

    def js(self, *args, **kw):
        p = self.show(*args, "--json", **kw)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)["data"]

    def saved(self):
        return json.loads((self.state_dir() / "state.json").read_text())

    def state_dir(self):
        return self.state / "show"

    def ts_calls(self):
        return self.ts_log.read_text().splitlines() if self.ts_log.exists() else []


class ShowPublish(ShowBase):
    def test_publish_file_json_shape_and_ttl_bookkeeping(self):
        before = int(time.time())
        d = self.js("publish", str(self.page), "--name", "My Report!", "--ttl", "90m")
        p = d["published"]
        self.assertEqual(p["name"], "my-report")
        self.assertEqual(p["url"], "https://vps.example.ts.net:8443/my-report/report.html")
        self.assertEqual(p["ttl"], 5400)
        self.assertGreaterEqual(p["expires"], before + 5400)
        self.assertLessEqual(p["expires"], int(time.time()) + 5400)
        self.assertEqual(p["expires_in"], "1h")
        self.assertTrue((self.state_dir() / "pages/my-report/report.html").is_file())
        self.assertIn(f"serve --bg --https=8443 --set-path=/my-report {self.state_dir()}/pages/my-report",
                      self.ts_calls())
        self.assertEqual([e["name"] for e in self.saved()["entries"]], ["my-report"])
        self.assertTrue(all("funnel" not in c for c in self.ts_calls()))

    def test_sugar_existing_path_beats_digits_and_digits_mean_port(self):
        digits = self.tmp / "3000"
        digits.write_text("a file named like a port")
        d = self.js(str(digits), env={})   # existing path wins
        self.assertEqual(d["published"]["kind"], "page")
        d = self.js("4999", "--name", "app")  # no such path: a port
        self.assertEqual(d["published"]["kind"], "port")
        self.assertIn("http://127.0.0.1:4999", " ".join(self.ts_calls()))

    def test_port_gets_free_serve_port_and_warns_when_nothing_listens(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen()
        self.addCleanup(srv.close)
        port = srv.getsockname()[1]
        d = self.js("port", str(port), "--ttl", "2h", env={"FAKE_TS_SERVE": '{"TCP":{"8450":{}}}'})
        self.assertEqual(d["warnings"], [])
        self.assertEqual(d["published"]["url"], "https://vps.example.ts.net:8451/")
        d = self.js("port", "1", "--name", "dead")
        self.assertTrue(d["warnings"])

    def test_dry_run_changes_nothing(self):
        d = self.js("publish", str(self.page), "--dry-run")
        self.assertTrue(d["dry_run"])
        self.assertFalse((self.state_dir() / "pages").exists())
        self.assertFalse((self.state_dir() / "state.json").exists())
        self.assertFalse([c for c in self.ts_calls() if c.startswith("serve") and "status" not in c])

    def test_bad_input_is_refused_with_exit_2_before_any_side_effect(self):
        for args in (["publish", str(self.page), "--ttl", "31d"], ["publish", str(self.page), "--ttl", "0s"],
                     ["publish", str(self.page), "--ttl", "soon"], ["publish", str(self.tmp / "nope")],
                     ["publish", str(self.page), "--max-size", "5"], ["publish", str(self.page), "--name", "!!!"],
                     ["port", "70000"], ["rm", "ghost"]):
            p = self.show(*args, "--json")
            self.assertEqual(p.returncode, 2, (args, p.stderr))
            err = json.loads(p.stderr)
            self.assertFalse(err["ok"])
            self.assertEqual(err["error"]["code"], 2)
        self.assertFalse([c for c in self.ts_calls() if c.startswith("serve") and "status" not in c])
        self.assertFalse((self.state_dir() / "state.json").exists())

    def test_tailscale_down_or_refusing_is_exit_3_and_leaves_no_state(self):
        p = self.show("publish", str(self.page), "--json",
                      env={"FAKE_TS_STATUS": json.dumps({"BackendState": "Stopped"})})
        self.assertEqual(p.returncode, 3)
        p = self.show("publish", str(self.page), "--json", env={"FAKE_TS_FAIL": "1"})
        self.assertEqual(p.returncode, 3)
        self.assertIn("operator", json.loads(p.stderr)["error"]["hint"])
        self.assertFalse((self.state_dir() / "state.json").exists())
        self.assertEqual(list((self.state_dir() / "pages").glob("*")), [])


class ShowExpiry(ShowBase):
    def test_ls_rm_and_reap_respect_ttl(self):
        self.js("publish", str(self.page), "--name", "short", "--ttl", "1m")
        self.js("publish", str(self.page), "--name", "long", "--ttl", "7d")
        names = {e["name"]: e for e in self.js("ls")["entries"]}
        self.assertEqual(names["long"]["expires_in"], "7d")
        self.assertFalse(names["short"]["expired"])

        # nothing is due: reap leaves both up
        self.assertEqual(self.js("reap")["reaped"], [])
        self.assertEqual(len(self.saved()["entries"]), 2)

        # age the short entry past its expiry in the state file
        st = self.saved()
        for e in st["entries"]:
            if e["name"] == "short":
                e["expires"] = int(time.time()) - 5
        (self.state_dir() / "state.json").write_text(json.dumps(st))
        self.assertEqual(self.js("reap")["reaped"], ["short"])
        self.assertEqual([e["name"] for e in self.saved()["entries"]], ["long"])
        self.assertFalse((self.state_dir() / "pages/short").exists())
        self.assertTrue((self.state_dir() / "pages/long").exists())
        self.assertIn("serve --https=8443 --set-path=/short off", self.ts_calls())

        self.assertEqual(self.js("rm", "long")["removed"], "long")
        self.assertEqual(self.saved()["entries"], [])

    def test_any_command_reaps_expired_first_and_a_refused_removal_is_retried(self):
        self.js("publish", str(self.page), "--name", "old", "--ttl", "1m")
        st = self.saved()
        st["entries"][0]["expires"] = int(time.time()) - 5
        (self.state_dir() / "state.json").write_text(json.dumps(st))
        # tailscale refuses: the entry is kept so the next reap can try again
        p = self.show("reap", "--json", env={"FAKE_TS_FAIL": "1"})
        self.assertEqual(p.returncode, 3)
        self.assertEqual(len(self.saved()["entries"]), 1)
        # ls reaps as housekeeping once tailscale works again
        self.assertEqual(self.js("ls")["entries"], [])


class ShowInstall(ShowBase):
    def row(self, env=None):
        p = self.estate("doctor", "--json", env=self.env | (env or {}))
        return {r["name"]: r for r in json.loads(p.stdout)["checks"]}["show"]

    def test_install_check_warns_without_tailnet_then_ok(self):
        label = "com.example.estate.show"
        unit_dir = self.home / ".config/systemd/user"
        # no tailnet in config: a warning, not a failure
        self.set_tailnet("")
        r = self.row()
        self.assertEqual(r["status"], 2, r)
        self.assertIn("tailnet", r["summary"])
        self.set_tailnet("example.ts.net")
        # tailnet set but tailscale down: warn
        self.assertEqual(self.row(env={"FAKE_TS_STATUS": '{"BackendState":"Stopped"}'})["status"], 2)
        # tailscale fine but not installed yet: fail
        self.assertEqual(self.row()["status"], 1)

        p = self.estate("install", "--dry-run", env=self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse((unit_dir / f"{label}.timer").exists())
        p = self.estate("install", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("OnUnitActiveSec=1min", (unit_dir / f"{label}.timer").read_text())
        self.assertEqual(self.estate("install", env=self.env).returncode, 0)  # idempotent
        self.assertEqual(self.row()["status"], 0, self.row())

        self.js("publish", str(self.page), "--name", "x")
        p = self.estate("uninstall", "show", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse((unit_dir / f"{label}.timer").exists())
        self.assertFalse((self.home / ".local/bin/estate-show").exists())
        self.assertIn("serve --https=8443 --set-path=/x off", self.ts_calls())

    def test_mac_check_is_ok(self):
        p = self.estate("doctor", "--json", env={"ESTATE_PLATFORM": "mac"})
        r = {r["name"]: r for r in json.loads(p.stdout)["checks"]}["show"]
        self.assertEqual(r["status"], 0)


STATEFUL_TAILSCALE = r'''#!/usr/bin/env python3
"""A tailscale that keeps a serve table in $FAKE_TS_TABLE: {"<port>[/<path>]": "<target>"}."""
import json, os, sys
args = sys.argv[1:]
table_file = os.environ["FAKE_TS_TABLE"]
try:
    table = json.load(open(table_file))
except OSError:
    table = {}
with open(os.environ["FAKE_TS_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")
if args == ["status", "--json"]:
    print(os.environ["FAKE_TS_STATUS"])
elif args == ["serve", "status", "--json"]:
    print(json.dumps({"TCP": {k.split("/")[0]: {"HTTPS": True} for k in table}}))
elif args[:1] == ["serve"]:
    https = next(a.split("=", 1)[1] for a in args if a.startswith("--https="))
    path = next((a.split("=", 1)[1] for a in args if a.startswith("--set-path=")), "")
    key = https + path
    if args[-1] == "off":
        if os.environ.get("FAKE_TS_REFUSE_OFF"):
            print("access denied: not the operator", file=sys.stderr)
            sys.exit(1)
        for k in [k for k in table if k == key or (not path and k.split("/")[0] == https)]:
            del table[k]
    else:
        table[key] = args[-1]
    json.dump(table, open(table_file, "w"))
'''


class StatefulShow(ShowBase):
    """Tailscale remembers what is served, so a publication that is dropped from our state
    without being turned off stays visible in the table."""

    def setUp(self):
        super().setUp()
        fake = self.tmp / "fakebin" / "tailscale"
        fake.write_text(STATEFUL_TAILSCALE)
        fake.chmod(0o755)
        self.table_file = self.tmp / "serve-table.json"
        self.env["FAKE_TS_TABLE"] = str(self.table_file)

    def table(self):
        return json.loads(self.table_file.read_text()) if self.table_file.exists() else {}

    def entries(self):
        return {e["name"]: e["kind"] for e in self.saved()["entries"]}


class ShowReplace(StatefulShow):
    def test_page_replacing_a_port_turns_the_old_port_off(self):
        d = self.js("port", "4999", "--name", "app")
        old_port = str(d["published"]["url"].rsplit(":", 1)[1].rstrip("/"))
        self.assertIn(old_port, self.table())
        d = self.js("publish", str(self.page), "--name", "app")
        self.assertEqual(d["published"]["kind"], "page")
        self.assertNotIn(old_port, {k.split("/")[0] for k in self.table()}, self.table())
        self.assertEqual(list(self.table()), ["8443/app"])
        self.assertEqual(self.entries(), {"app": "page"})

    def test_port_replacing_a_page_turns_the_old_page_off(self):
        self.js("publish", str(self.page), "--name", "app")
        self.assertEqual(list(self.table()), ["8443/app"])
        d = self.js("port", "4999", "--name", "app")
        self.assertEqual(d["published"]["kind"], "port")
        self.assertEqual([k.split("/")[0] for k in self.table()], ["8450"])
        self.assertEqual(self.entries(), {"app": "port"})
        self.assertFalse((self.state_dir() / "pages/app").exists())

    def test_failed_replacement_keeps_state_and_exits_nonzero(self):
        self.js("port", "4999", "--name", "app")
        before_table, before_entries = self.table(), self.saved()
        p = self.show("publish", str(self.page), "--name", "app", "--json",
                      env={"FAKE_TS_REFUSE_OFF": "1"})
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(self.saved(), before_entries)
        self.assertEqual(self.table(), before_table)
        self.assertFalse((self.state_dir() / "pages/app").exists())
        # once tailscale cooperates, the replacement goes through
        self.js("publish", str(self.page), "--name", "app")
        self.assertEqual(list(self.table()), ["8443/app"])


class ShowUninstall(StatefulShow):
    def setUp(self):
        super().setUp()
        self.label = "com.example.estate.show"
        self.unit_dir = self.home / ".config/systemd/user"
        p = self.estate("install", "show", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.js("publish", str(self.page), "--name", "keepme")
        self.assertEqual(list(self.table()), ["8443/keepme"])

    def installed(self):
        return {"timer": (self.unit_dir / f"{self.label}.timer").exists(),
                "service": (self.unit_dir / f"{self.label}.service").exists(),
                "bin": (self.home / ".local/bin/estate-show").is_symlink()}

    def test_refused_teardown_fails_uninstall_and_leaves_everything_for_a_retry(self):
        p = self.estate("uninstall", "show", env=self.env | {"FAKE_TS_REFUSE_OFF": "1"})
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.installed(), {"timer": True, "service": True, "bin": True})
        self.assertEqual([e["name"] for e in self.saved()["entries"]], ["keepme"])
        self.assertEqual(list(self.table()), ["8443/keepme"])
        self.assertIn("keepme", p.stdout + p.stderr)  # names what survives
        # the retry, with Tailscale cooperating, finishes the job
        p = self.estate("uninstall", "show", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.installed(), {"timer": False, "service": False, "bin": False})
        self.assertEqual(self.table(), {})

    def test_unreadable_enumeration_fails_uninstall_too(self):
        import shutil
        mods = self.tmp / "mods"
        shutil.copytree(ROOT / "modules" / "show", mods / "show")
        broken = mods / "show" / "estate-show"
        broken.write_text("#!/bin/sh\necho 'cannot list' >&2\nexit 4\n")
        broken.chmod(0o755)
        p = self.estate("uninstall", "show", env=self.env | {"ESTATE_MODULES_DIR": str(mods)})
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.installed()["timer"], True)
        self.assertEqual(list(self.table()), ["8443/keepme"])

    def test_force_removes_the_machinery_anyway_and_prints_the_surviving_links(self):
        p = self.estate("uninstall", "show", env=self.env | {"FAKE_TS_REFUSE_OFF": "1",
                                                             "ESTATE_SHOW_FORCE": "1"})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("keepme", p.stdout + p.stderr)
        self.assertIn("vps.example.ts.net:8443/keepme", p.stdout + p.stderr)
        self.assertEqual(self.installed(), {"timer": False, "service": False, "bin": False})


class ShowDirectoryLinks(StatefulShow):
    """A published copy must not be able to read anything outside the published tree."""

    def setUp(self):
        super().setUp()
        self.site = self.tmp / "work" / "site"
        (self.site / "sub").mkdir(parents=True)
        (self.site / "index.html").write_text("<h1>site</h1>")
        (self.site / "sub" / "data.txt").write_text("inside\n")
        self.secret = self.tmp / "work" / "secret.txt"
        self.secret.write_text("private\n")

    def refused(self):
        p = self.show("publish", str(self.site), "--name", "site", "--json")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("outside", json.loads(p.stderr)["error"]["message"])
        self.assertFalse((self.state_dir() / "state.json").exists())
        self.assertEqual(self.table(), {})
        pages = self.state_dir() / "pages"
        self.assertEqual(list(pages.iterdir()) if pages.exists() else [], [])

    def test_absolute_link_out_of_the_tree_is_refused(self):
        (self.site / "key").symlink_to(self.secret)
        self.refused()

    def test_relative_dotdot_link_out_of_the_tree_is_refused(self):
        (self.site / "sub" / "up").symlink_to("../../secret.txt")
        self.refused()

    def test_link_to_a_directory_outside_is_refused(self):
        (self.site / "etc").symlink_to(self.tmp / "work")
        self.refused()

    def test_internal_links_are_kept_inside_the_copy(self):
        (self.site / "rel").symlink_to("sub/data.txt")
        (self.site / "abs").symlink_to(self.site / "sub" / "data.txt")
        (self.site / "sub" / "dir").symlink_to("..")  # a loop back inside the tree
        self.js("publish", str(self.site), "--name", "site")
        copy = self.state_dir() / "pages" / "site"
        root = os.path.realpath(copy)
        for name in ("rel", "abs"):
            link = copy / name
            self.assertEqual(link.read_text(), "inside\n")
            real = os.path.realpath(link)
            self.assertTrue(real.startswith(root + os.sep), (name, real))
            self.assertFalse(os.path.isabs(os.readlink(link)), os.readlink(link))
        self.assertEqual(os.path.realpath(copy / "sub" / "dir"), root)
        self.assertEqual(list(self.table()), ["8443/site"])
