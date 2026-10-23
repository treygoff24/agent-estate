"""The `estate` command. See `estate --help`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config as C
from . import doctor as D
from . import modules as M
from . import render as R


def _die(msg: str, code: int = 1) -> int:
    print(f"estate: {msg}", file=sys.stderr)
    return code


def _load():
    known = M.discover()
    return C.load(None, known), known


def cmd_config(args) -> int:
    if args.action == "check":
        try:
            cfg, _ = _load()
        except (C.ConfigError, M.ModuleError) as e:
            print(e, file=sys.stderr)
            return 1
        print(f"ok: {cfg['_path']}")
        return 0
    if args.action == "path":
        print(C.config_path())
        return 0
    if not args.key:
        return _die("config get needs a dotted key, e.g. estate config get paths.code")
    cfg, _ = _load()
    try:
        value = C.get(cfg, args.key)
    except KeyError:
        return _die(f"no such config key: {args.key}")
    if args.json:
        print(json.dumps(value))
    elif isinstance(value, list) and all(not isinstance(v, (dict, list)) for v in value):
        for v in value:
            print(v)
    elif isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2))
    elif isinstance(value, bool):
        print("true" if value else "false")
    else:
        print(value)
    return 0


def cmd_render(args) -> int:
    cfg, _ = _load()
    text = R.render_file(cfg, Path(args.template), args.module, C.current_platform())
    if args.out:
        R.write_atomic(Path(args.out).expanduser(), text)
    else:
        sys.stdout.write(text)
    return 0


def cmd_label(args) -> int:
    cfg, known = _load()
    if args.module not in known:
        return _die(f"no module named {args.module!r}")
    print(R.label(cfg, args.module))
    return 0


def cmd_list(args) -> int:
    known = M.discover()
    try:
        enabled = set(C.load(None, known)["modules"]["enabled"])
    except C.ConfigError:
        enabled = set()
    w = max(len(n) for n in known)
    for name, meta in known.items():
        state = "stub" if meta["stub"] else "ready"
        flag = "enabled" if name in enabled else "-"
        print(f"{name:<{w}}  {state:<5}  {flag:<7}  {'/'.join(meta['platforms']):<10}  "
              f"{meta['description']}")
    return 0


def cmd_install(args, script="install") -> int:
    cfg, known = _load()
    platform = C.current_platform()
    names = args.modules or cfg["modules"]["enabled"]
    if not names:
        return _die("nothing to do: name modules, or list them in modules.enabled")
    order = M.install_order(names, known)
    if script == "uninstall":  # only what was named, dependents first
        order = [n for n in reversed(order) if n in names]
    extra = ["--dry-run"] if args.dry_run else []
    worst = 0
    for name in order:
        meta = known[name]
        if platform not in meta["platforms"]:
            print(f"== {name}: skipped (not used on {platform})")
            continue
        has = meta[f"has_{script}"]
        if not has:
            if script == "uninstall":
                print(f"== {name}: nothing to uninstall (module has no uninstall script)")
                continue
            print(f"== {name}: not built yet (module has no {script} script)")
            worst = 1
            break
        missing = M.missing_prereqs(meta, platform)
        if missing:
            print(f"== {name}: missing prerequisites: {', '.join(missing)}")
            worst = 1
            break
        note = "" if name in cfg["modules"]["enabled"] else \
            " (not in modules.enabled, so doctor will not check it)"
        print(f"== {name}: {script}{' --dry-run' if extra else ''}{note}", flush=True)
        rc = M.run_script(cfg, meta, script, platform, extra).returncode
        if rc != 0:
            print(f"== {name}: {script} failed (exit {rc}); stopping")
            worst = 1
            break
    return worst


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="estate",
        description="Run coding agents across a Mac and Linux boxes as one system.",
        epilog="Config: $ESTATE_CONFIG, default ~/.config/agent-estate/estate.toml")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("config", help="read or validate estate.toml")
    c.add_argument("action", choices=["get", "check", "path"])
    c.add_argument("key", nargs="?", help="dotted key, e.g. paths.code or machines.vps.ssh")
    c.add_argument("--json", action="store_true", help="print the value as JSON")

    r = sub.add_parser("render", help="fill ${...} placeholders in a template from the config")
    r.add_argument("template")
    r.add_argument("--out", help="write here (atomically) instead of stdout")
    r.add_argument("--module", help="module name for ${label}/${module} "
                                    "(default: from the template's path)")

    lb = sub.add_parser("label", help="print the launchd/systemd label for a module")
    lb.add_argument("module")

    sub.add_parser("list", help="list modules")

    for name in ("install", "uninstall"):
        i = sub.add_parser(name, help=f"{name} modules (default: every enabled module)")
        i.add_argument("modules", nargs="*")
        i.add_argument("--dry-run", action="store_true", help="say what would change; change nothing")

    d = sub.add_parser("doctor", help="check this machine; exit 0 ok, 2 warn, 1 fail")
    d.add_argument("--json", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "config":
            return cmd_config(args)
        if args.cmd == "render":
            return cmd_render(args)
        if args.cmd == "label":
            return cmd_label(args)
        if args.cmd == "list":
            return cmd_list(args)
        if args.cmd == "install":
            return cmd_install(args)
        if args.cmd == "uninstall":
            if not args.modules:
                return _die("uninstall needs module names")
            return cmd_install(args, "uninstall")
        if args.cmd == "doctor":
            return D.main(C.current_platform(), args.json)
    except (C.ConfigError, M.ModuleError, R.RenderError, ValueError, OSError) as e:
        return _die(str(e))
    return 2
