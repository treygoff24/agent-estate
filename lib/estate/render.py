"""Fill ${dotted.key} placeholders in a template from the config.

Rules (also in modules/README.md):
  ${a.b.c}   value of a.b.c from estate.toml (paths already expanded)
  ${label}   label_prefix + "." + module name, e.g. com.example.estate.tmp-cleanup
  ${module}  module name;  ${home}  $HOME;  ${estate.root}  the repo checkout
  ${machine} this machine's name ("" if unknown)
  $${x}      a literal ${x} (for systemd's own ${VAR} expansion)
An unknown key, a non-scalar value, or any leftover "${" is an error:
nothing is written unless every placeholder rendered.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import config as C

PLACEHOLDER = re.compile(r"\$(\$?)\{([^}]*)\}")
KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class RenderError(Exception):
    pass


def label(cfg: dict, module: str) -> str:
    return f"{cfg['label_prefix']}.{module}"


def context(cfg: dict, module: str | None, platform: str | None = None) -> dict:
    from .modules import repo_root
    machine = C.this_machine(cfg, platform)
    extra = {
        "home": os.path.expanduser("~"),
        "estate": {"root": str(repo_root())},
        "machine": machine["name"] if machine else "",
    }
    if module:
        extra |= {"module": module, "label": label(cfg, module)}
    return {k: v for k, v in cfg.items() if not k.startswith("_")} | extra


def _scalar(key, value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    raise RenderError(f"${{{key}}}: is a {type(value).__name__}, not a single value")


def render_text(text: str, ctx: dict, where: str = "template") -> str:
    problems = []

    def sub(m):
        escaped, key = m.group(1), m.group(2)
        if escaped:
            return "${" + key + "}"
        if not KEY_RE.match(key):
            problems.append(f"${{{key}}}: not a valid key")
            return m.group(0)
        if key in ("label", "module") and key not in ctx:
            problems.append(f"${{{key}}}: needs a module (template under modules/<name>/, "
                            f"or pass --module)")
            return m.group(0)
        try:
            return _scalar(key, C.get(ctx, key))
        except KeyError:
            problems.append(f"${{{key}}}: no such key in the config")
        except RenderError as e:
            problems.append(str(e))
        return m.group(0)

    out = PLACEHOLDER.sub(sub, text)
    # Anything shaped like ${ that the pattern did not consume (e.g. unclosed).
    covered = set()
    for m in PLACEHOLDER.finditer(text):
        covered.update(range(m.start(), m.end()))
    for m in re.finditer(r"\$\{", text):
        if m.start() not in covered:
            line = text.count("\n", 0, m.start()) + 1
            problems.append(f"line {line}: unclosed or malformed ${{ placeholder")
    if problems:
        raise RenderError(f"{where}: " + "; ".join(problems))
    return out


def module_of(template: Path) -> str | None:
    """modules/<name>/templates/... -> <name>."""
    parts = template.resolve().parts
    for i in range(len(parts) - 2):
        if parts[i] == "modules" and parts[i + 2] == "templates":
            return parts[i + 1]
    return None


def render_file(cfg: dict, template: Path, module: str | None = None,
                platform: str | None = None) -> str:
    module = module or module_of(template)
    return render_text(template.read_text(), context(cfg, module, platform), str(template))


def write_atomic(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp-{os.getpid()}")
    tmp.write_text(text)
    os.replace(tmp, dest)
