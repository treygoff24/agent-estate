"""config-sync: install an agent-env repo's manifest into $HOME, safely.

The agent-env repo is a git checkout holding `manifest.tsv` and the files it
names. Each manifest row is `kind  source  dest  [platform]`, tab separated:

  file         copy source (a file in the repo) to dest (a path under $HOME)
  tree         copy a directory; files later removed from the source are removed
               from dest, but only files this engine installed and nobody edited
  merge-json   merge source's keys into dest, a JSON file a harness also writes
  merge-toml   the same for a simple TOML file (see config_merge.py for limits)
  link         dest becomes a symlink to the source inside the repo checkout

platform is `mac`, `linux`, `all` (default) or a comma list. Lines starting
with `#` and blank lines are ignored. source is relative to the repo root; dest
is relative to $HOME (a leading `~/` is allowed).

Two promises:
  * A file is only replaced while it still holds the bytes this engine last
    wrote there. Anything else is a local edit: kept, reported, and rescued
    with `--harvest <dest>`. A file the engine never wrote is treated the same.
  * Nothing outside the manifest is touched; state lives under
    $ESTATE_STATE/config-sync/.

Standard library only.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import config_merge as M

PROG = "estate-config-sync"
KINDS = ("file", "tree", "merge-json", "merge-toml", "link")
PLATFORMS = ("mac", "linux")
SKIP_NAMES = {".DS_Store", ".git"}
CHANGES = {"install", "update", "remove", "merge", "link"}
DONE_WHEN = ("every file in the agent-env manifest is installed under your home, nothing "
             "local is waiting to be harvested, and the last apply succeeded")


class SyncError(Exception):
    pass


# ---------------------------------------------------------------- manifest


@dataclass(frozen=True)
class Row:
    kind: str
    src: str
    dest: str
    platforms: tuple[str, ...]
    line: int


def _safe_rel(path: str, what: str, line: int, allow_tilde: bool = False) -> str:
    p = path
    if allow_tilde and p.startswith("~/"):
        p = p[2:]
    parts = p.split("/")
    if not p or p.startswith("/") or any(x in ("", ".", "..") for x in parts):
        raise SyncError(f"manifest line {line}: unsafe {what} {path!r} (relative, no '..')")
    return p


def parse_manifest(text: str) -> list[Row]:
    rows = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = [f.strip() for f in (raw.split("\t") if "\t" in raw else raw.split())]
        fields = [f for f in fields if f]
        if len(fields) < 3:
            raise SyncError(f"manifest line {n}: expected `kind  source  dest  [platform]`, "
                            f"got {raw!r}")
        kind, src, dest = fields[:3]
        plat = fields[3] if len(fields) > 3 else "all"
        if kind not in KINDS:
            raise SyncError(f"manifest line {n}: unknown kind {kind!r} (one of {', '.join(KINDS)})")
        names = {"mac" if p == "darwin" else p for p in plat.split(",")}
        if "all" in names:
            names = set(PLATFORMS)
        if not names or not names <= set(PLATFORMS):
            raise SyncError(f"manifest line {n}: platform {plat!r} must be mac, linux, all "
                            f"or a comma list")
        rows.append(Row(kind, _safe_rel(src, "source", n), _safe_rel(dest, "dest", n, True),
                        tuple(sorted(names)), n))
    return rows


def _overlaps(a: str, b: str) -> bool:
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def active_rows(rows: list[Row], platform: str) -> list[Row]:
    out = [r for r in rows if platform in r.platforms]
    for i, a in enumerate(out):
        for b in out[i + 1:]:
            if _overlaps(a.dest, b.dest):
                raise SyncError(f"manifest lines {a.line} and {b.line}: destinations "
                                f"{a.dest!r} and {b.dest!r} overlap on {platform}")
    return out


# ---------------------------------------------------------------- helpers


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    return sha(path.read_bytes())


def write_atomic(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".cs-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def want_mode(src: Path) -> int:
    return 0o755 if src.stat().st_mode & 0o111 else 0o644


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_platform() -> str:
    forced = os.environ.get("ESTATE_PLATFORM")
    if forced:
        return forced
    return "mac" if sys.platform == "darwin" else "linux"


@dataclass
class Result:
    action: str  # install update remove merge link unchanged local-edit error warn harvest
    dest: str
    detail: str = ""


@dataclass
class Engine:
    repo: Path
    home: Path
    state_dir: Path
    platform: str
    dry: bool = False
    results: list[Result] = field(default_factory=list)

    # ---- state ----
    @property
    def cs_dir(self) -> Path:
        return self.state_dir / "config-sync"

    @property
    def state_file(self) -> Path:
        return self.cs_dir / "state.json"

    def load_state(self) -> dict:
        try:
            data = json.loads(self.state_file.read_text())
        except FileNotFoundError:
            data = {}
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncError(f"{self.state_file} is unreadable ({exc}); delete it to start "
                            f"over (files you edited will then count as local edits)") from None
        data.setdefault("entries", {})
        return data

    def save_state(self, state: dict) -> None:
        write_atomic(self.state_file, (json.dumps(state, indent=2, sort_keys=True) + "\n").encode(),
                     0o600)

    def note(self, action: str, dest: str, detail: str = "") -> None:
        self.results.append(Result(action, dest, detail))

    def contain(self, dest_rel: str, follow_leaf: bool = False) -> Path:
        """The path under home to act on, after proving it cannot lead outside home.

        Every parent component is resolved, so a directory that is a symlink to somewhere else
        is refused, not followed. The leaf itself is resolved only when `follow_leaf` is set (a
        merge row follows a link to the file the harness really owns); a symlink that resolves
        inside home may be followed, one that resolves outside is an error. The stored
        retirement paths come through here too, so a hand-edited state file cannot aim a delete
        elsewhere."""
        parts = dest_rel.split("/")
        if not dest_rel or dest_rel.startswith("/") or any(x in ("", ".", "..") for x in parts):
            raise SyncError(f"unsafe destination {dest_rel!r}; refusing to touch it")
        root = Path(os.path.realpath(self.home))
        path = self.home / dest_rel
        real = Path(os.path.realpath(path if follow_leaf else path.parent))
        if not follow_leaf:
            real = real / path.name
        if real != root and root not in real.parents:
            raise SyncError(f"{dest_rel} resolves to {real}, outside {root} (a directory on its "
                            f"path is a symlink out of your home); refusing to follow it")
        return path

    # ---- repo ----
    def manifest(self) -> list[Row]:
        mf = self.repo / "manifest.tsv"
        if not mf.is_file():
            raise SyncError(f"{mf} is missing")
        return active_rows(parse_manifest(mf.read_text()), self.platform)

    # ---- file installs ----
    def _file(self, state: dict, dest_rel: str, src: Path, src_rel: str, tree: str | None) -> None:
        entries = state["entries"]
        dest = self.contain(dest_rel)
        data = src.read_bytes()
        want, mode = sha(data), want_mode(src)
        rec = entries.get(dest_rel)
        entry = {"kind": "file", "sha256": want, "src": src_rel}
        if tree:
            entry["tree"] = tree
        if dest.is_symlink():
            return self.note("error", dest_rel, "destination is a symlink; not replacing it")
        if not dest.exists():
            self.note("install", dest_rel)
            if not self.dry:
                write_atomic(dest, data, mode)
            entries[dest_rel] = entry
            return
        if not dest.is_file():
            return self.note("error", dest_rel, "destination is not a regular file")
        have = file_sha(dest)
        if have == want:
            if (dest.stat().st_mode & 0o777) != mode and not self.dry:
                os.chmod(dest, mode)
            entries[dest_rel] = entry
            return self.note("unchanged", dest_rel)
        if rec and rec.get("kind") == "file" and rec.get("sha256") == have:
            self.note("update", dest_rel)
            if not self.dry:
                write_atomic(dest, data, mode)
            entries[dest_rel] = entry
            return
        why = ("changed since config-sync installed it" if rec
               else "already exists and config-sync did not install it")
        self.note("local-edit", dest_rel, f"{why}; kept")

    def _tree(self, state: dict, row: Row, desired: set[str]) -> None:
        root = self.repo / row.src
        if root.is_symlink() or not root.is_dir():
            return self.note("error", row.dest, f"tree source {row.src} is not a directory")
        dest_root = self.home / row.dest
        if dest_root.is_symlink() or (dest_root.exists() and not dest_root.is_dir()):
            return self.note("error", row.dest, "tree destination is not a plain directory")
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_NAMES)
            for name in sorted(filenames):
                if name in SKIP_NAMES:
                    continue
                f = Path(dirpath) / name
                rel = f.relative_to(root).as_posix()
                dest_rel = f"{row.dest}/{rel}"
                desired.add(dest_rel)
                if f.is_symlink():
                    self.note("warn", dest_rel, "symlink in a tree source is skipped")
                    continue
                self._file(state, dest_rel, f, f"{row.src}/{rel}", row.dest)

    def _merge(self, state: dict, row: Row) -> None:
        src = self.repo / row.src
        if not src.is_file():
            return self.note("error", row.dest, f"source {row.src} is not a file")
        real = Path(os.path.realpath(self.contain(row.dest, follow_leaf=True)))
        merge = M.merge_json if row.kind == "merge-json" else M.merge_toml
        try:
            cur = real.read_text() if real.exists() else None
            new = merge(cur, src.read_text())
        except M.MergeError as exc:
            return self.note("error", row.dest, f"merge refused, file untouched: {exc}")
        except (OSError, UnicodeDecodeError) as exc:
            return self.note("error", row.dest, str(exc))
        state["entries"][row.dest] = {"kind": row.kind, "sha256": sha(new.encode()), "src": row.src}
        if cur == new:
            return self.note("unchanged", row.dest)
        self.note("install" if cur is None else "merge", row.dest, "merged keys only" if cur else "")
        if not self.dry:
            mode = (real.stat().st_mode & 0o777) if cur is not None else 0o600
            write_atomic(real, new.encode(), mode)

    def _link(self, state: dict, row: Row) -> None:
        src = self.repo / row.src
        if not src.exists():
            return self.note("error", row.dest, f"link source {row.src} is missing")
        target = str(src.resolve())
        dest = self.contain(row.dest)
        rec = state["entries"].get(row.dest)
        entry = {"kind": "link", "target": target, "src": row.src}
        if dest.is_symlink():
            cur = os.readlink(dest)
            if cur == target:
                state["entries"][row.dest] = entry
                return self.note("unchanged", row.dest)
            if not (rec and rec.get("kind") == "link" and rec.get("target") == cur):
                return self.note("local-edit", row.dest, f"is a link to {cur}; kept")
            self.note("link", row.dest, "relinked")
            if not self.dry:
                dest.unlink()
        elif dest.exists():
            return self.note("local-edit", row.dest, "exists and is not a link; kept")
        else:
            self.note("link", row.dest)
        if not self.dry:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.symlink_to(target)
        state["entries"][row.dest] = entry

    # ---- retire ----
    def _retire(self, state: dict, desired: set[str]) -> None:
        entries = state["entries"]
        for dest_rel in sorted(set(entries) - desired):
            rec = entries[dest_rel]
            kind = rec.get("kind")
            try:
                dest = self.contain(dest_rel)
            except SyncError as exc:
                self.note("error", dest_rel, f"not retired: {exc}")
                continue  # the entry stays; fix or delete it by hand
            if kind in ("merge-json", "merge-toml"):
                self.note("warn", dest_rel, "no longer in the manifest; merged keys left in place")
            elif kind == "link":
                if dest.is_symlink() and os.readlink(dest) == rec.get("target"):
                    self.note("remove", dest_rel, "link")
                    if not self.dry:
                        dest.unlink()
            elif dest.is_symlink() or not dest.exists():
                pass
            elif dest.is_file() and file_sha(dest) == rec.get("sha256"):
                self.note("remove", dest_rel, "no longer in the repo")
                if not self.dry:
                    dest.unlink()
                    parent = dest.parent
                    while (parent != self.home and not parent.is_symlink() and parent.is_dir()
                           and not any(parent.iterdir())):
                        try:
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent
            else:
                self.note("local-edit", dest_rel, "no longer in the repo but edited locally; kept")
            entries.pop(dest_rel, None)  # a dry run never saves the state

    # ---- apply ----
    def apply(self) -> list[Result]:
        self.results = []
        state = self.load_state()
        desired: set[str] = set()
        try:
            rows = self.manifest()
        except SyncError as exc:
            self.note("error", "manifest.tsv", str(exc))
            self._finish(state, failed=True)
            return self.results
        for row in rows:
            try:
                if row.kind == "file":
                    desired.add(row.dest)
                    src = self.repo / row.src
                    if src.is_symlink() or not src.is_file():
                        self.note("error", row.dest, f"source {row.src} is not a file")
                    else:
                        self._file(state, row.dest, src, row.src, None)
                elif row.kind == "tree":
                    self._tree(state, row, desired)
                elif row.kind == "link":
                    desired.add(row.dest)
                    self._link(state, row)
                else:
                    desired.add(row.dest)
                    self._merge(state, row)
            except (OSError, SyncError) as exc:
                self.note("error", row.dest, str(exc))
        if not any(r.action == "error" for r in self.results):
            self._retire(state, desired)
        self._finish(state, any(r.action == "error" for r in self.results))
        return self.results

    def _finish(self, state: dict, failed: bool) -> None:
        if self.dry:
            return
        errs = [f"{r.dest}: {r.detail}" for r in self.results if r.action == "error"]
        state["last_apply"] = {"at": now(), "ok": not failed, "errors": errs[:5],
                               "local_edits": sum(r.action == "local-edit" for r in self.results)}
        self.save_state(state)

    # ---- harvest ----
    def norm_dest(self, arg: str) -> str:
        p = os.path.expanduser(arg) if arg.startswith("~") else arg
        if os.path.isabs(p):
            try:
                p = os.path.relpath(p, self.home)
            except ValueError:
                pass
            if p.startswith(".."):
                raise SyncError(f"{arg} is not under {self.home}")
        p = os.path.normpath(p)
        if p.startswith("..") or p == ".":
            raise SyncError(f"{arg} is not a path under your home")
        return p

    def harvest(self, arg: str) -> list[Result]:
        self.results = []
        rel = self.norm_dest(arg)
        rows = self.manifest()
        row = next((r for r in rows if r.dest == rel
                    or (r.kind == "tree" and rel.startswith(r.dest + "/"))), None)
        if row is None:
            raise SyncError(f"{rel} is not managed by any manifest row on {self.platform}; "
                            f"add a row to {self.repo}/manifest.tsv first")
        if row.kind.startswith("merge-"):
            raise SyncError(f"{rel} is a merged file: edit the fragment {row.src} in the repo "
                            f"instead (a harvest would copy the machine's own keys into it)")
        if row.kind == "link":
            raise SyncError(f"{rel} is a link into the repo; edits through it already land there")
        state = self.load_state()
        pairs: list[tuple[str, Path]] = []
        base = self.home / rel
        if row.kind == "file":
            pairs.append((rel, self.repo / row.src))
        elif base.is_dir() and not base.is_symlink():
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = sorted(d for d in dirnames if d not in SKIP_NAMES)
                for name in sorted(filenames):
                    if name not in SKIP_NAMES:
                        d_rel = (Path(dirpath) / name).relative_to(self.home).as_posix()
                        pairs.append((d_rel, self.repo / row.src / d_rel[len(row.dest) + 1:]))
        else:
            pairs.append((rel, self.repo / row.src / rel[len(row.dest) + 1:]))
        for d_rel, target in pairs:
            try:
                dest = self.contain(d_rel)
            except SyncError as exc:
                self.note("error", d_rel, str(exc))
                continue
            if not dest.exists() and not dest.is_symlink():
                self.note("error", d_rel, "does not exist")
                continue
            if dest.is_symlink() or not dest.is_file():
                self.note("warn", d_rel, "not a regular file; skipped")
                continue
            data = dest.read_bytes()
            if target.is_file() and not target.is_symlink() and target.read_bytes() == data:
                self.note("unchanged", d_rel, "already matches the repo")
            else:
                if target.is_symlink() or target.is_dir():
                    self.note("error", d_rel, f"{target} is not a regular file")
                    continue
                self.note("harvest", d_rel, f"-> {target.relative_to(self.repo).as_posix()}")
                if not self.dry:
                    write_atomic(target, data, 0o755 if dest.stat().st_mode & 0o111 else 0o644)
            if not self.dry:
                entry = {"kind": "file", "sha256": sha(data),
                         "src": target.relative_to(self.repo).as_posix()}
                if row.kind == "tree":
                    entry["tree"] = row.dest
                state["entries"][d_rel] = entry
        if not self.dry:
            self.save_state(state)
        return self.results


# ---------------------------------------------------------------- git / init


def git(repo: Path, *args: str, env: dict | None = None, check: bool = True, timeout: int = 120):
    e = dict(os.environ, GIT_TERMINAL_PROMPT="0", **(env or {}))
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=e,
                       stdin=subprocess.DEVNULL, timeout=timeout)
    if check and p.returncode:
        raise SyncError(f"git {' '.join(args)} failed: {(p.stderr or p.stdout).strip()[:300]}")
    return p


def is_checkout(repo: Path) -> bool:
    if not repo.is_dir() or not ((repo / ".git").exists()):
        return False
    return git(repo, "rev-parse", "--is-inside-work-tree", check=False).returncode == 0


def settings_file(state_dir: Path) -> Path:
    return state_dir / "config-sync" / "settings.json"


HOOK_DEFAULT = "~/.local/bin/footgun-hook"


def seed(repo: Path, starter: Path, doctrine: Path, fragments: Path | None = None,
         hook_bin: str = "") -> None:
    """Copy the starter (payload/ becomes home/), the doctrine pack and the guardrails hook
    fragments into a new checkout. `fragments` is modules/guardrails/settings: its Claude
    fragment is merged into home/.claude/settings.json (one row can then own that file) and its
    Codex fragment becomes home/.codex/hooks.json. `hook_bin` is the directory holding
    footgun-hook when it is not ~/.local/bin."""
    if not (starter / "manifest.tsv").is_file():
        raise SyncError(f"starter {starter} has no manifest.tsv")
    # The starter keeps its files under payload/ (a directory literally named home/ would trip
    # the repo's absolute-home-path scan); in the new repo they live under home/.
    for item in starter.iterdir():
        if item.name == "payload":
            shutil.copytree(item, repo / "home", dirs_exist_ok=True)
        elif item.is_dir():
            shutil.copytree(item, repo / item.name, dirs_exist_ok=True)
        else:
            shutil.copyfile(item, repo / item.name)
    seed_hooks(repo, fragments, hook_bin)
    target = repo / "home" / "doctrine"
    target.mkdir(parents=True, exist_ok=True)
    pack = ["agent-operating-contract.md", "shell-footguns.md", "shell-footguns-catalog.md",
            "shell-footguns-lore.md", "build-doctrine.md", "no-ceremony.md"]
    for name in pack:
        if (doctrine / name).is_file():
            shutil.copyfile(doctrine / name, target / name)
    reg = doctrine / "templates" / "house-register.md"
    if reg.is_file():
        text = reg.read_text().replace("<doctrine-dir>", "~/.config/agent-estate/doctrine")
        (target / "house-register.md").write_text(text)


def seed_hooks(repo: Path, fragments: Path | None, hook_bin: str) -> None:
    """Put the guardrails footgun-hook entries into the new checkout, copied from the module so
    the repo carries no second copy that could drift. A missing fragment is an error: the
    manifest's codex row would have no source."""
    if fragments is None:
        return
    wanted = {"claude.json": Path("home/.claude/settings.json"),
              "codex-hooks.json": Path("home/.codex/hooks.json")}
    for name, rel in wanted.items():
        src = fragments / name
        if not src.is_file():
            raise SyncError(f"guardrails hook fragment {src} is missing")
        text = src.read_text()
        if hook_bin and hook_bin.rstrip("/") != HOOK_DEFAULT.rsplit("/", 1)[0]:
            text = text.replace(HOOK_DEFAULT, hook_bin.rstrip("/") + "/footgun-hook")
        dest = repo / rel
        if dest.is_file():  # the starter's own settings.json: merge, keeping its keys
            try:
                text = M.merge_json(dest.read_text(), text)
            except M.MergeError as exc:
                raise SyncError(f"{dest}: {exc}") from exc
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)


