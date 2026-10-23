# Shell footguns: core rules

Each rule below comes from a real incident. Read the reason before you weaken one.
Incident stories are in `shell-footguns-lore.md`; the long tail of tool-specific rules is in
`shell-footguns-catalog.md`. This one file covers macOS and Linux.

> **Note on what is here.** These rules were extracted from a private agent setup. Rules that
> only made sense inside its private tools (a shell-guard hook, launchers, internal mail and
> orchestration CLIs) were dropped; rules about shells,
> git, processes, tests and measuring tools were kept with their reasons. If your harness
> installs a pre-tool hook that denies machine-checkable mistakes, it enforces roughly the
> first half of this file at call time; the rest is judgment.

## Shell state

- `cd` does not persist between Bash calls in an agent harness that starts each call in the
  project directory (Claude Code with `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` does this,
  and it ended a class of silent working-directory drift). Pass directories explicitly
  (`git -C`, `pnpm --dir`, `make -C`, absolute paths) or `cd` inside the same call.
- **A backgrounded command runs in the session cwd**, not the directory you were just working
  in, and nothing echoes the resolved directory. Any backgrounded command that writes (build,
  install, migration) takes an explicit directory argument, every time.
- **Never write a file and consume it in the same Bash call.** A denied compound command runs
  none of it: the heredoc never created the file, the consumer never ran, and a backgrounded
  host task still reports "completed, exit 0" (that is the hosting task's status, not the
  command's). Write, then `test -f "$p" || { echo missing >&2; exit 1; }`, then consume, in
  separate calls.
- In JavaScript template literals or exec wrappers, never write shell `${...}`; use a plain
  command string or a quoted heredoc.

## Bash

- **`;` means "then", not "on success".** `cmd --body-file "$f"; rm -f "$f"` deletes the input
  when `cmd` fails, so the retry has nothing to send. Cleanup is `cmd && rm -f "$f"`, or a
  separate call after checking the result.
- **An unquoted heredoc expands `${VAR}` before the inner program sees it**, and a variable
  unset locally becomes an empty string with no warning. Writing a literal `${API_KEY}`
  reference into a config through `ssh host 'python3 - <<PYEOF'` stores `""`, and the next
  service restart authenticates as nobody. Quote the delimiter (`<<'EOF'`) whenever the body
  contains `$`, and read the written value back rather than trusting the write.
- **`set -e` does not abort on a command used as an `&&`/`||`/`if` condition:**
  `diff -q a b && echo same` sails past a failed comparison. Verify-before-delete is explicit:
  `diff -q a b || { echo "differs, aborting" >&2; exit 1; }`. Never delete the last copy of
  anything in the same command that deletes the rest; migrate, verify the union, then remove.
- **Never pass a possibly-empty variable to a deletion command.** `rm -rf "$UNSET/subdir"`
  deletes `/subdir`; `trash ""`, `trash .` and `trash "$UNSET"` each trash the current
  directory and exit 0 (`rm ""` errors harmlessly). Guard with
  `[ -n "$p" ] || { echo "empty path" >&2; exit 1; }`, re-read the path, and ask before
  removing anything you did not create.
- A gate piped through `tail`, `head` or `grep` inside a longer script or `;` chain masks its
  exit status: `echo "exit=$?"` reports the last pipeline stage. Use `set -o pipefail`, or grep
  the log for `FAILED|OK`, and never feed a filtered gate pipeline straight into `git commit`
  or `git push`.
- Quote every URL argument and query string: they are data, not shell syntax.
- Never put backticked code inside a double-quoted message argument (`--body "..."`): the shell
  runs the backticks and splices the output into the message. Prose containing shell syntax
  goes through `--body-file`, a heredoc, or single quotes.
- Single-quote `rg`/`grep` patterns. When a pattern fights the shell (quotes, backticks, `$`, a
  leading `-`), feed it on stdin: `printf '%s\n' 'pat' | rg -f - -- path/`. Not for newlines:
  `-f` reads one pattern per line, so a two-line pattern becomes two independent patterns that
  match non-adjacent lines. A multi-line pattern needs `-U`, never `-f -`.
- **The `grep` and `find` you call may be shell functions, not the binaries.** Claude Code's
  Bash tool shadows `grep` with bundled `ugrep` (silently applying `--ignore-files --hidden
  --exclude-dir=.git`) and `find` with `bfs`; mtime queries through the shadow can return a
  silently wrong count with no error. Anything whose correctness depends on exact semantics,
  mtimes, or seeing ignored/VCS files needs `command grep` and `/usr/bin/find` (or an absolute
  path). Interpreter shells can also shadow coreutils with builtins that take different flags
  (one reports `sort is a shell builtin` with a broken `-k2,2`); when a verify step's coreutil
  result matters, run it through `sh -c`.
- zsh is still reachable (subagent shells, `zsh -c`, habit). Under zsh `status` and lowercase
  `path` are reserved (capture exit codes as `rc`, never name a variable `path`; assigning it
  destroys `PATH`), unmatched globs error under `nomatch`, and `set -- $var` does not
  word-split. Quote globs, use arrays or tab-delimited `read`. Secret-safe smoke:
  `zsh -df -c 'command -v tool'`; never source startup files under `-x`.
- Records: `while IFS=$'\t' read -r file start end; do ...; done < records.tsv`; parallel arrays
  when assembled in-shell. File matrices:
  `while IFS= read -r file; do ...; done < <(rg --files -g '*.md')` with no command
  substitution and no unguarded globs.
- JSON: parse path-bearing JSON with `jq`, not regex (`rg --no-filename -o PATTERN` when the
  match itself is a path). Split arrays with `jq -c '.[]' file.json | while IFS= read -r item; ...`.
  Default optional arrays (`jq -r '.warnings // [] | .[]'`): iterating a null field aborts the
  whole run with "Cannot iterate over null", which reads like malformed input.

## Git

- `git status -sb` compares against the last-**fetched** ref, so a stale clone reads as
  current. `git fetch` before trusting a clone's HEAD, especially before promoting or
  deploying from it. Before Git-only verification run
  `git rev-parse --is-inside-work-tree >/dev/null 2>&1`; use a scoped snapshot check otherwise.
- **`git config user.name/email` inside a worktree writes the shared `.git/config`**, so every
  later commit in every worktree of that repo (other lanes included) carries the fake author
  until it is unset. Rehearsal identity goes on the command:
  `git -c user.name=… -c user.email=… commit …`. A merge script asserts
  `git config --get user.name` is the real author first.
- `git pull --ff-only` still honors a global `pull.rebase = true`, and git evaluates the rebase
  precondition first: an unrelated unstaged change aborts the pull (rc 128) even when the pull
  is a pure fast-forward. Automation that must fast-forward past unrelated edits passes
  `git pull --no-rebase --ff-only` or `git merge --ff-only @{upstream}`.
- **In a checkout shared by several lanes, `git commit` commits the whole index**, not the
  files you just added: another lane's staged deletions ride along under your subject line even
  when you `git add` by name. Commit with explicit pathspecs (`git commit -- <path>`) and read
  `git diff --cached --stat` first; never `-a`/`-A`.

## Processes

- **Zero CPU plus a silent log is what a healthy I/O-bound job looks like. Do not kill it.**
  CPU answers "is it computing", the log answers "is it printing"; neither answers "is it
  working". Probe what actually moves (`lsof -p <pid> -i` for sockets, `lsof -p <pid>` for
  files, the remote side's request log), and build a per-unit heartbeat line in before
  launching. A job you cannot cheaply prove alive will eventually be killed by mistake.
- **Never stop a systemd unit you found by reading a process's `/proc/<pid>/cgroup`.** A job
  not launched in its own transient unit lives in the shared login-session scope
  (`session-N.scope`) or an agent's scope, and `systemctl --user stop` on that name kills every
  agent on the box. Stop a heavy job only by the named `systemd-run --unit=<name>` unit it was
  launched in, or by its own PID tree (`kill -- -<pgid>` after `ps -o pgid= <pid>`). If the
  cgroup resolves to a `session-*.scope` or `user@*.service`, stop and re-derive the target.
  Give every heavy job its own named unit before it starts; where `testrun` is installed, run
  tests and gates through it (it provides a named unit in a capped slice), with an explicit
  worker cap, and never launch a second copy of a run already going.
- **Never kill by pattern.** `pkill -f <pattern>`, `killall <name>` and `kill -1` match across
  the whole host and will eventually reap a process you did not create. Every kill names a PID
  or process group you created and can check. This binds a test harness's cleanup exactly as
  hard as the thing it tests. Where cleanup looks necessary, prefer proving the owned tree is
  already gone and reporting a survivor over killing it: scan `/proc/<pid>/cmdline` for your
  own sandbox path and fail loudly. Wrap the read as
  `$( { tr '\0' ' ' < /proc/$pid/cmdline; } 2>/dev/null )`, since a pid exiting mid-scan makes
  the shell print its own redirection error.
- **Killing a `/usr/bin/time` or `timeout` wrapper does not kill what it wraps.**
  `kill -TERM "$pid"` on the wrapper reaps the wrapper and leaves the real child alive, so a
  `143` exit proves the wrapper got the signal and nothing about the workload. Run the job in
  its own process group (`set -m`, or `setsid`), signal the group (`kill -TERM -"$pgid"`), then
  re-enumerate the tree by `ppid` and confirm every descendant is gone before reporting it
  stopped.

## Tests and instruments

- **A new test or assertion proves nothing until you have watched it fail.** Run it against
  the pre-fix code and see red, or break the behaviour it guards once and confirm red. A guard
  can pass incidentally (probed file absent, branch never reached) and retire vigilance while
  guarding nothing. One mutation per new test is the bar; its other assertions ride on it.
- **A red-proof over an empty set passes and proves nothing.** Before asserting a detector or
  cleanup worked, assert the precondition that makes the test meaningful (the tree had two or
  more members, the match set was non-empty, the file had the marker) and fail the test when
  it does not hold.
- **State out loud what question an instrument actually answers before trusting it; the gap
  is the finding.** The dangerous ones answer a question adjacent to yours, and the true part
  buys credibility for a claim they never made. Judge detectors by output bytes, not exit
  status. One probe licenses one rule family, never the tool: run a battery, one single-defect
  file per rule family you believe exists, each alone, watching each fire. Design test for any
  probe: would the wrong implementation give a different answer in this exact scenario? Write
  the wrong version down and check. `du -s .next` is ~96% build cache; `rg -c name` answers
  "does this substring appear", not "does this identifier exist"; a build-time average whose
  first run followed an install reports warmup. Review the instrument as code, at the same
  standard as its subject, and re-read the artifact, not the report about it. This rule does
  not generalize on its own: re-derive it at every new instrument.
- **A whole-file grep on an append-only log answers "has this ever appeared", never "did this
  just happen".** A journal or `.jsonl` event log keeps every prior failure forever, so grepping
  it as a liveness trigger fires immediately off history. Baseline the length when you arm the
  check (`BASE=$(wc -l < "$f")`, then read only `tail -n +$((BASE+1)) "$f"`). The tell is a
  detector that fires faster than the event it watches could possibly have occurred.
- **File state is not evidence of mechanism.** "Unchanged, therefore something rewrote it" is
  a guess in a finding's costume. Probe the mechanism directly, and match probe polarity to
  the question (an addition surviving says nothing about whether a deletion would).

Before using rg/sed/perl/Python/zsh, package test tools, browser/server/process tools, systemd
or launchctl, Docker Desktop, keychains, macOS services or Rust linking, read
`shell-footguns-catalog.md`.
