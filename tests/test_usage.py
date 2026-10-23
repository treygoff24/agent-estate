"""The usage module: parsing, polling against a fake HTTP server, token refresh,
atomic snapshot writes, and the install/check lifecycle with systemctl,
launchctl and security faked on PATH. Field names are the vendors' real ones;
every number is invented."""

import base64
import importlib.machinery
import importlib.util
import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from tests.helpers import ROOT, PinnedPythonMac, TempHome

POLL = ROOT / "modules" / "usage" / "usage-poll"
_loader = importlib.machinery.SourceFileLoader("usage_poll", str(POLL))
_spec = importlib.util.spec_from_loader("usage_poll", _loader)
U = importlib.util.module_from_spec(_spec)
_loader.exec_module(U)

CLAUDE_USAGE = {"limits": [
    {"kind": "session", "group": "session", "percent": 42.0, "resets_at": "2026-10-22T15:00:00.000000Z",
     "scope": {}, "is_active": True},
    {"kind": "weekly_all", "group": "weekly", "percent": 17.5, "resets_at": "2026-10-27T08:00:00Z"},
    {"kind": "weekly_scoped", "group": "weekly", "percent": 61,
     "resets_at": "2026-10-27T08:00:00Z", "scope": {"model": {"display_name": "Opus"}}},
    {"kind": "junk", "percent": "n/a"},
]}
CLAUDE_OLD = {"five_hour": {"utilization": 9, "resets_at": "2026-10-22T15:00:00Z"},
              "seven_day": {"utilization": 3.5, "resets_at": "2026-10-27T08:00:00Z"}}
CODEX_USAGE = {"plan_type": "plus", "email": "x@example.com", "rate_limit": {
    "limit_reached": False,
    "primary_window": {"used_percent": 12, "limit_window_seconds": 18000, "reset_at": 1790000000},
    "secondary_window": {"used_percent": 55.5, "limit_window_seconds": 604800, "reset_at": 1790500000}}}


def jwt(exp):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return f"{enc({'alg': 'none'})}.{enc({'exp': exp})}.sig"


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        srv = self.server
        srv.hits.append((self.path, self.headers.get("Authorization")))
        if self.path == "/api/oauth/usage":
            if self.headers.get("Authorization") != f"Bearer {srv.good_claude_token}":
                return self._send(401, {})
            return self._send(200, srv.claude_body)
        if self.path == "/wham/usage":
            if self.headers.get("Authorization") != f"Bearer {srv.good_codex_token}":
                return self._send(401, {})
            return self._send(200, CODEX_USAGE)
        self._send(404, {})

    def do_POST(self):
        srv = self.server
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        srv.hits.append((self.path, body))
        if self.path == "/token" and body.get("refresh_token") == "old-refresh":
            return self._send(200, {"access_token": "new-access", "refresh_token": "new-refresh",
                                    "expires_in": 3600})
        self._send(400, {"error": "invalid_grant"})