def init(repo: Path, state_dir: Path, remote: str, starter: Path, doctrine: Path,
         name: str, email: str, dry: bool, say, fragments: Path | None = None,
         hook_bin: str = "") -> int:
    ident = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
             "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
    if is_checkout(repo):
        say(f"agent-env checkout exists: {repo}")
    elif repo.exists() and any(repo.iterdir()):
        say(f"error: {repo} exists but is not a git checkout; move it aside or set "
            f"modules.config-sync.repo")
        return 1
    elif dry:
        say(f"would create {repo} " + (f"by cloning {remote}" if remote else "from the starter"))
    else:
        repo.parent.mkdir(parents=True, exist_ok=True)
        if remote:
            p = subprocess.run(["git", "clone", "--quiet", remote, str(repo)], capture_output=True,
                               text=True, stdin=subprocess.DEVNULL, timeout=300,
                               env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
            if p.returncode:
                say(f"error: cannot clone {remote}: {p.stderr.strip()[:300]}\n"
                    f"  create that (empty, private) repository first, or clear "
                    f"modules.config-sync.remote to start from the starter without one")
                return 1
            say(f"cloned {remote} -> {repo}")
        else:
            repo.mkdir(parents=True, exist_ok=True)
            git(repo, "init", "--quiet", "-b", "main")
        if not (repo / "manifest.tsv").exists():
            seed(repo, starter, doctrine, fragments, hook_bin)
            git(repo, "add", "-A")
            git(repo, "commit", "--quiet", "-m", "Start from the agent-estate config-sync starter",
                env=ident)
            if remote:
                publish = f"git -C {repo} push -u origin HEAD:main"
            else:
                publish = f"git -C {repo} remote add origin <url> && git -C {repo} push -u origin HEAD:main"
            say(f"created {repo} from the starter; review it, then publish it ({publish})")
    if not dry:
        write_atomic(settings_file(state_dir), (json.dumps({"repo": str(repo)}) + "\n").encode(),
                     0o600)
    return 0


# ---------------------------------------------------------------- reports


def render(results: list[Result], dry: bool, verbose: bool, out, err) -> None:
    for r in results:
        if r.action == "unchanged" and not verbose:
            continue
        if r.action == "local-edit":
            err(f"local-edit  {r.dest}  {r.detail}\n    keep yours in the repo: "
                f"{PROG} --harvest {r.dest}   (or delete it to take the repo's)")
        elif r.action == "error":
            err(f"error       {r.dest}  {r.detail}")
        elif r.action == "warn":
            err(f"warn        {r.dest}  {r.detail}")
        else:
            word = ("would " if dry and r.action in CHANGES else "") + r.action
            out(f"{word:<11} {r.dest}  {r.detail}".rstrip())


def summary(results: list[Result], dry: bool) -> str:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.action] = counts.get(r.action, 0) + 1
    shown = [f"{counts[a]} {'would ' if dry and a in CHANGES else ''}{a}"
             for a in ("install", "update", "merge", "link", "remove", "harvest", "local-edit",
                       "error") if counts.get(a)]
    shown.append(f"{counts.get('unchanged', 0)} unchanged")
    return "config-sync: " + ", ".join(shown) + (" (dry run, nothing changed)" if dry else "")


