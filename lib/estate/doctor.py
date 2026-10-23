"""estate doctor: core prerequisites, then every enabled module's check.

Exit code is the worst row: 1 if anything failed, else 2 if anything
warned, else 0 (the same codes a module check uses).
"""

from __future__ import annotations

import getpass
import json
import shutil
import subprocess
import sys

from . import config as C
from . import modules as M

MIN_PYTHON = (3, 11)


def _row(name, status, summary, done_when=""):
    return {"name": name, "status": status, "summary": summary, "done_when": done_when,
            "output": ""}


def _run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                           stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def core_checks(platform: str, run=_run, which=shutil.which,
                version=sys.version_info) -> list[dict]:
    rows = []
    v = ".".join(map(str, version[:3]))
    rows.append(_row("core:python", M.OK if tuple(version[:2]) >= MIN_PYTHON else M.FAIL,
                     f"python {v}", "python3 on PATH is 3.11 or newer"))
    rows.append(_row("core:git", M.OK if which("git") else M.FAIL,
                     "git found" if which("git") else "git not on PATH", "git is on PATH"))
    if platform == "linux":
        rc, out = run(["systemctl", "--user", "is-system-running"])
        state = out.splitlines()[-1] if out else "unreachable"
        st = M.OK if state == "running" else M.WARN if state == "degraded" else M.FAIL
        rows.append(_row("core:systemd-user", st, f"systemd user manager: {state}",
                         "systemctl --user is-system-running says running"))
        rc, out = run(["loginctl", "show-user", getpass.getuser(), "-p", "Linger", "--value"])
        linger = out == "yes"
        rows.append(_row("core:linger", M.OK if linger else M.FAIL,
                         "linger on" if linger else f"linger off ({out or 'no answer'})",
                         "loginctl shows Linger=yes, so user timers run with nobody logged in "
                         "(an admin runs: sudo loginctl enable-linger <agent-login>)"))
    return rows


def worst(rows) -> int:
    if not rows:
        return M.OK
    return max((r["status"] for r in rows), key=lambda s: M.SEVERITY[s])


def run(platform: str, cfg_path=None, known=None, core=None) -> tuple[list[dict], dict | None]:
    """All rows, plus the config (None if it did not load)."""
    rows = list(core if core is not None else core_checks(platform))
    try:
        known = known if known is not None else M.discover()
    except M.ModuleError as e:
        rows.append(_row("core:modules", M.FAIL, str(e), "every module.toml is valid"))
        return rows, None
    try:
        cfg = C.load(cfg_path, known)
    except C.ConfigError as e:
        first = e.problems[0] if e.problems else str(e)
        more = f" (+{len(e.problems) - 1} more; run estate config check)" if len(e.problems) > 1 else ""
        rows.append(_row("core:config", M.FAIL, first + more, "estate config check passes"))
        return rows, None
    rows.append(_row("core:config", M.OK, cfg["_path"], "estate config check passes"))
    machine = C.this_machine(cfg, platform)
    rows.append(_row("core:machine", M.OK if machine else M.WARN,
                     f"this is {machine['name']}" if machine else
                     "cannot tell which [[machines]] entry this is",
                     "set hostname on its [[machines]] entry, or export ESTATE_MACHINE"))
    for name in M.install_order(cfg["modules"]["enabled"], known):
        if name in cfg["modules"]["enabled"]:
            rows.append(M.run_check(cfg, known[name], platform))
    return rows, cfg


def format_table(rows) -> str:
    w = max([len(r["name"]) for r in rows] + [5])
    out = [f"{'CHECK':<{w}}  STATUS  DETAIL"]
    for r in rows:
        out.append(f"{r['name']:<{w}}  {M.LABEL[r['status']]:<6}  {r['summary']}")
        if r["status"] != M.OK and r["done_when"]:
            out.append(f"{'':<{w}}          done when: {r['done_when']}")
    return "\n".join(out)


def main(platform: str, as_json: bool) -> int:
    rows, _ = run(platform)
    code = worst(rows)
    if as_json:
        print(json.dumps({"platform": platform, "status": M.LABEL[code].lower(),
                          "exit": code, "checks": rows}, indent=2))
    else:
        print(format_table(rows))
        n = {s: sum(r["status"] == s for r in rows) for s in (M.OK, M.WARN, M.FAIL)}
        print(f"\ndoctor: {M.LABEL[code].lower()} ({n[M.OK]} ok, {n[M.WARN]} warn, "
              f"{n[M.FAIL]} fail)")
    return code