class UsageBase(TempHome):
    def setUp(self):
        super().setUp()
        self.srv = HTTPServer(("127.0.0.1", 0), Fake)
        self.srv.hits = []
        self.srv.claude_body = CLAUDE_USAGE
        self.srv.good_claude_token = "claude-access"
        self.srv.good_codex_token = jwt(int(time.time()) + 3600)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.fake_env = {"ESTATE_USAGE_CLAUDE_API": base, "ESTATE_USAGE_CLAUDE_TOKEN_URL": base + "/token",
                         "ESTATE_USAGE_CODEX_URL": base + "/wham/usage"}
        self.fakebin = self.tmp / "fakebin"
        self.fakebin.mkdir()
        self.log = self.tmp / "cmds.log"
        self.on = self.tmp / "loaded"
        fakes = {
            "systemctl": '#!/usr/bin/env bash\necho "$*" >> "$FAKE_LOG"\ncase "$*" in\n'
                         '  *is-enabled*|*is-active*) [ -f "$FAKE_ON" ] ;;\n'
                         '  *"enable --now"*) touch "$FAKE_ON" ;;\n  *"disable --now"*) rm -f "$FAKE_ON" ;;\nesac\n',
            "launchctl": '#!/usr/bin/env bash\necho "$*" >> "$FAKE_LOG"\ncase "$1" in\n'
                         '  list) [ -f "$FAKE_ON" ] ;;\n  bootstrap) touch "$FAKE_ON" ;;\n'
                         '  bootout) rm -f "$FAKE_ON" ;;\nesac\n',
            "security": "#!/bin/sh\nexit 44\n",  # never read a real keychain
        }
        for name, body in fakes.items():
            (self.fakebin / name).write_text(body)
            (self.fakebin / name).chmod(0o755)
        self.env = {**self.fake_env, "PATH": f"{self.fakebin}:{os.environ['PATH']}",
                    "FAKE_LOG": str(self.log), "FAKE_ON": str(self.on)}
        os.environ.update(self.fake_env)
        for k in ("CLAUDE_CONFIG_DIR", "CODEX_HOME"):  # a developer's own login dirs
            os.environ.pop(k, None)
        self.snap = self.state / "usage" / "snapshot.json"

    def write_claude_login(self, expires_ms=None, access="claude-access", refresh="old-refresh"):
        d = self.home / ".claude"
        d.mkdir(exist_ok=True)
        expires_ms = expires_ms if expires_ms is not None else (int(time.time()) + 7200) * 1000
        p = d / ".credentials.json"
        p.write_text(json.dumps({"claudeAiOauth": {
            "accessToken": access, "refreshToken": refresh, "expiresAt": expires_ms,
            "scopes": ["user:profile"], "subscriptionType": "max"}, "other": {"keep": 1}}))
        p.chmod(0o600)
        return p

    def write_codex_login(self, token):
        d = self.home / ".codex"
        d.mkdir(exist_ok=True)
        (d / "auth.json").write_text(json.dumps({"tokens": {"access_token": token, "account_id": "acct-1"}}))

    def poll(self, platform="linux"):
        return self.estate_script("poll", platform)

    def estate_script(self, *args, platform="linux"):
        import subprocess
        e = dict(os.environ) | self.env | {
            "ESTATE_ROOT": str(ROOT), "ESTATE_CONFIG": str(self.cfg_path),
            "ESTATE_STATE": str(self.state), "ESTATE_PLATFORM": platform}
        return subprocess.run([str(POLL), *args], capture_output=True, text=True, env=e,
                              stdin=subprocess.DEVNULL)


