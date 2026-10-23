"""Discover modules, read module.toml, order installs, run module scripts.

The contract itself is written down in modules/README.md; this file is the
code that holds modules to it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from . import config as C

META_KEYS = {"name", "description", "platforms", "requires", "prerequisites", "defaults"}
PREREQ_KEYS = {"all", "mac", "linux"}

# Check exit codes, and the order doctor ranks them in (worst last).
OK, FAIL, WARN = 0, 1, 2
SEVERITY = {OK: 0, WARN: 1, FAIL: 2}
LABEL = {OK: "ok", WARN: "warn", FAIL: "FAIL"}

CHECK_TIMEOUT = 60


class ModuleError(Exception):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_meta(mod_dir: Path) -> dict:
    """Parse and validate modules/<name>/module.toml."""
    f = mod_dir / "module.toml"
    where = f"{mod_dir.name}/module.toml"
    if not f.is_file():
        raise ModuleError(f"{where}: missing")
    try:
        meta = tomllib.loads(f.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ModuleError(f"{where}: not valid TOML: {e}") from None
    problems = [f"unknown key {k!r}" for k in meta if k not in META_KEYS]
    if meta.get("name") != mod_dir.name:
        problems.append(f"name must equal the directory name {mod_dir.name!r}")
    if not C.NAME_RE.match(mod_dir.name) or mod_dir.name == "enabled":
        problems.append("directory name must be lowercase letters, digits, dashes (not 'enabled')")
    if not isinstance(meta.get("description"), str) or not meta.get("description"):
        problems.append("description: missing")
    plats = meta.get("platforms")
    if not isinstance(plats, list) or not plats or any(p not in C.PLATFORMS for p in plats):
        problems.append("platforms: must be a non-empty list drawn from 'mac', 'linux'")
    req = meta.setdefault("requires", [])
    if not isinstance(req, list) or not all(isinstance(r, str) for r in req):
        problems.append("requires: must be a list of module names")
    pre = meta.setdefault("prerequisites", {})
    if not isinstance(pre, dict) or any(k not in PREREQ_KEYS for k in pre) or not all(
            isinstance(v, list) and all(isinstance(x, str) for x in v) for v in pre.values()):
        problems.append("prerequisites: must be a table with lists 'all', 'mac', 'linux' "
                        "of commands that must be on PATH")
    if not isinstance(meta.setdefault("defaults", {}), dict):
        problems.append("defaults: must be a table")
    if problems:
        raise ModuleError(f"{where}: " + "; ".join(problems))
    meta["dir"] = str(mod_dir)
    meta["has_install"] = _executable(mod_dir / "install")
    meta["has_check"] = _executable(mod_dir / "check")
    meta["has_uninstall"] = _executable(mod_dir / "uninstall")
    meta["stub"] = not (meta["has_install"] or meta["has_check"])
    return meta


def _executable(p: Path) -> bool:
    return p.is_file() and os.access(p, os.X_OK)


def discover(modules_dir: Path | None = None) -> dict:
    """name -> meta for every directory under modules/ holding a module.toml."""
    if modules_dir is None:
        override = os.environ.get("ESTATE_MODULES_DIR")
        modules_dir = Path(override) if override else repo_root() / "modules"
    found = {}
    for d in sorted(modules_dir.iterdir()):
        if d.is_dir() and (d / "module.toml").exists():
            found[d.name] = read_meta(d)
    for name, meta in found.items():
        for r in meta["requires"]:
            if r not in found:
                raise ModuleError(f"{name}/module.toml: requires unknown module {r!r}")
    return found


def install_order(names, known: dict) -> list[str]:
    """Requested modules plus everything they require, dependencies first.
    Stable: ties keep the order the names were given in. Raises on cycles."""
    order: list[str] = []
    state: dict[str, str] = {}

    def visit(n, chain):
        if n not in known:
            raise ModuleError(f"no module named {n!r} (known: {', '.join(sorted(known))})")
        if state.get(n) == "done":
            return
        if state.get(n) == "active":
            raise ModuleError("requires cycle: " + " -> ".join(chain + [n]))
        state[n] = "active"
        for r in known[n]["requires"]:
            visit(r, chain + [n])
        state[n] = "done"
        order.append(n)

    for n in names:
        visit(n, [])
    return order


def missing_prereqs(meta: dict, platform: str) -> list[str]:
    pre = meta.get("prerequisites", {})
    cmds = list(pre.get("all", [])) + list(pre.get(platform, []))
    return [c for c in cmds if shutil.which(c) is None]


def script_env(cfg: dict, meta: dict, platform: str) -> dict:
    """The environment every module script gets (documented in modules/README.md)."""
    env = dict(os.environ)
    machine = C.this_machine(cfg, platform)
    env.update({
        "ESTATE_CONFIG": cfg["_path"],
        "ESTATE_ROOT": str(repo_root()),
        "ESTATE_STATE": cfg["paths"]["state"],
        "ESTATE_PLATFORM": platform,
        "ESTATE_MACHINE": machine["name"] if machine else "",
        "ESTATE_MODULE": meta["name"],
        "ESTATE_MODULE_DIR": meta["dir"],
    })
    return env


def run_script(cfg, meta, script, platform, args=(), capture=False, timeout=None):
    path = Path(meta["dir"]) / script
    Path(cfg["paths"]["state"]).mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [str(path), *args], env=script_env(cfg, meta, platform), cwd=meta["dir"],
        capture_output=capture, text=True, timeout=timeout, stdin=subprocess.DEVNULL)


def run_check(cfg, meta, platform) -> dict:
    """Run one module's check. Returns {module, status, summary, done_when, output}.
    status is OK/WARN/FAIL; any exit code other than 0 or 2 counts as FAIL."""
    row = {"name": meta["name"], "summary": "", "done_when": "", "output": ""}
    if platform not in meta["platforms"]:
        return row | {"status": OK, "summary": f"not used on {platform}"}
    if not meta["has_check"]:
        return row | {"status": WARN, "summary": "not built yet (module has no check script)"}
    missing = missing_prereqs(meta, platform)
    if missing:
        return row | {"status": FAIL, "summary": "missing prerequisites: " + ", ".join(missing),
                      "done_when": "every listed command is on PATH"}
    try:
        p = run_script(cfg, meta, "check", platform, capture=True, timeout=CHECK_TIMEOUT)
    except subprocess.TimeoutExpired:
        return row | {"status": FAIL, "summary": f"check timed out after {CHECK_TIMEOUT}s"}
    out = (p.stdout or "") + (p.stderr or "")
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    status = p.returncode if p.returncode in (OK, WARN) else FAIL
    summary = lines[0] if lines else "(check printed nothing)"
    word, _, rest = summary.partition(":")
    if word.lower() in ("ok", "warn", "fail") and rest.strip():
        summary = rest.strip()  # the STATUS column already says it
    if p.returncode not in (OK, FAIL, WARN):
        summary = f"check exited {p.returncode}: {summary}"
    done_when = next((ln.split(":", 1)[1].strip() for ln in lines
                      if ln.lower().startswith("done when:")), "")
    return row | {"status": status, "summary": summary, "done_when": done_when, "output": out}