# ---------------------------------------------------------------- check


def check(eng: Engine) -> tuple[int, list[str]]:
    """(exit code, [status line, extra lines]) for the doctor check."""
    repo = eng.repo
    fix = "run: estate install config-sync"
    if not is_checkout(repo):
        return 1, [f"fail: agent-env checkout missing at {repo} ({fix})"]
    if not (repo / "manifest.tsv").is_file():
        return 1, [f"fail: {repo}/manifest.tsv is missing"]
    try:
        state = eng.load_state()
        eng.manifest()
    except SyncError as exc:
        return 1, [f"fail: {exc}"]
    last = state.get("last_apply")
    if not last:
        return 1, [f"fail: config has never been applied on this machine ({fix})"]
    if not last.get("ok"):
        first = (last.get("errors") or ["unknown error"])[0]
        return 1, [f"fail: the last apply failed ({last.get('at')}): {first}"]
    eng.dry = True
    results = eng.apply()
    errors = [r for r in results if r.action == "error"]
    if errors:
        return 1, [f"fail: {errors[0].dest}: {errors[0].detail}"]
    edits = [r.dest for r in results if r.action == "local-edit"]
    pending = [r for r in results if r.action in CHANGES]
    dirty = git(repo, "status", "--porcelain", check=False).stdout.strip()
    warns = []
    if edits:
        warns.append(f"{len(edits)} local edit(s) not in the repo ({', '.join(edits[:3])}"
                     f"{', ...' if len(edits) > 3 else ''}): {PROG} --harvest <path>, "
                     f"commit, push")
    if pending:
        warns.append(f"{len(pending)} change(s) waiting to apply ({PROG} apply)")
    if dirty:
        warns.append(f"{repo} has uncommitted changes (commit and push them)")
    if warns:
        return 2, ["warn: " + "; ".join(warns)]
    files = sum(r.action == "unchanged" for r in results)
    return 0, [f"ok: {files} managed file(s) match {repo}"]