class Parsing(unittest.TestCase):
    def test_claude_limits(self):
        rows = U.parse_claude_limits(CLAUDE_USAGE)
        self.assertEqual([U.label(r) for r in rows], ["5h", "7d", "opus"])
        self.assertEqual(rows[0]["percent"], 42.0)
        self.assertEqual(rows[0]["resets_at"], 1792681200)
        self.assertEqual(rows[2]["model"], "Opus")  # the junk row is dropped

    def test_claude_old_shape(self):
        rows = U.parse_claude_limits(CLAUDE_OLD)
        self.assertEqual([(U.label(r), r["percent"]) for r in rows], [("5h", 9.0), ("7d", 3.5)])

    def test_codex(self):
        p = U.parse_codex_usage(CODEX_USAGE)
        self.assertEqual([(U.label(r), r["percent"], r["resets_at"]) for r in p["limits"]],
                         [("5h", 12.0, 1790000000), ("7d", 55.5, 1790500000)])
        self.assertEqual(p["plan"], "plus")
        self.assertFalse(p["limit_reached"])

    def test_garbage_is_empty_not_a_crash(self):
        self.assertEqual(U.parse_claude_limits({"limits": "x"}), [])
        self.assertEqual(U.parse_codex_usage({"rate_limit": 5})["limits"], [])

    def test_atomic_write_leaves_no_temp_and_keeps_old_on_failure(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "snap.json"
            U.write_json_atomic(p, {"a": 1}, mode=0o600)
            self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")
            with self.assertRaises(TypeError):
                U.write_json_atomic(p, {"a": object()})
            self.assertEqual(json.loads(p.read_text()), {"a": 1})
            self.assertEqual([x.name for x in p.parent.iterdir()], ["snap.json"])


class Polling(UsageBase):
    def setUp(self):
        super().setUp()
        self.write_config(["usage"], "\n[harnesses.codex]\n")

    def test_happy_path_both_harnesses(self):
        self.write_claude_login()
        self.write_codex_login(self.srv.good_codex_token)
        p = self.poll()
        self.assertEqual(p.returncode, 0, p.stderr)
        snap = json.loads(self.snap.read_text())
        by = {a["harness"]: a for a in snap["accounts"]}
        self.assertEqual(by["claude"]["status"], "ok")
        self.assertEqual([U.label(r) for r in by["claude"]["limits"]], ["5h", "7d", "opus"])
        self.assertEqual(by["claude"]["plan"], "max")
        self.assertEqual(by["codex"]["status"], "ok")
        self.assertEqual(by["codex"]["plan"], "plus")
        self.assertEqual(oct(self.snap.stat().st_mode & 0o777), "0o600")
        self.assertNotIn("claude-access", self.snap.read_text())  # no token in the snapshot
        shown = self.estate_script("show").stdout
        self.assertIn("42%", shown)
        self.assertIn("55%", shown)
        self.assertNotIn("STALE", shown)
        self.assertFalse(json.loads(self.estate_script("show", "--json").stdout)["stale"])

    def test_expired_claude_token_is_refreshed_and_written_back(self):
        self.write_config(["usage"], "\n[modules.usage]\nrefresh_login = true\n")
        creds = self.write_claude_login(expires_ms=1000, access="stale-access")
        self.srv.good_claude_token = "new-access"
        p = self.poll()
        self.assertEqual(p.returncode, 0, p.stderr)
        acc = json.loads(self.snap.read_text())["accounts"][0]
        self.assertEqual(acc["status"], "ok")
        self.assertTrue(acc["token"]["refreshed"])
        stored = json.loads(creds.read_text())
        self.assertEqual(stored["claudeAiOauth"]["accessToken"], "new-access")
        self.assertEqual(stored["claudeAiOauth"]["refreshToken"], "new-refresh")
        self.assertEqual(stored["claudeAiOauth"]["subscriptionType"], "max")
        self.assertEqual(stored["other"], {"keep": 1})
        self.assertEqual(oct(creds.stat().st_mode & 0o777), "0o600")

    def test_valid_token_is_never_refreshed(self):
        creds = self.write_claude_login()
        before = creds.read_text()
        self.poll()
        self.assertFalse([h for h in self.srv.hits if h[0] == "/token"])
        self.assertEqual(creds.read_text(), before)

    def test_refresh_is_off_by_default_reports_expired_and_writes_nothing(self):
        creds = self.write_claude_login(expires_ms=1000)
        before = creds.read_text()
        self.poll()
        self.assertEqual(json.loads(self.snap.read_text())["accounts"][0]["status"], "expired")
        self.assertEqual(creds.read_text(), before)
        self.assertFalse([h for h in self.srv.hits if h[0] == "/token"])

    def test_failed_refresh_leaves_login_alone(self):
        self.write_config(["usage"], "\n[modules.usage]\nrefresh_login = true\n")
        creds = self.write_claude_login(expires_ms=1000, refresh="revoked")
        before = creds.read_text()
        self.poll()
        status = json.loads(self.snap.read_text())["accounts"][0]["status"]
        self.assertTrue(status.startswith("refresh_failed"), status)
        self.assertEqual(creds.read_text(), before)

    def test_expired_codex_is_not_called_or_written(self):
        tok = jwt(int(time.time()) - 10)
        self.write_codex_login(tok)
        self.poll()
        acc = [a for a in json.loads(self.snap.read_text())["accounts"] if a["harness"] == "codex"][0]
        self.assertEqual(acc["status"], "expired")
        self.assertFalse([h for h in self.srv.hits if h[0] == "/wham/usage"])

    def test_no_login_and_stale_numbers_carry_over(self):
        self.write_claude_login()
        self.poll()
        self.srv.good_claude_token = "something-else"  # now the API says 401
        self.poll()
        acc = [a for a in json.loads(self.snap.read_text())["accounts"] if a["harness"] == "claude"][0]
        self.assertEqual(acc["status"], "expired")
        self.assertTrue(acc["stale"])
        self.assertEqual(U.label(acc["limits"][0]), "5h")
        codex = [a for a in json.loads(self.snap.read_text())["accounts"] if a["harness"] == "codex"][0]
        self.assertEqual(codex["status"], "no_login")
        self.assertIn("stale numbers", self.estate_script("show").stdout)

    def test_extra_account_reads_its_own_dir(self):
        self.write_config(["usage"], '\n[harnesses.claude]\naccounts = ["default", "spare"]\n')
        self.write_claude_login()
        spare = self.home / ".claude-spare"
        spare.mkdir()
        (spare / ".credentials.json").write_text(json.dumps(
            {"claudeAiOauth": {"accessToken": "claude-access", "expiresAt": (int(time.time()) + 999) * 1000}}))
        # base config declares [harnesses.claude] twice; use a clean one instead
        self.cfg_path.write_text(self.cfg_path.read_text().replace("\n[harnesses.claude]\n\n[modules]",
                                                                   "\n[modules]", 1))
        p = self.poll()
        self.assertEqual(p.returncode, 0, p.stderr)
        names = [(a["account"], a["status"]) for a in json.loads(self.snap.read_text())["accounts"]
                 if a["harness"] == "claude"]
        self.assertEqual(names, [("default", "ok"), ("spare", "ok")])


class Lifecycle(PinnedPythonMac, UsageBase):
    module, output = "usage", "usage/snapshot.json"

    def prepare(self):
        self.write_config(["usage"])
        self.write_claude_login()

    def run_estate(self, *args, platform="linux"):
        return self.estate(*args, env=self.env | {"ESTATE_PLATFORM": platform})

    def row(self, platform="linux"):
        p = self.run_estate("doctor", "--json", platform=platform)
        return {r["name"]: r for r in json.loads(p.stdout)["checks"]}["usage"]

    def test_install_check_statuses_uninstall_linux(self):
        self.write_config(["usage"], '\n[modules.usage]\ninterval_seconds = 300\n')
        self.assertEqual(self.row()["status"], 1)
        self.assertIn("not installed", self.row()["summary"])

        p = self.run_estate("install", "usage", "--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("would write", p.stderr)
        self.assertFalse(self.snap.exists())
        self.assertNotIn("enable --now", self.log.read_text() if self.log.exists() else "")

        self.write_claude_login()
        p = self.run_estate("install", "usage")
        self.assertEqual(p.returncode, 0, p.stderr)
        unit = self.home / ".config/systemd/user"
        label = "com.example.estate.usage"
        self.assertIn("OnUnitActiveSec=300s", (unit / f"{label}.timer").read_text())
        self.assertIn("poll.sh poll", (unit / f"{label}.service").read_text())
        self.assertIn("enable --now com.example.estate.usage.timer", self.log.read_text())
        self.assertTrue(self.snap.exists())  # first poll at install
        self.assertEqual(self.run_estate("install", "usage").returncode, 0)  # idempotent

        # one configured harness (claude) with a good login: ok
        r = self.row()
        self.assertEqual((r["status"], r["summary"].split(" polled")[0]), (0, "1 account(s)"), r)
        shown = self.run_estate("config", "get", "paths.bin").stdout.strip()
        show = Path(shown) / "usage-show"
        import subprocess
        out = subprocess.run([str(show)], capture_output=True, text=True, env=dict(os.environ) | self.env)
        self.assertIn("42%", out.stdout, out.stderr)

        # an errored account warns
        self.srv.good_claude_token = "revoked"
        self.estate_script("poll")
        self.assertEqual(self.row()["status"], 2)
        self.assertIn("claude/default expired", self.row()["summary"])

        # a snapshot older than 3 intervals warns
        snap = json.loads(self.snap.read_text())
        snap["observed_at"] -= 3 * 300 + 60
        for a in snap["accounts"]:
            a["status"] = "ok"
        self.snap.write_text(json.dumps(snap))
        r = self.row()
        self.assertEqual(r["status"], 2)
        self.assertIn("old", r["summary"])

        # missing snapshot fails
        self.snap.unlink()
        self.assertEqual(self.row()["status"], 1)
        self.assertIn("no usage snapshot", self.row()["summary"])

        # timer not loaded fails
        self.on.unlink()
        self.assertIn("not enabled", self.row()["summary"])

        # config drift fails
        self.write_config(["usage"], '\n[modules.usage]\ninterval_seconds = 900\n')
        self.assertIn("does not match estate.toml", self.row()["summary"])

        self.assertEqual(self.run_estate("uninstall", "usage").returncode, 0)
        self.assertFalse((unit / f"{label}.timer").exists() or (Path(shown) / "usage-show").exists())

    def test_install_check_mac(self):
        self.write_config(["usage"])
        self.write_claude_login()
        p = self.run_estate("install", "usage", platform="mac")
        self.assertEqual(p.returncode, 0, p.stderr)
        plist = self.home / "Library/LaunchAgents/com.example.estate.usage.plist"
        self.assertIn("<integer>600</integer>", plist.read_text())
        self.assertIn("bootstrap gui/", self.log.read_text())
        self.assertEqual(self.row("mac")["status"], 0, self.row("mac"))
        self.on.unlink()
        self.assertIn("not loaded", self.row("mac")["summary"])

    def test_bad_interval_refused(self):
        self.write_config(["usage"], '\n[modules.usage]\ninterval_seconds = 5\n')
        p = self.run_estate("install", "usage")
        self.assertEqual(p.returncode, 1)
        self.assertIn("60 or more", p.stderr)


if __name__ == "__main__":
    unittest.main()
