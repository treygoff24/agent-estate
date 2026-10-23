"""Load and validate estate.toml, the one file a newcomer fills in.

The schema lives in this file and nowhere else. `load()` returns a plain
dict with defaults applied and every path expanded; `ConfigError` carries
every problem found, one per line, so a user fixes them all in one pass.
"""

from __future__ import annotations

import os
import re
import socket
import sys
import tomllib
from pathlib import Path

DEFAULT_CONFIG = "~/.config/agent-estate/estate.toml"

PLATFORMS = ("mac", "linux")
ROLES = ("workstation", "agents", "server")

DEFAULT_PATHS = {
    "code": "~/Code",
    "skills": "~/.agents/skill-library",
    "state": "~/.local/state/agent-estate",
    "bin": "~/.local/bin",
}
DEFAULT_KEYS_FILE = "~/.config/agent-estate/keys.env"
DEFAULT_ACCOUNT = "default"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PREFIX_RE = re.compile(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HOST_RE = re.compile(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*$")
KEY_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

TOP_KEYS = {"user", "label_prefix", "tailnet", "git", "paths", "machines",
            "harnesses", "keys", "modules"}


class ConfigError(Exception):
    """One or more problems with estate.toml; str() lists them all."""

    def __init__(self, path, problems):
        self.path = str(path)
        self.problems = list(problems)
        lines = [f"{self.path}: {p}" for p in self.problems]
        super().__init__("\n".join(lines))


def config_path() -> Path:
    """Where the config lives: $ESTATE_CONFIG, else the default location."""
    return Path(os.path.expanduser(os.environ.get("ESTATE_CONFIG") or DEFAULT_CONFIG))


def current_platform() -> str:
    """'mac' or 'linux'. $ESTATE_PLATFORM overrides (tests, cross-checks)."""
    forced = os.environ.get("ESTATE_PLATFORM")
    if forced:
        if forced not in PLATFORMS:
            raise ValueError(f"ESTATE_PLATFORM must be one of {PLATFORMS}, got {forced!r}")
        return forced
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("linux"):
        return "linux"
    raise ValueError(f"unsupported platform {sys.platform!r}: agent-estate runs on macOS and Linux")


def _expand(p: str) -> str:
    return os.path.expanduser(os.path.expandvars(p))


def _check_str(problems, where, value, pattern=None, hint="", allow_empty=False):
    if not isinstance(value, str):
        problems.append(f"{where}: must be a string (got {type(value).__name__})")
        return False
    if not value and not allow_empty:
        problems.append(f"{where}: must not be empty")
        return False
    if value and pattern is not None and not pattern.match(value):
        problems.append(f"{where}: {value!r} is not valid{': ' + hint if hint else ''}")
        return False
    return True


def _check_table(problems, where, value, allowed):
    if not isinstance(value, dict):
        problems.append(f"{where}: must be a table")
        return False
    for k in value:
        if k not in allowed:
            problems.append(f"{where}.{k}: unknown key (allowed: {', '.join(sorted(allowed))})")
    return True


def _str_list(problems, where, value, pattern=None, hint=""):
    if not isinstance(value, list):
        problems.append(f"{where}: must be a list of strings")
        return []
    out = []
    for i, v in enumerate(value):
        if _check_str(problems, f"{where}[{i}]", v, pattern, hint):
            out.append(v)
    if len(set(out)) != len(out):
        problems.append(f"{where}: has duplicate entries")
    return out


def validate(raw: dict, known_modules: dict | None = None, path="estate.toml") -> dict:
    """Validate a parsed config and return it normalised.

    known_modules maps module name -> module.toml dict (see modules.py). When
    given, modules.enabled and each [modules.<name>] settings table are
    checked against it, and each module's [defaults] are filled in under
    modules.<name>.
    """
    problems: list[str] = []
    cfg: dict = {}

    for k in raw:
        if k not in TOP_KEYS:
            problems.append(f"{k}: unknown top-level key (allowed: {', '.join(sorted(TOP_KEYS))})")

    user = raw.get("user")
    if user is None:
        problems.append("user: missing; add [user] with name and email")
        user = {}
    elif _check_table(problems, "user", user, {"name", "email"}):
        _check_str(problems, "user.name", user.get("name"))
        _check_str(problems, "user.email", user.get("email"), EMAIL_RE, "expected you@example.com")
    cfg["user"] = dict(user) if isinstance(user, dict) else {}

    prefix = raw.get("label_prefix")
    if prefix is None:
        problems.append('label_prefix: missing; e.g. label_prefix = "com.example.estate"')
    else:
        _check_str(problems, "label_prefix", prefix, PREFIX_RE,
                   'reverse-DNS like "com.example.estate"')
    cfg["label_prefix"] = prefix

    tailnet = raw.get("tailnet", "")
    _check_str(problems, "tailnet", tailnet, HOST_RE, 'e.g. "example.ts.net", or "" for none',
               allow_empty=True)
    cfg["tailnet"] = tailnet

    git = raw.get("git")
    if git is None:
        problems.append('git: missing; add [git] remote_base = "git@github.com:<you>"')
        git = {}
    elif _check_table(problems, "git", git, {"remote_base"}):
        _check_str(problems, "git.remote_base", git.get("remote_base"))
    cfg["git"] = dict(git) if isinstance(git, dict) else {}

    paths = raw.get("paths", {})
    cfg["paths"] = {}
    if _check_table(problems, "paths", paths, set(DEFAULT_PATHS)):
        for k, default in DEFAULT_PATHS.items():
            v = paths.get(k, default)
            if _check_str(problems, f"paths.{k}", v):
                cfg["paths"][k] = _expand(v)

    machines = raw.get("machines")
    cfg["machines"] = []
    if not machines:
        problems.append("machines: missing; add at least one [[machines]] entry")
    elif not isinstance(machines, list):
        problems.append("machines: must be an array of tables ([[machines]])")
    else:
        seen = set()
        for i, m in enumerate(machines):
            where = f"machines[{i}]"
            if not _check_table(problems, where, m, {"name", "ssh", "role", "os", "hostname"}):
                continue
            ok = _check_str(problems, f"{where}.name", m.get("name"), NAME_RE,
                            "lowercase letters, digits, dashes")
            if ok:
                if m["name"] in seen:
                    problems.append(f"{where}.name: {m['name']!r} is used twice")
                seen.add(m["name"])
            _check_str(problems, f"{where}.ssh", m.get("ssh", m.get("name", "")))
            role = m.get("role")
            if role not in ROLES:
                problems.append(f"{where}.role: must be one of {', '.join(ROLES)} (got {role!r})")
            osname = m.get("os")
            if osname not in PLATFORMS:
                problems.append(f"{where}.os: must be 'mac' or 'linux' (got {osname!r})")
            if "hostname" in m:
                _check_str(problems, f"{where}.hostname", m["hostname"], HOST_RE)
            entry = {"ssh": m.get("name")} | dict(m)
            entry.setdefault("hostname", "")
            cfg["machines"].append(entry)

    harnesses = raw.get("harnesses")
    cfg["harnesses"] = {}
    if not harnesses:
        problems.append("harnesses: missing; add e.g. [harnesses.claude] (one table per harness you use)")
    elif not isinstance(harnesses, dict):
        problems.append("harnesses: must be a table of tables, e.g. [harnesses.claude]")
    else:
        for kind, h in harnesses.items():
            where = f"harnesses.{kind}"
            if not NAME_RE.match(kind):
                problems.append(f"{where}: harness name must be lowercase letters, digits, dashes")
            if not _check_table(problems, where, h, {"accounts"}):
                continue
            accounts = _str_list(problems, f"{where}.accounts",
                                 h.get("accounts", [DEFAULT_ACCOUNT]), NAME_RE,
                                 "lowercase letters, digits, dashes")
            if "accounts" in h and not h["accounts"]:
                problems.append(f"{where}.accounts: must list at least one account (or omit it)")
            cfg["harnesses"][kind] = {"accounts": accounts}

    keys = raw.get("keys", {})
    cfg["keys"] = {"file": _expand(DEFAULT_KEYS_FILE), "names": []}
    if _check_table(problems, "keys", keys, {"file", "names"}):
        f = keys.get("file", DEFAULT_KEYS_FILE)
        if _check_str(problems, "keys.file", f):
            cfg["keys"]["file"] = _expand(f)
        cfg["keys"]["names"] = _str_list(problems, "keys.names", keys.get("names", []),
                                         KEY_NAME_RE, "UPPER_SNAKE_CASE like EXA_API_KEY")

    # [modules] holds `enabled` plus one [modules.<name>] settings table per
    # module that has settings.
    mods = raw.get("modules", {})
    cfg["modules"] = {"enabled": []}
    settings: dict[str, dict] = {}
    if not isinstance(mods, dict):
        problems.append("modules: must be a table")
        mods = {}
    for k, v in mods.items():
        if k == "enabled":
            cfg["modules"]["enabled"] = _str_list(problems, "modules.enabled", v)
        elif isinstance(v, dict):
            settings[k] = dict(v)
        else:
            problems.append(f"modules.{k}: unknown key (expected `enabled`, or a "
                            f"[modules.<name>] settings table)")

    if known_modules is None:
        cfg["modules"] |= settings
    else:
        enabled = cfg["modules"]["enabled"]
        for i, name in enumerate(enabled):
            if name not in known_modules:
                problems.append(f"modules.enabled[{i}]: no module named {name!r} "
                                f"(known: {', '.join(sorted(known_modules))})")
        for name in enabled:
            for req in known_modules.get(name, {}).get("requires", []):
                if req not in enabled:
                    problems.append(f"modules.enabled: {name!r} requires {req!r}; enable it too")
        for name, table in settings.items():
            if name not in known_modules:
                problems.append(f"modules.{name}: no module named {name!r}")
                continue
            allowed = known_modules[name].get("defaults", {})
            for k in table:
                if k not in allowed:
                    problems.append(f"modules.{name}.{k}: unknown setting (module {name} has: "
                                    f"{', '.join(sorted(allowed)) or 'no settings'})")
        for name, meta in known_modules.items():
            defaults = meta.get("defaults", {})
            if defaults:
                cfg["modules"][name] = dict(defaults) | settings.get(name, {})
        # A rendered unit or plist cannot expand "~": keep the key shims' folder absolute.
        keys_table = cfg["modules"].get("keys", {})
        if isinstance(keys_table.get("shim_dir"), str):
            keys_table["shim_dir"] = _expand(keys_table["shim_dir"])

    if problems:
        raise ConfigError(path, problems)
    return cfg


def load(path: Path | None = None, known_modules: dict | None = None) -> dict:
    """Read, parse and validate the config file. Raises ConfigError."""
    path = path or config_path()
    if not path.is_file():
        raise ConfigError(path, [
            "no config file here. Copy estate.example.toml from the repo to this path "
            "and edit it, or point ESTATE_CONFIG at your config."])
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(path, [f"not valid TOML: {e}"]) from None
    cfg = validate(raw, known_modules, path)
    cfg["_path"] = str(path)
    return cfg


def get(cfg: dict, dotted: str):
    """Look up a dotted key. Machine entries are addressable by name:
    machines.vps.ssh. Raises KeyError with the key that failed."""
    node = cfg
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node and not part.startswith("_"):
            node = node[part]
        elif isinstance(node, list) and all(isinstance(x, dict) and "name" in x for x in node):
            match = [x for x in node if x["name"] == part]
            if not match:
                raise KeyError(dotted)
            node = match[0]
        else:
            raise KeyError(dotted)
    return node


def this_machine(cfg: dict, platform: str | None = None) -> dict | None:
    """Which configured machine this is.

    $ESTATE_MACHINE names it outright; otherwise the short hostname is
    matched against each machine's hostname or name; otherwise, if exactly
    one machine has this platform's os, it is that one. None if unknown.
    """
    machines = cfg.get("machines", [])
    forced = os.environ.get("ESTATE_MACHINE")
    if forced:
        return next((m for m in machines if m["name"] == forced), None)
    host = socket.gethostname().split(".")[0].lower()
    for m in machines:
        if host and host in {m.get("hostname", "").split(".")[0].lower(), m["name"].lower()}:
            return m
    platform = platform or current_platform()
    same_os = [m for m in machines if m.get("os") == platform]
    return same_os[0] if len(same_os) == 1 else None