# ---------------------------------------------------------------- cli


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", help="the agent-env checkout (default: remembered by install, "
                                       "else ~/Code/agent-env)")
    common.add_argument("--home", help="install into this home instead of $HOME")
    common.add_argument("--state", help="state directory (default $ESTATE_STATE)")
    common.add_argument("--platform", choices=PLATFORMS)
    common.add_argument("--dry-run", action="store_true", help="show every change; make none")
    p = argparse.ArgumentParser(prog=PROG, description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("apply", parents=[common], help="install the manifest into $HOME")
    a.add_argument("--pull", action="store_true", help="git pull --ff-only the checkout first")
    a.add_argument("-v", "--verbose", action="store_true", help="also list unchanged files")
    h = sub.add_parser("harvest", parents=[common],
                       help="copy a locally edited file (or a tree row's directory) into the repo")
    h.add_argument("dest")
    sub.add_parser("check", parents=[common], help="doctor check: ok/warn/fail")
    i = sub.add_parser("init", parents=[common], help="create or clone the agent-env checkout")
    i.add_argument("--remote", default="")
    i.add_argument("--starter")
    i.add_argument("--doctrine")
    i.add_argument("--guardrails-settings",
                   help="directory holding the guardrails hook fragments (default: "
                        "modules/guardrails/settings in this repo)")
    i.add_argument("--hook-bin", default="",
                   help="directory footgun-hook is installed in (default ~/.local/bin)")
    i.add_argument("--name", default="agent-estate")
    i.add_argument("--email", default="agent-estate@localhost")
    return p


def resolve(args) -> tuple[Path, Path, Path, str]:
    home = Path(args.home or os.environ.get("HOME") or Path.home()).expanduser()
    state_dir = Path(args.state or os.environ.get("ESTATE_STATE")
                     or home / ".local/state/agent-estate").expanduser()
    repo = args.repo or os.environ.get("ESTATE_CONFIG_SYNC_REPO")
    if not repo:
        try:
            repo = json.loads(settings_file(state_dir).read_text())["repo"]
        except (OSError, ValueError, KeyError):
            repo = str(home / "Code" / "agent-env")
    return Path(repo).expanduser(), home, state_dir, args.platform or default_platform()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--harvest" in argv:  # `estate-config-sync --harvest <dest>` is the documented spelling
        argv[argv.index("--harvest")] = "harvest"
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 2
    out = lambda s: print(s, flush=True)  # noqa: E731
    err = lambda s: print(s, file=sys.stderr, flush=True)  # noqa: E731
    repo, home, state_dir, platform = resolve(args)
    here = Path(__file__).resolve().parent
    if args.cmd == "init":
        return init(repo, state_dir, args.remote, Path(args.starter or here / "starter"),
                    Path(args.doctrine or here.parent.parent / "doctrine"), args.name, args.email,
                    args.dry_run, err,
                    Path(args.guardrails_settings or here.parent / "guardrails" / "settings"),
                    args.hook_bin)

    eng = Engine(repo, home, state_dir, platform, dry=args.dry_run)
    if args.cmd == "check":
        eng.dry = True
        code, lines = check(eng)
        for line in lines:
            out(line)
        out(f"done when: {DONE_WHEN}")
        return code
    if not is_checkout(repo) or not (repo / "manifest.tsv").is_file():
        if args.cmd == "apply" and args.dry_run and not repo.exists():
            out(f"{PROG}: {repo} does not exist yet; install would create it")
            return 0
        err(f"error: no agent-env checkout with a manifest.tsv at {repo} (estate install "
            f"config-sync creates one)")
        return 1
    if not eng.dry:
        eng.cs_dir.mkdir(parents=True, exist_ok=True)
    with (open(eng.cs_dir / "lock", "w") if not eng.dry else open(os.devnull)) as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            err("error: another config-sync run holds the lock")
            return 1
        try:
            if args.cmd == "harvest":
                results = eng.harvest(args.dest)
                render(results, eng.dry, True, out, err)
                out(summary(results, eng.dry))
                if any(r.action == "harvest" for r in results) and not eng.dry:
                    out(f"now review and commit: git -C {repo} status; git -C {repo} add -A; "
                        f"git -C {repo} commit; git -C {repo} push")
                return 1 if any(r.action == "error" for r in results) else 0
            if args.pull and (repo / ".git").exists() \
                    and "origin" in git(repo, "remote", check=False).stdout.split() and not eng.dry:
                p = git(repo, "pull", "--ff-only", "--quiet", check=False)
                if p.returncode:
                    err(f"warn: git pull --ff-only failed ({(p.stderr or p.stdout).strip()[:200]}); "
                        f"applying what is checked out")
            results = eng.apply()
        except SyncError as exc:
            err(f"error: {exc}")
            return 1
    render(results, eng.dry, args.verbose, out, err)
    out(summary(results, eng.dry))
    return 1 if any(r.action == "error" for r in results) else 0
