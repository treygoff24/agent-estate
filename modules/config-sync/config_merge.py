"""Merge a managed fragment into a file that a harness also writes.

Two merges, both pure functions of (existing text, fragment text) -> new text:

merge_json   Claude Code's ~/.claude/settings.json and friends.
merge_toml   Codex's ~/.codex/config.toml.

Both keep every key the fragment does not mention. Both refuse (MergeError)
rather than guess: a target or fragment that does not parse, or whose shape the
merge cannot handle, is never written.

JSON rules
  - objects merge key by key, the target's order first, new keys last;
  - under "hooks", each event's list of hook groups merges per command: a
    fragment hook whose command the target already carries (any spelling of
    $HOME / ~, with or without a leading "bash ") converges in place, a missing
    one is appended in its own group, target-only groups stay;
  - every other list and every scalar takes the fragment's value. A list the
    fragment names is therefore owned by the fragment: put every item you want
    in it.

TOML rules (the standard library only reads TOML, so this is a line-level merge
verified by parsing the result)
  - the fragment holds only single-line `key = value` pairs, at the root or
    under `[table]` headers; dotted keys, `[[array tables]]`, multi-line values
    and a table declared twice are refused;
  - a fragment key present in the target replaces that line in place (comments
    and neighbours stay); a key absent from its table is appended to that table;
    an absent table is appended at the end of the file;
  - a target value that spans several lines cannot be replaced and is refused;
  - the result must parse and must carry every fragment value, or nothing is
    written.
Neither merge can delete a key: removing one from the fragment leaves the
target's copy in place.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tomllib


class MergeError(Exception):
    pass


# ---------------------------------------------------------------- JSON


def _hook_identity(hook: dict) -> str:
    command = str(hook.get("command", ""))
    args = hook.get("args")
    if isinstance(args, list) and args:
        command = " ".join([command, *(str(a) for a in args)])
    text = command.strip()
    for prefix in ("bash ", "sh "):
        if text.startswith(prefix):
            rest = text[len(prefix):].lstrip()
            if rest and not rest.startswith("-"):
                text = rest
            break
    text = text.replace('"', "").replace("'", "")
    text = text.replace("${HOME}", "~").replace("$HOME", "~")
    home = os.path.expanduser("~")
    if home and home != "/":
        text = text.replace(home + "/", "~/")
    return text


def _group_commands(group: object) -> list[tuple[int, str]]:
    if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
        return []
    return [(i, _hook_identity(h)) for i, h in enumerate(group["hooks"])
            if isinstance(h, dict) and "command" in h]


def _merge_hook_event(target_groups: list, canon_groups: list, event: str) -> list:
    merged = list(target_groups)
    for cgroup in canon_groups:
        if not isinstance(cgroup, dict):
            raise MergeError(f"fragment hooks.{event} has a group that is not an object")
        missing = []
        for chook in cgroup.get("hooks", []):
            if not isinstance(chook, dict) or "command" not in chook:
                raise MergeError(f"fragment hooks.{event} has a hook without a command")
            want = _hook_identity(chook)
            for tgroup in merged:
                hit = next((i for i, have in _group_commands(tgroup) if have == want), None)
                if hit is not None:
                    tgroup["hooks"][hit] = dict(chook)
                    break
            else:
                missing.append(dict(chook))
        if missing:
            new_group = {k: v for k, v in cgroup.items() if k != "hooks"}
            new_group["hooks"] = missing
            merged.append(new_group)
    return merged


def _merge_hooks(target: object, canon: object) -> dict:
    if not isinstance(target, dict):
        raise MergeError("target 'hooks' is not an object")
    if not isinstance(canon, dict):
        raise MergeError("fragment 'hooks' is not an object")
    out = dict(target)
    for event, cgroups in canon.items():
        if not isinstance(cgroups, list):
            raise MergeError(f"fragment hooks.{event} is not a list")
        tgroups = out.get(event, [])
        if not isinstance(tgroups, list):
            raise MergeError(f"target hooks.{event} is not a list")
        out[event] = _merge_hook_event(list(tgroups), cgroups, event)
    return out


def _merge_obj(target: dict, canon: dict, path: str = "") -> dict:
    out = dict(target)
    for key, cval in canon.items():
        here = f"{path}.{key}" if path else key
        tval = out.get(key)
        if here == "hooks":
            out[key] = _merge_hooks(tval if tval is not None else {}, cval)
        elif isinstance(cval, dict) and isinstance(tval, dict):
            out[key] = _merge_obj(tval, cval, here)
        else:
            out[key] = cval
    return out


def _load_obj(text: str, role: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MergeError(f"{role} is not valid JSON ({exc})") from None
    if not isinstance(data, dict):
        raise MergeError(f"{role} is not a JSON object")
    return data


def merge_json(target_text: str | None, fragment_text: str) -> str:
    """Return the merged JSON text. An absent target (None) becomes the fragment.
    A converged file comes back byte-identical (no reformatting)."""
    canon = _load_obj(fragment_text, "fragment")
    if target_text is None:
        return json.dumps(canon, indent=2) + "\n"
    target = _load_obj(target_text, "target")
    merged = _merge_obj(copy.deepcopy(target), canon)
    if merged == target:
        return target_text
    return json.dumps(merged, indent=2) + "\n"


# ---------------------------------------------------------------- TOML

_HEADER = re.compile(r"^\s*\[(?P<array>\[)?(?P<name>[^\]]+)\]\]?\s*(#.*)?$")
_KEY = re.compile(r"""^\s*(?P<key>"(?:[^"\\]|\\.)*"|'[^']*'|[A-Za-z0-9_-]+)\s*=""")

