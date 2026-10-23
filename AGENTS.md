# AGENTS.md

For any agent in this repo: one installing the estate for its person, or one changing the repo itself.

## If you are installing

Follow `INSTALL.md` from the top. The person's values go in one file, `~/.config/agent-estate/estate.toml` (copy `estate.example.toml`; `ESTATE_CONFIG` overrides the path). Ask the person for anything you cannot read off the machine; never invent an email, host or account. Run `bin/estate config check` after every edit and `bin/estate doctor` after every install. Done means `estate doctor` exits 0 on every machine.

Two rules hold throughout:

- Machines share state only through git. Do not `scp` or `rsync` config between them.
- The agents' login has no sudo. When a step needs root, show the person the exact command and wait; do not work around it.

## Layout

```
bin/estate             the CLI: config, render, label, list, install, uninstall, doctor
lib/estate/            Python 3.11+ stdlib helpers: config.py (schema), render.py,
                       modules.py (discovery, ordering, running scripts), doctor.py, cli.py
lib/estate.sh          shell helper sourced by module scripts
modules/<name>/        one directory per core module; contract in modules/README.md
estate.example.toml    the config a newcomer copies and fills in
scripts/gate.sh        the gate: shellcheck, tests, gitleaks, private-marker scan
scripts/scan-private.py
tests/                 unittest; every test uses a temporary HOME and config
addons/  guides/  doctrine/  skills/   content areas, each owned by its own work
```

## If you are changing the repo

- **Python is standard library only**, 3.11+ (`tomllib`). Shell is bash. No new languages, frameworks or third-party packages.
- **The config schema lives in `lib/estate/config.py` alone.** A new top-level key goes there, in `estate.example.toml` with a comment, and in a test. Module settings do not touch the schema: declare them under `[defaults]` in the module's `module.toml`.
- **A module follows `modules/README.md`.** Its check exits 0 ok, 1 fail, 2 warn and prints a status line plus `done when:`. Its install is idempotent, has `--dry-run`, and needs no sudo. Unit and plist names come from `${label}`, never a hard-coded prefix.
- **A new built module** goes in the `enabled` list of `estate.example.toml` and gets a row and a paragraph in `INSTALL.md`; `tests/test_install_guide.py` fails until it does. A stub stays out of `enabled` (commented) and is marked "coming soon: module not built yet".
- **Tests:** `python3 -m unittest discover -s tests -t .` from the repo root. Tests never touch the real home directory, real systemd or launchd: give them a temporary HOME and fake system commands on PATH. A new test is proven by breaking what it guards once and watching it fail.
- **Gate:** `scripts/gate.sh` before you hand work on. It must print `gate: PASS`.

## This repo is public

Nothing personal goes in a committed file: no real names (the LICENSE copyright line is the one exception), emails, hostnames, tailnet names, IP addresses, account names, company or client names, absolute paths into a home directory, or secrets. Use placeholders: `<you>`, `you@example.com`, `mac`, `vps`, `example.ts.net`, `~/Code`. Write "in practice" or "we learned", not who learned it.

`scripts/scan-private.py` (part of the gate) enforces this. It always flags absolute home paths, and it reads extra regexes, one per line, from `$ESTATE_PRIVATE_MARKERS`, else `.private-markers` in the repo root (git-ignored), else `~/.config/agent-estate/private-markers`. Keep your own names and hosts in that file; never commit it. A hit prints `file:line:pattern`; fix every one.

Never read or print credential files (`*.key`, `.env`, key files named in `[keys]`, SSH private keys) while working here.
