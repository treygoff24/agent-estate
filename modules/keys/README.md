# Keys: scrub, then inject

Keep provider credentials in one file per machine, never in git and never
sourced by an interactive shell. This module generates per-tool shims which
remove **every** managed name from the inherited environment, then load only
the names assigned to that tool. Tools must be invoked through the shims;
this is not a sandbox against programs deliberately reading your files.

## Configure

```toml
[keys]
file = "~/.config/agent-estate/credentials"
names = ["EXA_API_KEY", "OPENROUTER_API_KEY"]

[modules.keys]
shim_dir = "~/.local/bin/estate-shims"
optional = ["OPENROUTER_API_KEY"]
remote_root = "Code/agent-estate"

[modules.keys.tools]
exa-agent = ["EXA_API_KEY"]
```

Enable `keys` in `modules.enabled`. `optional` names may be absent or empty;
all other managed names must be present and nonempty. `tools` maps executable
basenames to managed names; even a tool with an empty list gets a scrubbed
environment. `shim_dir` is dedicated to generated shims. Do not place unrelated
files there. Changing tool mappings takes effect immediately; reinstall after
adding or removing tools. Removed generated tools are deleted on reinstall.

Create the key file privately with mode 0600 and your own ownership. Its format
is literal `NAME=value`, one per line. Blank lines and lines beginning with `#`
are ignored. No `export`, quoting, escaping, interpolation or shell evaluation
occurs. Quotes become part of the value; values can contain `=`. Duplicate names,
malformed names and NUL bytes are rejected. Symlink key files are refused.

Run `estate install keys` (or use `--dry-run` to preview). It creates shims but
never creates an empty credential file or changes shell startup files. Add this
line to the environment used to launch **each agent harness**, substituting your
configured shim directory if different:

```sh
export PATH="$HOME/.local/bin/estate-shims:$PATH"
```

Put it before the real tool directory (`paths.bin`). The real executable must
appear on PATH **after** the shim directory. Shims skip aliases of their own
directory and refuse recursion. Generated wrappers reference this checkout and
config, so keep the checkout in place and reinstall after moving it. Python 3.11+
must be available on PATH; do not configure `python3` itself as a shimmed tool.

## Push to another machine

On the destination first clone the repo, configure its own `estate.toml`, and
set its `[keys].file` to the local destination path. SSH must already work.
`remote_root` is the destination checkout path, relative to the remote login's
home directory (default `Code/agent-estate`). The remote uses its default config
path; custom `ESTATE_CONFIG` must be set in its SSH session environment.

```sh
estate-keys push vps
```

The command sends all managed names present in the local file as JSON on SSH
stdin, never as argv or a printed receipt. Remote stdout/stderr are suppressed
so an SSH failure reports only a generic failure. The receiver validates names
against its own managed list and atomically replaces the destination at mode
0600, with umask 077 and a synced temporary file. Its parent is created at 0700
if absent; existing parent directories must already be trusted. This replaces,
not merges, the remote file. Use the same managed-name list on both machines;
a remote subset rejects unknown names rather than silently dropping them.
No SSH or real credential store is modified by module installation.

## Done when

`estate doctor` reports that the key file is owned by you at exactly 0600, all
required managed names are nonempty, shims match the current installation and
the shim directory precedes the configured tool directory on PATH. Missing
optional keys or an incorrect PATH are warnings; unsafe permissions, missing
required keys or stale shims fail. Check reads no live tool API and does not
prove that a provider accepts a credential.