Table = tuple[str, ...] | None


def _header_identity(name: str) -> tuple[str, ...]:
    try:
        doc = tomllib.loads(f"[{name}]\n")
    except tomllib.TOMLDecodeError as exc:
        raise MergeError(f"bad table header [{name}]: {exc}") from None
    path: list[str] = []
    node = doc
    while isinstance(node, dict) and len(node) == 1:
        (k, node), = node.items()
        path.append(k)
    return tuple(path)


def _key_identity(raw: str) -> str:
    try:
        doc = tomllib.loads(f"{raw} = 0\n")
    except tomllib.TOMLDecodeError as exc:
        raise MergeError(f"bad key {raw!r}: {exc}") from None
    if len(doc) != 1:
        raise MergeError(f"bad key {raw!r}")
    (k, v), = doc.items()
    if isinstance(v, dict):
        raise MergeError(f"dotted key {raw!r} is not supported in a fragment; use a [table] header")
    return k


def _sections(text: str) -> list[tuple[Table, bool, list[str]]]:
    out: list[tuple[Table, bool, list[str]]] = [(None, False, [])]
    for line in text.split("\n"):
        m = _HEADER.match(line)
        if m and not line.lstrip().startswith("#"):
            out.append((_header_identity(m.group("name")), bool(m.group("array")), [line]))
        else:
            out[-1][2].append(line)
    return out


def _parses_alone(line: str) -> bool:
    try:
        tomllib.loads(line + "\n")
    except tomllib.TOMLDecodeError:
        return False
    return True


def _fragment_pairs(text: str) -> list[tuple[Table, list[tuple[str, str]]]]:
    out: list[tuple[Table, list[tuple[str, str]]]] = []
    seen: set[Table] = set()
    for table, is_array, lines in _sections(text):
        if is_array:
            raise MergeError("array tables ([[...]]) are not supported in a fragment")
        if table in seen:
            raise MergeError(f"table {'.'.join(table or ())} is declared twice in the fragment")
        seen.add(table)
        pairs: list[tuple[str, str]] = []
        for line in lines:
            if not line.strip() or line.strip().startswith("#") or _HEADER.match(line):
                continue
            m = _KEY.match(line)
            if not m:
                raise MergeError(f"fragment line is not a single-line key = value: {line!r}")
            if not _parses_alone(line):
                raise MergeError(f"fragment value must fit on one line: {line!r}")
            pairs.append((_key_identity(m.group("key")), line))
        if pairs:
            out.append((table, pairs))
    return out


def _quote_key(k: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", k):
        return k
    return '"' + k.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _dig(doc: dict, table: Table) -> dict:
    node = doc
    for part in table or ():
        node = node[part]
    return node


def merge_toml(target_text: str | None, fragment_text: str) -> str:
    try:
        tomllib.loads(fragment_text)
    except tomllib.TOMLDecodeError as exc:
        raise MergeError(f"fragment is not valid TOML ({exc})") from None
    pairs_by_table = _fragment_pairs(fragment_text)
    if target_text is None:
        return fragment_text if fragment_text.endswith("\n") else fragment_text + "\n"
    try:
        tomllib.loads(target_text)
    except tomllib.TOMLDecodeError as exc:
        raise MergeError(f"target is not valid TOML ({exc})") from None

    sections = _sections(target_text)
    for table, pairs in pairs_by_table:
        idx = next((i for i, (t, arr, _) in enumerate(sections) if t == table and not arr), None)
        if idx is None:
            header = "[" + ".".join(_quote_key(k) for k in table or ()) + "]"
            if sections[-1][2] and sections[-1][2][-1].strip():
                sections[-1][2].append("")
            sections.append((table, False, [header, *[line for _, line in pairs], ""]))
            continue
        lines = sections[idx][2]
        for key, new_line in pairs:
            hit = None
            for i, line in enumerate(lines):
                m = _KEY.match(line)
                if m and not line.lstrip().startswith("#") and _key_identity(m.group("key")) == key:
                    hit = i
                    break
            if hit is None:
                end = len(lines)
                while end > 0 and not lines[end - 1].strip():
                    end -= 1
                lines.insert(end, new_line)
            else:
                if not _parses_alone(lines[hit]):
                    raise MergeError(f"target value for {key!r} spans several lines; set it by hand")
                lines[hit] = new_line
    merged = "\n".join(line for _, _, lines in sections for line in lines)
    if merged != target_text and not merged.endswith("\n"):
        merged += "\n"

    try:
        got = tomllib.loads(merged)
    except tomllib.TOMLDecodeError as exc:
        raise MergeError(f"merged result does not parse ({exc}); nothing written") from None
    want = tomllib.loads(fragment_text)
    for table, pairs in pairs_by_table:
        for key, _ in pairs:
            try:
                have = _dig(got, table)[key]
            except (KeyError, TypeError):
                raise MergeError(f"merged result lacks {key!r}; nothing written") from None
            if have != _dig(want, table)[key]:
                raise MergeError(f"merged result has {key!r} = {have!r}, wanted "
                                 f"{_dig(want, table)[key]!r}; nothing written")
    return merged
