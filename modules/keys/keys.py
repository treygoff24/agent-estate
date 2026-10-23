#!/usr/bin/env python3
"""Fail-closed key delivery; never interpret key files as shell code."""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lib'))
from estate.config import load
from estate.modules import discover


class KeyErrorSafe(Exception):
    pass


def settings():
    cfg = load(known_modules=discover())
    opts = cfg['modules']['keys']
    names = cfg['keys']['names']
    tools = opts['tools']
    if not isinstance(tools, dict) or any(
        not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', tool)
        or tool in {'estate-keys', 'python3'} or not isinstance(wants, list)
        or any(n not in names for n in wants) for tool, wants in tools.items()
    ):
        raise KeyErrorSafe('tools must map binary names to lists of managed key names')
    if not isinstance(opts['optional'], list) or any(n not in names for n in opts['optional']):
        raise KeyErrorSafe('optional must list managed key names')
    return cfg, opts, Path(opts['shim_dir']).expanduser()


def read_keys(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        raise KeyErrorSafe('key file ' + str(path) + ' does not exist; create it with mode 0600') from None
    except OSError as e:
        raise KeyErrorSafe('cannot open key file ' + str(path) + ': ' + e.strerror) from None
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
            raise KeyErrorSafe('key file must be owned by this user and mode 0600')
        values = {}
        for line in stream:
            line = line.rstrip('\n')
            if not line or line.startswith('#'):
                continue
            name, sep, value = line.partition('=')
            if not sep or not re.fullmatch(r'[A-Z_][A-Z0-9_]*', name) or name in values or '\x00' in value:
                raise KeyErrorSafe('invalid key file format (expected unique NAME=value lines)')
            values[name] = value
        return values


def atomic(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def generated(cfg, opts):
    script = str(Path(__file__).resolve())
    result = {}
    for tool in opts['tools']:
        result[tool] = '#!/bin/sh\nexec python3 ' + shlex.quote(script) + ' exec ' + shlex.quote(tool) + ' "$@"\n'
    result['estate-keys'] = '#!/bin/sh\nexec python3 ' + shlex.quote(script) + ' "$@"\n'
    # Bind shims to the installation config, not the caller's ambient config.
    for tool in result:
        result[tool] = result[tool].replace('exec python3 ', 'export ESTATE_CONFIG=' + shlex.quote(cfg['_path']) + '\nexec python3 ')
    return result


def execute(cfg, opts, directory, tool, args):
    if tool not in opts['tools']:
        raise KeyErrorSafe('tool is not configured')
    env = dict(os.environ)
    for name in cfg['keys']['names']:
        env.pop(name, None)
    values = read_keys(cfg['keys']['file'])
    for name in opts['tools'][tool]:
        if not values.get(name) and name not in opts['optional']:
            raise KeyErrorSafe('required key missing: ' + name)
        if values.get(name):
            env[name] = values[name]
    entries = os.get_exec_path()
    indices = [i for i, p in enumerate(entries) if Path(p).resolve() == directory.resolve()]
    if not indices:
        raise KeyErrorSafe('shim directory is absent from PATH')
    search = [p for p in entries[indices[0] + 1:] if Path(p).resolve() != directory.resolve()]
    binary = shutil.which(tool, path=os.pathsep.join(search))
    if not binary or Path(binary).resolve() == (directory / tool).resolve():
        raise KeyErrorSafe('real binary not found after shim directory')
    os.execve(binary, [binary, *args], env)


# Receiver loads its own config: differing home paths between machines are normal.
RECEIVER = '''import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'modules'/'keys'))
from keys import receive
receive()
'''


def receive():
    os.umask(0o077)
    cfg, _, _ = settings()
    raw = sys.stdin.buffer.read(1048577)
    if len(raw) > 1048576:
        raise KeyErrorSafe('payload too large')
    values = json.loads(raw)
    if not isinstance(values, dict) or any(n not in cfg['keys']['names'] or not isinstance(v, str) or any(c in v for c in '\n\r\x00') for n, v in values.items()):
        raise KeyErrorSafe('invalid key payload')
    dest = Path(cfg['keys']['file'])
    if dest.is_symlink():
        raise KeyErrorSafe('refusing symlink destination')
    atomic(dest, ''.join(n + '=' + v + '\n' for n, v in sorted(values.items())), 0o600)


def main():
    cfg, opts, directory = settings()
    command, *args = sys.argv[1:]
    expected = generated(cfg, opts)
    if command == 'exec':
        execute(cfg, opts, directory, args[0], args[1:])
    elif command == 'install':
        if '--dry-run' in args:
            print('would generate key shims in ' + str(directory))
            return 0
        directory.mkdir(parents=True, exist_ok=True)
        manifest = directory / '.estate-keys.json'
        old = json.loads(manifest.read_text()) if manifest.exists() else []
        for name in old:
            if name not in expected and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', name):
                (directory / name).unlink(missing_ok=True)
        for name, body in expected.items():
            target = directory / name
            if target.is_symlink():
                raise KeyErrorSafe('refusing symlink shim')
            if not target.exists() or target.read_text() != body or stat.S_IMODE(target.stat().st_mode) != 0o755:
                atomic(target, body, 0o755)
        atomic(manifest, json.dumps(sorted(expected)), 0o600)
        print('installed key shims')
    elif command == 'check':
        values = read_keys(cfg['keys']['file'])
        missing = [n for n in cfg['keys']['names'] if not values.get(n)]
        if any(n not in opts['optional'] for n in missing):
            raise KeyErrorSafe('required managed keys missing')
        for name, body in expected.items():
            p = directory / name
            if p.is_symlink() or not p.is_file() or p.read_text() != body or stat.S_IMODE(p.stat().st_mode) != 0o755:
                raise KeyErrorSafe('shims are stale; run estate install keys')
        paths = [Path(p).resolve() for p in os.get_exec_path()]
        bindir = Path(cfg['paths']['bin']).resolve()
        warning = directory.resolve() not in paths or (bindir in paths and paths.index(directory.resolve()) >= paths.index(bindir))
        print(('warn: ' if warning or missing else 'ok: ') + ('add: export PATH=' + shlex.quote(str(directory)) + ':"$PATH"' if warning else 'key file and shims current' + ('; optional keys missing' if missing else '')))
        print('done when: required keys exist at mode 0600 and current shims precede the tool bin directory on PATH')
        return 2 if warning or missing else 0
    elif command == 'push' and len(args) == 1:
        machine = next((m for m in cfg['machines'] if m['name'] == args[0]), None)
        if not machine or machine['ssh'].startswith('-'):
            raise KeyErrorSafe('unknown or invalid SSH machine')
        values = read_keys(cfg['keys']['file'])
        payload = {n: values[n] for n in cfg['keys']['names'] if n in values}
        # The checkout location is supplied as a module setting, relative to remote HOME.
        remote = 'python3 -c ' + shlex.quote(RECEIVER) + ' ' + shlex.quote(opts['remote_root'])
        result = subprocess.run(['ssh', '--', machine['ssh'], remote], input=json.dumps(payload).encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode:
            raise KeyErrorSafe('SSH key push failed (remote output suppressed)')
        print('keys pushed')
    else:
        raise KeyErrorSafe('usage: estate-keys push MACHINE')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyErrorSafe as e:
        # These messages name the failed rule and never carry a key value.
        print('fail: ' + str(e))
        print('done when: key file is owned by this user at mode 0600 and shims match estate.toml')
        sys.exit(1)
    except (OSError, ValueError, KeyError, IndexError):
        print('fail: keys operation failed; verify config, required names, file ownership/mode 0600 and installed shims')
        print('done when: key file is owned by this user at mode 0600 and shims match estate.toml')
        sys.exit(1)
