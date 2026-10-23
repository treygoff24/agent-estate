# Shell footguns catalog

The long tail. Reached from `shell-footguns.md` when a named topic applies (rg, sed, perl,
Python, zsh, package test tools, browser and server tools, systemd or launchctl, Docker
Desktop, keychains, macOS services, Rust linking). Each entry is a rake someone stepped on;
the reason is in the entry. Narratives for some of them are in `shell-footguns-lore.md`.

Entries from the original set that only made sense inside private tooling were dropped; a few
were generalized (a named daemon became "a Node daemon", a named agent harness became "an
agent harness").

## Browser and web automation

- Browser-automating a React login: re-read field values immediately before submit. A Fast
  Refresh rebuild between fill and click remounts the form, clears both fields, and posts empty
  credentials with no visible error. Click-then-type drops keystrokes pre-hydration; wait after
  each click and verify.
- Admin-console `div[role=button]` elements can ignore plain `.click()`: dispatch the full
  pointerdown, mousedown, pointerup, mouseup, click sequence with real coordinates on the
  `[role=button]` ancestor. And cloud consoles can put fresh credentials in `aria-label` text, so
  snapshots pull secrets into the transcript: assume credential-creating flows leak into the
  log, tell the user, and treat rotation as the remedy.
- Image libraries do no glyph shaping and cannot preview font ligatures. Render candidates in
  a real browser with `font-feature-settings` forcing `calt`/`liga` on and off.
- A single-use token is consumed by the test that exercises it; re-opening the URL later shows
  the expired state, which reads as a regression. Spend a fresh token per verification pass,
  keep one unconsumed, and use an incognito context so cookies do not skip the gate.
- `screencapture` immediately after a config reload returns a stale frame. Capture in a
  separate later call, and re-capture before believing a measurement that contradicts what a
  change should have done.
- macOS screenshot filenames contain U+202F (narrow no-break space) before AM/PM. Reference
  them via glob or `find -name "Screenshot *"`, never by retyping the visible name.

## Shell and quoting

- In JS template literals or exec wrappers, never write shell `${...}`; use a plain command
  string or a quoted heredoc.
- Keep record fields intact: `while IFS=$'\t' read -r file start end; do ...; done < records.tsv`;
  parallel arrays for in-shell records.
- Name every compound-check failure: `test -f "$f" || { echo "missing file: $f" >&2; exit 1; }`.
- Parse path-bearing JSON with `jq`, not regex; `rg --no-filename -o PATTERN` when the match
  itself is a path.
- Split JSON arrays portably: `jq -c '.[]' file.json | while IFS= read -r item; do ...; done`.
- Default optional JSON arrays before iterating: `jq -r '.warnings // [] | .[]'`. Iterating an
  absent or `null` field aborts the whole jq run ("Cannot iterate over null"), which reads like
  malformed input.
- File matrices: `while IFS= read -r file; do ...; done < <(rg --files -g '*.md')`; avoid
  command substitution and unguarded globs.
- Pass only real paths to `awk`; print display labels separately with `printf '%s\n' "$label"`.
- `printf '%s\n' "$sep"`, never data as the format string (a leading hyphen is an option).
- Never expand `${!array[@]}` inside `[ ... ]`; capture `${#array[@]}` or iterate.
- `file -b "$p"` before piping a possible binary through text tools.
- `python3`, never bare `python`; guard optional tools with `command -v`.
- Find instruction files by walking parents from cwd to `/` only; never recurse into children.
- Copy YAML frontmatter with
  `awk 'NR==1&&$0=="---"{p=1} p{print} p&&NR>1&&$0=="---"{exit}' file.md`.
- Secret-safe zsh smoke: `zsh -df -c 'command -v tool'`; never source startup files under `-x`.
- Small unique `apply_patch` hunks; after dependency or lockfile mutations, reread the target
  before the next patch.

## sed, awk, perl, stat

- Never assume which `sed`/`stat`/`ls`/`awk` variant PATH resolves to. GNU `sed -i 's/old/new/'`
  fails on stock macOS, which needs `/usr/bin/sed -i ''`; BSD `stat -f '%Sm'` is rejected by GNU
  `stat`. Scripts that run on both choose explicitly or probe the flag syntax.
- Quote sed addresses and include the command: `sed -n "${range}p" file`. A bare range is an
  address, not a script, and is a hard GNU error ("missing command").
- macOS `awk` may be BSD: no `match(s, re, arr)` capture arrays. Use `grep -oE`/`sed` or an
  explicit `gawk`.
- Text normalization: `perl -CSD -pi` or another Unicode-aware tool; byte-mode Perl classes
  corrupt multi-byte punctuation. Apostrophes in inline regexes: use a heredoc.
- `perl -i` redirects output to the file only for `-p`/`-n` loops. An explicit `<>` slurp
  one-liner truncates the file to 0 bytes. For EOF or trailing-newline surgery use byte-safe
  Python (`p.write_bytes(p.read_bytes().rstrip(b"\n") + b"\n")`).

## zsh

- An unquoted word starting with `=` (for example `echo ===` as a separator) triggers `=cmd`
  PATH expansion and kills the compound command. Quote it.
- `status` and lowercase `path` are reserved; use `rc`/`exit_code` and `repo_path`. Assigning
  `path` destroys `PATH`.
- Quote globs or set `nullglob` when zero matches is legitimate; zsh `nomatch` aborts the
  command.
- `set -- $var` does not word-split; use `${=var}` or a real array. Do not rely on splitting in
  code an agent's zsh shell might run.

## rg (ripgrep)

- `rg -r` is **replace**, not recursive: `rg -rn PAT path` prints every match rewritten to the
  literal `n`, which is output that looks real and is fabricated.
- Leading-dash patterns need the terminator: `rg -- '--log'`.
- `rg -h` is **help** (suppress filenames with `-I`); `rg -oh` prints the help screen
  mid-pipeline.
- A nonexistent path in rg's arguments prints an error, then searches the remaining paths anyway
  and can exit 0: a failed-looking search that succeeded. Guard optional paths before passing
  them.
- A literal newline in an rg pattern needs `-U`, and the failure is version-dependent: a newer
  ripgrep exits 2 naming the fix, while an older one exits **1 with empty stdout and empty
  stderr**, indistinguishable from an ordinary no-match, so a verify row reads green while
  matching nothing.

## Python, JavaScript, Rust, package tools

- `pnpm run <script> -- <filter>` silently de-scopes: the `--` keeps the filter from reaching
  the runner, so the full suite runs and passes. No `--` with pnpm.
- `str.splitlines()` also splits on U+2028/U+2029, `\x1c`-`\x1e` and `\x85`, all legal inside
  JSON strings, so it silently breaks JSONL records that `json.loads` would parse fine. Split
  newline-delimited formats on `"\n"` (or iterate the file object); reserve `splitlines()` for
  human text.
- `re.sub`/`re.subn`: insert untrusted text with a callable (`lambda _: replacement`);
  replacement strings interpret backslashes and `\1`.
- Union Python sets with `update`/`|=`, never `set.add(other_set)`.
- `cargo test` accepts one positional filter: use a shared substring or separate runs.
- Before assuming `tests/` exists, read the package's test script or run
  `rg --files -g '*.{test,spec}.*'`.
- Inspect archive entries before asserting paths; validate a unique basename, not a guessed
  depth.
- Never filter default tsc output with `rg 'error TS'`: the pretty printer puts an ANSI reset
  between "error" and "TS", so a red build reads green. Use `--pretty false` first.
- Python test classes below `if __name__ == "__main__":` never run on direct execution but do
  under discovery, so both look green and direct runs silently drop cases. Keep the main guard
  last in the file.
- A file-wide `# shellcheck disable=` placed after the first command is silently inert (it must
  precede everything but the shebang and comments). gitleaks allowlist clauses are OR'd: a bare
  regex next to a paths clause exempts that pattern repo-wide. When an artifact asserts a
  property (suppression, allowlist, version banner), strip it and watch the finding appear.
- Tool versions disagree about real findings (ShellCheck, gitleaks). A cross-machine gate is
  reproducible only if it prints the tool versions with the verdict.
- **Rust links fail on the Mac after a Command Line Tools update that outruns Xcode.**
  `xcode-select` pointing at Xcode (its `ld`) while `xcrun --show-sdk-path` resolves the CLT SDK
  produces `ld: tapi error: malformed file ... unknown architecture` on every build script,
  minutes into a build. Check `ld -v` and `xcrun --show-sdk-path` come from the same developer
  dir before a long cargo run. Per-command fix:
  `DEVELOPER_DIR=/Library/Developer/CommandLineTools cargo ...`; the durable fix is the user's
  (`sudo xcode-select -s ...` or a matching Xcode).

## Tests

- **Linux-green, macOS-red has two systematic causes that are not product bugs.** `/proc` does
  not exist on macOS (mark `/proc`-mechanism tests `skipUnless(sys.platform == "linux")`;
  portable liveness is `os.kill(pid, 0)` plus `ps -p <pid> -o stat=`), and sub-second timing
  windows lose to macOS spawn latency (give about 10x margin). Run the commit on Linux before
  treating the failure as real.
- Suites that bind Unix sockets fail in agent worktrees on path length (`sun_path` is about 104
  bytes on macOS), not code. Re-run with a short `TMPDIR=/tmp/x` before trusting a worktree
  failure on socket-opening projects.
- **An exclusion added to cut noise silently redefines the question.** "Referenced outside its
  own file" is not "used": same-file consumers report as dead. State the predicate your filter
  actually implements, and hand-verify every positive hit by opening the defining file.
  "Imported only by tests" is not a defect signal; orphaned UI means nothing renders it, which
  is a different query.
- **Never fire a test write at a live credential-store item.** Keychain has no undo. Probe
  writability against a throwaway service name; diagnose failures by inspecting the exact argv,
  never by firing variants at the live item.

## Processes, servers, services

- Never pipe a long-lived server through `head`/`tail` in a background task: once the reader
  exits, the next write hits a closed pipe and the server wedges (alive, listening, not
  serving). Redirect to a file; `tail` separately.
- `pkill -f "next start"` does not kill a Next.js production server (the process is
  `next-server (v...)`). Killing by pattern is unsafe anyway (see the core rules). Kill by port
  (`lsof -ti :<port>`, inspect with `ps -p`), and verify the swap with a DB-backed route, never
  just a static page.
- **Before restarting a live service on Linux, check host load and D-state processes**
  (`ps -eo pid,stat,etime,cmd | awk '$2 ~ /D/'`). A restart during I/O saturation (a multi-GB
  rsync on the same dataset, a heavy build) can sit in filesystem transaction-group wait
  (`wchan` `__cv_timedwait_common` on ZFS) for minutes with no log line and read as a hung boot.
  Wait for the copy or pause it (`kill -STOP` / `-CONT`); never stack a second restart on top.
- **`kill -USR1` on a Node daemon is not "open the inspector"**: daemons map SIGUSR1 to their
  own restart (drain, exit 0; with `Restart=on-failure` the unit then stays down). To look
  inside a running service, use a `NODE_OPTIONS=--import=<preload>` drop-in and a planned
  restart, and try/catch every handler in the preload. An uncaught throw in a
  `diagnostics_channel` subscriber crashes the host process (an HTTP/2 response handed the
  handler an object where HTTP/1 hands an array), and a crash-loop breaker may then refuse to
  autostart the service's other integrations.
- `launchctl bootstrap gui/$UID <plist>` fails with `Input/output error` (5), and the job is
  absent afterwards, when the label sits in the domain's **disabled list** (left by an earlier
  `bootout`/`disable`; it survives a new plist). Run
  `launchctl print-disabled gui/$UID | grep <label>`, then
  `launchctl enable gui/$UID/<label>`, then bootstrap; use `launchctl kickstart -k` only after
  `launchctl print` shows the job. The plist itself lints clean, so the error reads like a
  permissions problem.
- `docker info` HANGS (not errors) when Docker Desktop is wedged, and a wedge is
  indistinguishable from a boot. Always `timeout 10 docker info`; a boot not done in about 90 s
  is a wedge. Read `~/Library/Containers/com.docker.docker/Data/log/host/com.docker.backend.log`,
  then do a full quit-and-relaunch.
- `ssh -n host 'cmd' <<'EOF'` runs `cmd` on empty input: `-n` points the remote stdin at
  `/dev/null`, so the heredoc is silently dropped and a `python3 -` script prints nothing and
  exits 0, which reads as "no findings". To feed a script, drop `-n`, or `scp` the script over
  and run it by path.
- Claude Code's built-in deletion check reads rm-shaped text anywhere in a command, including
  quoted data such as `printf` test lines or hook fixtures (`rm -rf "$D"/*`), and denies the
  whole call; nothing in it runs. Keep deletion-shaped test cases in fixture files written with
  the file tool and pass the path. Never re-issue the text another way to get past the check.
