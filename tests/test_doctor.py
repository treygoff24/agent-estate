import shutil
import json
import os

from tests.helpers import ROOT, TempHome, write_module

from estate import doctor as D
from estate import modules as M

OK, FAIL, WARN = M.OK, M.FAIL, M.WARN


def rows(*statuses):
    return [{"name": f"r{i}", "status": s, "summary": "", "done_when": "", "output": ""}
            for i, s in enumerate(statuses)]


class Aggregate(TempHome):
    def test_worst_ranks_fail_over_warn_over_ok(self):
        self.assertEqual(D.worst([]), OK)
        self.assertEqual(D.worst(rows(OK, OK)), OK)
        self.assertEqual(D.worst(rows(OK, WARN, OK)), WARN)
        self.assertEqual(D.worst(rows(WARN, FAIL, OK)), FAIL)
        self.assertEqual(D.worst(rows(FAIL, WARN)), FAIL)

    def _run(self, platform="linux"):
        mdir = self.tmp / "modules"
        write_module(mdir, "good", check='echo "ok: fine"; echo "done when: always"')
        write_module(mdir, "meh", check='echo "warn: hmm"; echo "done when: later"; exit 2')
        write_module(mdir, "weird", check='echo "something odd"; exit 7')
        write_module(mdir, "stub")
        write_module(mdir, "maconly", platforms='["mac"]', check="exit 1")
        write_module(mdir, "needy", meta='[prerequisites]\nlinux = ["no-such-cmd-xyz"]\n',
                     check="exit 0")
        write_module(mdir, "envcheck", check=(
            'for v in ESTATE_CONFIG ESTATE_ROOT ESTATE_STATE ESTATE_PLATFORM ESTATE_MODULE '
            'ESTATE_MODULE_DIR; do [ -n "${!v}" ] || { echo "fail: $v unset"; exit 1; }; done\n'
            'echo "ok: $ESTATE_PLATFORM $ESTATE_MODULE $ESTATE_MACHINE"'))
        os.environ["ESTATE_MACHINE"] = "vps"
        names = ["good", "meh", "weird", "stub", "maconly", "needy", "envcheck"]
        self.write_config(names)
        known = M.discover(mdir)
        return {r["name"]: r for r in D.run(platform, self.cfg_path, known, core=[])[0]}

    def test_module_rows(self):
        r = self._run()
        self.assertEqual((r["good"]["status"], r["good"]["summary"]), (OK, "fine"))
        self.assertEqual(r["good"]["done_when"], "always")
        self.assertEqual((r["meh"]["status"], r["meh"]["done_when"]), (WARN, "later"))
        self.assertEqual(r["weird"]["status"], FAIL)
        self.assertIn("check exited 7", r["weird"]["summary"])
        self.assertEqual(r["stub"]["status"], WARN)
        self.assertIn("not built yet", r["stub"]["summary"])
        self.assertEqual((r["maconly"]["status"], r["maconly"]["summary"]),
                         (OK, "not used on linux"))
        self.assertEqual(r["needy"]["status"], FAIL)
        self.assertIn("no-such-cmd-xyz", r["needy"]["summary"])
        self.assertEqual((r["envcheck"]["status"], r["envcheck"]["summary"]),
                         (OK, "linux envcheck vps"))
        self.assertEqual(r["core:config"]["status"], OK)
        self.assertEqual(D.worst(r.values()), FAIL)

    def test_bad_config_is_a_failed_row_not_a_crash(self):
        self.cfg_path.write_text("this is not toml")
        r, cfg = D.run("mac", self.cfg_path, {}, core=[])
        self.assertIsNone(cfg)
        self.assertEqual([(x["name"], x["status"]) for x in r], [("core:config", FAIL)])

    def test_table_shows_done_when_only_for_problems(self):
        table = D.format_table([
            {"name": "a", "status": OK, "summary": "fine", "done_when": "x-ok", "output": ""},
            {"name": "b", "status": WARN, "summary": "hmm", "done_when": "x-warn", "output": ""}])
        self.assertIn("a      ok      fine", table)
        self.assertNotIn("x-ok", table)
        self.assertIn("done when: x-warn", table)


class CoreChecks(TempHome):
    def fake(self, systemd="running", linger="yes"):
        def run(cmd):
            if cmd[:2] == ["systemctl", "--user"]:
                return (0 if systemd == "running" else 1), systemd
            if cmd[0] == "loginctl":
                return 0, linger
            raise AssertionError(cmd)
        return run

    def statuses(self, platform, **kw):
        version = kw.pop("version", (3, 12, 1))
        which = kw.pop("which", lambda c: "/usr/bin/" + c)
        got = D.core_checks(platform, run=self.fake(**kw), which=which, version=version)
        return {r["name"]: r["status"] for r in got}

    def test_linux_all_good(self):
        self.assertEqual(self.statuses("linux"), {"core:python": OK, "core:git": OK,
                                                  "core:systemd-user": OK, "core:linger": OK})

    def test_linux_problems(self):
        s = self.statuses("linux", systemd="degraded", linger="no")
        self.assertEqual((s["core:systemd-user"], s["core:linger"]), (WARN, FAIL))
        s = self.statuses("linux", systemd="offline")
        self.assertEqual(s["core:systemd-user"], FAIL)

    def test_old_python_and_missing_git(self):
        s = self.statuses("mac", version=(3, 10, 4), which=lambda c: None)
        self.assertEqual(s, {"core:python": FAIL, "core:git": FAIL})


class DoctorCli(TempHome):
    def test_doctor_on_this_repo_exit_codes_and_json(self):
        self.write_config(["tmp-cleanup"])
        env = {"ESTATE_PLATFORM": "mac"}
        p = self.estate("doctor", env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("doctor: ok", p.stdout)
        p = self.estate("doctor", "--json", env=env)
        data = json.loads(p.stdout)
        self.assertEqual((data["status"], data["exit"]), ("ok", 0))
        self.assertIn("tmp-cleanup", [c["name"] for c in data["checks"]])

        mdir = self.tmp / "modules"
        shutil.copytree(ROOT / "modules" / "tmp-cleanup", mdir / "tmp-cleanup")
        write_module(mdir, "stubby")
        self.write_config(["tmp-cleanup", "stubby"])  # an enabled stub: warn
        p = self.estate("doctor", env=env | {"ESTATE_MODULES_DIR": str(mdir)})
        self.assertEqual(p.returncode, 2, p.stdout)
        self.cfg_path.write_text("broken = [")
        p = self.estate("doctor", env=env)
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertFalse(os.path.exists(self.home / ".local"))
