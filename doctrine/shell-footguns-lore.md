# Shell footguns: lore

The incident behind each rule in `shell-footguns.md` and `shell-footguns-catalog.md`. Names,
hosts and products are removed; the failure and the lesson are kept. Read the story before you
weaken the rule it produced. When you hit a new rake, append its story here and add the rule
to the core file (or the catalog, if it is tool-specific).

## Working directory and backgrounding

**`cd` does not persist.** Agent harnesses that start every Bash call in the project directory
(Claude Code with `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`) removed a class of silent
cwd-drift bugs. The cost is that you cannot rely on a prior call's `cd`: pass directories
explicitly (`git -C`, `pnpm --dir`, `make -C`, absolute paths) or `cd` within the same call.

**The backgrounded build in the wrong checkout.** An agent backgrounded `pnpm gate` while
mentally "in" a git worktree. The command ran in the session cwd, which was the main checkout,
where a dev server was live and serving from the same `.next` directory: the exact clobber the
project docs warn about, reached from a direction the warning does not describe. It was caught
during lint, before `next build`, so no damage. A `cd` inside the backgrounded command does not
help you reason about it either, because nothing echoes the resolved directory. Rule of thumb:
any backgrounded command that writes takes an explicit directory argument, every time.

## Deleting, chaining and quoting

**`set -e` and the consolidation script.** A consolidate-then-delete script guarded its
deletion with `diff -q a b && echo same`. `set -e` does not abort on a failing command used as
an `&&`/`||`/`if` condition, so the script went past a failed comparison and destroyed the only
differing copy of a file. Verify-before-delete must be explicit
(`diff -q a b || { echo differs >&2; exit 1; }`), and never delete the last copies of anything
in the same command that deletes the rest: migrate, verify the union, then remove.

**The empty variable.** `trash ""`, `trash .` and `trash "$UNSET"` each move the current working
directory to the trash and exit 0, while `rm ""` errors harmlessly. A blanket machine-wide
block on agent `rm` was tried and abandoned as a failed experiment; the durable defenses are
the guard (`[ -n "$p" ] || ...`), re-reading the path you are about to delete, and asking before
removing anything you did not create.

**The denied compound command.** `cat > brief.md <<'EOF' ... EOF` followed by a launcher that
reads `brief.md` is one Bash call. When a pre-tool hook denied it for the launcher half, the
`cat` never ran either, so the brief did not exist, and the launcher never ran, so nothing
reported the missing brief. The backgrounded lane still reported "completed, exit code 0" to
the harness's task notifier, because that reports the hosting task, not the command. A
silently failed review read as a successful one and cost a long, expensive contract review. The
launcher itself was not lying: given a missing prompt file it correctly prints an error and
exits 2. Rule: never write a file and consume it in the same call. Write it, verify it with
`test -f`, then consume it in a separate call. This applies to every write-then-consume pair.

**Cleanup chained with `;`.** `send-message --body-file brief.txt; rm -f brief.txt` deletes the
brief when the send errors, so the retry has nothing to send and the only copy of the message
is gone. `;` means "then", never "on success". It is the same family as write-then-consume: the
input and its consumer belong to different fates, and `;` gives them the same one. Chain
cleanup with `&&`, or leave it to a separate call after you have checked the result.

**The unquoted heredoc.** Writing a literal `${API_KEY}` environment reference into a config
through `ssh host 'python3 - <<PYEOF'` stored an empty string, because the unquoted heredoc
expanded the variable (unset locally) before the inner program saw it. The next service restart
authenticated as nobody. Quote the delimiter whenever the body contains `$`, and read the
written value back.

**Backticks in a message body.** Two agents independently mailed a channel 127 KB of unrelated
backlog output because a backticked command inside a double-quoted `--body` argument was
executed by the shell and its output spliced into the message. Prose containing shell syntax
goes through `--body-file`, a heredoc, or single quotes.

**Quote the pattern, not the shell.** The native fix for most "my regex got mangled" dead ends
is to stop escaping and feed the pattern on stdin (`printf '%s\n' 'pat' | rg -f - -- path/`),
so the shell never parses it. The limit is newlines: `-f` reads one pattern per line, so a
two-line pattern becomes two independent patterns. On `alpha/MIDDLE/beta`, `rg -f -` returns a
match while the correct `rg -U 'alpha\nbeta'` returns none.

## Git

**A stale clone promoted to a live runtime.** `git status -sb` shows ahead/behind only against
the last-fetched ref. With no fetch, a stale clone reads as current ("main...origin/main", no
markers). A clone five commits behind was promoted to a live runtime this way. `git fetch`
before treating a clone's HEAD as the latest.

**The rehearsal author that spread to every lane.** During an overnight multi-agent build, the
coordinator rehearsed merges in a throwaway worktree and set `git config user.name rehearsal`
and `user.email rehearsal@local` there so the rehearsal commits would be recognisable.
`git config` without `--worktree` writes the repository's shared `.git/config`, so from that
moment every commit in every worktree of the repo, including the delegated lanes' own commits,
was authored `rehearsal`. It was found only when the coordinator checked
`git config --get user.name` before the next merge, hours later, after the fake-authored
commits had been pushed. History was left alone and the report disclosed it. Rule: rehearsal
identity goes on the command (`git -c user.name=… -c user.email=…`), never into config, and a
merge script asserts the author name before merging.

**`git commit` in a shared checkout swept another lane's staged deletions.** Three sessions
shared one checkout. One lane had staged three file deletions and not yet committed. A second
lane ran `git add <file>` (by name, as the rules say) and then plain `git commit`, and the
commit carried the three deletions under an unrelated subject. Nothing was lost (the deletions
were intended), but history attributed them to the wrong change. `git add` by name limits what
you stage; only `git commit -- <path>` limits what gets committed. Read
`git diff --cached --stat` before committing anywhere more than one lane works.

**`git pull --ff-only` and `pull.rebase`.** With a global `pull.rebase = true`, git evaluates
the rebase precondition before the fast-forward, so an unrelated unstaged change aborts the
pull with rc 128 ("cannot pull with rebase: You have unstaged changes") even when the pull is a
pure fast-forward. Use `git pull --no-rebase --ff-only` or `git merge --ff-only @{upstream}`.

## Tools that are not the tools you think

**The shadowed `grep` and `find`.** Claude Code installs shell functions shadowing both: `grep`
becomes bundled `ugrep` with `--ignore-files --hidden --exclude-dir=.git` silently applied, and
`find` becomes `bfs`. Results are pre-filtered and regex dialects differ from GNU/BSD. A
recency query through the shadow returned 10 files where `/usr/bin/find` returned 30 on the same
tree at the same instant, and 0 for a job actively writing every four seconds; a 0 reads as "this
process is stalled", precisely the wrong conclusion. Verify rows in a plan are the usual
victims: they read as green while matching nothing. Anything whose correctness depends on exact
grep semantics, mtimes, or seeing ignored files must call `command grep` or an absolute path
explicitly. Coreutils can also be shadowed by an interpreter's builtins (another harness's
persistent shell reported `sort is a shell builtin` with a broken `-k2,2`); when a verify step's
coreutil result matters, run it through `sh -c`.

**`perl -i` with a manual slurp.** An explicit-slurp one-liner
(`perl -i -e 'my @l=<>; ... print @l' file`) truncated a 113 KB test file to 0 bytes and dumped
the content to stdout, because `-i` redirects output to the file only for `-p`/`-n` loops. It was
recovered only because HEAD held the file. For trailing-newline or EOF surgery use byte-safe
Python.

**`rg -r` and the fabricated result.** `rg -rn PATTERN path` consumes `n` as the replacement
string and prints every match rewritten to the literal `n`: output that looks like a real
result and is entirely fabricated. Several cuts of one sweep also misdiagnosed a nonexistent
path in rg's arguments (it prints an error to stderr, then searches the remaining paths anyway
and exits 0 on a hit) as rg mishandling `-g` globs placed after the path. It does not; guard
optional paths before passing them.

**`pnpm run <script> -- <filter>`.** In one repo, `pnpm test:unit path/to/one.test.ts` ran one
file, while `pnpm test:unit -- path/to/one.test.ts` ran the whole suite and passed, so nothing
signalled that the scoping was ignored. Pass filters to pnpm with no `--`.

**zsh `set -- $var`.** `sizes="1920 1080"; set -- $sizes` leaves `$#` at 1 with `$1` the whole
string, where sh and bash give 2. Loops built that way silently see an empty `$2` and compose
malformed filenames. Use `${=var}` to force splitting, or better, a real array.

**The `tsc` pretty printer.** A verification step piped default `tsc` output through
`rg 'error TS'`. The pretty printer emits an ANSI reset between "error" and "TS", so the pattern
never matched and a red build reads as green. An agent shipped a broken re-export while its
verification silently passed. Use `--pretty false`.

**Hand-typed screenshot names.** macOS puts a narrow no-break space (U+202F) before "AM"/"PM"
in screenshot filenames. A hand-typed `cp "Screenshot ... 2.10.29 PM.png"` fails with "No such
file or directory" even though `ls` shows the file. Use a glob or `find -name`.

**`ssh -n` and a heredoc.** `ssh -n host 'cmd' <<'EOF'` pointed the remote stdin at `/dev/null`;
the heredoc was silently dropped, a `python3 -` script printed nothing and exited 0, and the
result read as "no findings". Drop `-n`, or `scp` the script over and run it by path.

**The deletion check that reads quoted data.** Claude Code's built-in deletion check reads
rm-shaped text anywhere in a command, including quoted `printf` test lines and hook fixtures
(`rm -rf "$D"/*`), and denies the whole call; nothing in it runs. Keep deletion-shaped test
cases in fixture files written with the file tool, and pass the path. Do not re-issue the text
another way to get past the check.

## Servers, services and signals

**The server that wedged behind `head`.** `npm run dev 2>&1 | head -30` in a background task
wedges the server once `head` exits: the next write hits a closed pipe, and the process stays
alive and listening but stops serving. Two consecutive boots pegged about 120% CPU, TCP
connected fine, and there were zero HTTP responses; two long visual-QA preflights were burned.
Redirect to a file (`nohup npm run dev > dev.log 2>&1 &`) and `tail` it separately.

**`pkill -f "next start"`.** It did not kill a running Next.js production server: the process is
named `next-server (v...)` and the npm wrapper that matched "next start" was already gone. The
port stayed held, a later dev server failed to bind, and probes against static routes (a login
page returning 200) falsely confirmed "the new server is up" while every DB-backed route
returned 500. That burned a full ten-agent visual-QA run. Kill by port (`lsof -ti :<port>`),
inspect with `ps -p`, and verify the swap with a DB-backed route.

**The restart that looked like a hang.** Restarting a live service while a multi-GB `rsync`
sat on the same ZFS dataset left the service in transaction-group wait for minutes with no log
line, which read as a hung boot. Check host load and D-state processes before restarting, and
never stack a second restart on top.

**Stopping a systemd unit found through `/proc/<pid>/cgroup`.** An agent resolved a long timing
measurement's cgroup to a systemd scope and ran `systemctl --user stop` on it. The job had not
been launched in its own transient unit, so the scope it found was the shared agent scope, and
the stop took out every other running agent session on the box. Stop a heavy job only by the
named `systemd-run --unit=<name>` unit it was launched in, or by its own PID tree.

**`kill -USR1` to open the Node inspector.** Node's default SIGUSR1 handler starts the inspector
only when nothing else owns the signal. An agent gateway daemon registers SIGUSR1 as "restart",
drained cleanly and exited 0, and the unit's `Restart=on-failure` treated a clean exit as final:
the gateway stayed off until a manual start (the unit now uses `Restart=always`, matching the
daemon's own template). The replacement instrument, a `NODE_OPTIONS=--import` preload tapping
`undici:*` diagnostics channels, then crashed the gateway three times: HTTP/2 responses deliver
`response.headers` as an object, HTTP/1 as an array, and a `.map` call threw inside the channel
subscriber, which is an uncaught exception in the host process. The daemon's crash-loop breaker
then refused to autostart its chat integrations on the next boot. Rules: a daemon's signals are
the daemon's; every handler in a preload is try/caught; after any restart storm, check the
integrations came back.

**`launchctl bootstrap` and the disabled list.** `Input/output error` (5) from
`launchctl bootstrap` with the job absent afterwards means the label is in the domain's disabled
list from an earlier `bootout`/`disable`. It survives a new plist, and the plist lints clean,
which is why it reads like a permissions problem.

**Docker Desktop, wedged versus booting.** During a ship gate the tray app and
`com.docker.backend` were running and `/var/run/docker.sock` accepted connections, yet the Linux
VM had never started, so every `docker` command blocked forever instead of erroring, and a
polling loop read the wedge as "still booting" indefinitely. The tell was in the backend log:
`apiproxy ... still dialing ...: no route to host` on repeat, with an empty VM log directory. A
full quit-and-relaunch brought the engine up in 10 seconds after 15 minutes of fruitless waiting.
Never probe Docker unbounded (`timeout 10 docker info`), and cap the wait: a boot that has not
finished in about 90 seconds is a wedge.

**The linker that had never heard of `arm64e.x1`.** A Rust reinstall failed on build scripts
with `ld: ... tapi error: malformed file .../MacOSX27.0.sdk/usr/lib/libSystem.B.tbd: unknown
architecture arm64e.x1-macos`, though nothing in the repo had changed. A Command Line Tools
update had installed a newer SDK and linker, while `xcode-select -p` still pointed at an older
Xcode and `xcrun --show-sdk-path` resolved the CLT's new SDK anyway: the old Xcode linker was
handed new SDK stubs that name an architecture it does not know.
`DEVELOPER_DIR=/Library/Developer/CommandLineTools` in front of cargo paired the CLT linker
with the CLT SDK and the build finished in 30 seconds. A linker error naming an SDK path is a
toolchain-pairing question, not a code question: compare `ld -v` against the SDK's developer
dir before reading any Rust.

## Browser and credentials

**The React login that posted empty credentials.** Setting a field's value programmatically
works, but a Next.js Fast Refresh rebuild between fill and click silently remounts the form and
clears both fields, so the submit posts empty credentials and the page sits on /login with no
error. Click-then-type avoids the value problem but drops keystrokes if the page has not
finished hydrating. Re-read the field values immediately before submitting, expect this
whenever you have just edited source, and add a wait after each click. It cost a dozen failed
logins.

**Admin console buttons and leaked secrets.** Two traps hit while driving a cloud console and
a workspace admin console through a devtools MCP. (1) An admin console can build buttons as
`DIV[role=button]` wrappers around a text span; `el.click()` returns without error and does
nothing, because the handler listens for pointer events. Dispatch the full sequence on the
`[role=button]` ancestor, with `clientX/clientY` from `getBoundingClientRect()`. (2) A cloud
console can put freshly minted credentials into `aria-label` text (`"Copy to clipboard: ..."`), so
any snapshot or button-label scrape pulls the OAuth client secret into the transcript whether
you asked for it or not; the same is true of MCP tools that return created secrets. Assume
credential-creating flows leak into the log, tell the user, and treat rotation as the remedy.

**Fonts and ligatures.** A PIL/Pillow render of a ligature font shows `=>` and `!==` as separate
glyphs no matter what the font supports, producing a font comparison that looks authoritative
and is wrong. Render candidates in a real browser, with `font-feature-settings:"calt" 1,"liga" 1`
for the shaping arm and `"calt" 0,"liga" 0` for the no-ligature arm.

**The stale frame after a reload.** Measuring a terminal-config reload and a screenshot in one
call sampled a shader's output as pure black and concluded the background was unbound, when the
shader simply had not painted a frame yet. That reads as "my change did nothing" and invites a
second, wrong change on top of the first. Capture in a separate later call, and re-capture
before believing a measurement that contradicts what a change should have done.

**Single-use tokens.** Passing a seeded challenge or magic-link gate burns the token, so
re-opening that URL later renders the expired state, which reads as a regression in the surface
you were about to re-verify rather than as the fixture doing its job. Seed fixtures usually
include several tokens for exactly this reason: spend a fresh one per verification pass and keep
one unconsumed if you need to re-check the pre-auth surface. Cookies compound it, since the same
browser session may skip the gate, so a clean check needs an incognito context.

**A test write to a live keychain item.** Debugging a failed `security add-generic-password` by
re-running it "simplified" (`-X 74657374`) against the real service item overwrote the stored
value with the literal word "test". Keychain has no undo; the cost was a re-login. The actual bug (a list-splice that fed `-a`
as the `-s` value) was visible in the exact argv that had failed. Probe writability against a
throwaway service name and diagnose real failures by inspecting the argv.

## Tests, jobs and instruments

**Zero CPU and no output is a healthy I/O-bound job.** A long network-bound run (an eval
sweep) at low concurrency spent nearly all its wall time blocked on sockets: `top` showed about
0% CPU and the log had not grown in forty minutes, which reads exactly like a hang. Two hundred
sequential provider calls at concurrency 4 is legitimately forty-plus minutes of silence, and
the run was killed twice, costing it twice over. Probe the thing that actually moves
(`lsof -p <pid> -i`, files being written, the remote side's request log), and build the
heartbeat in before launching: append one line per completed unit. Corollary: a job you cannot
cheaply prove is alive is a job you will eventually kill by mistake.

**Five instruments that were each true about something.** In one long session five instruments
misled in the same shape: each was true about something, and the true part bought credibility
for a claim it never made. A design detector reported success on a file it never examined (true:
every rule it owns passed; asked: does this conform to the design system). Proving it fires with
one bad file is not enough, and this very entry said so for hours before its own advice was
caught being wrong: a single probe licenses one rule family and gets read as licensing the tool.
The battery is the ritual, **one single-declaration file per rule family you believe exists, each
run alone**. Run that way, the same detector enforced only out-of-palette colour literals and
off-scale radii, and sat silent on the elevation ban and every type axis, so a token-coloured
30px drop shadow passed clean. A split-attribution test built specifically to embody this rule
still missed half of it: its stub degraded on only one of two splits, the other split's count
was zero, and `total - other` and `total` returned the same number, so a real bug passed a test
written to catch that class of bug. The design question is not "is my probe targeted" but "would
the wrong implementation give a different answer in this exact scenario?": write the wrong
version down and check. Others from the same session: `du -s .next` counts about 96% build cache
(true: directory size; asked: shipped bytes); a build-time average over three runs where the
first followed an install reported an 11.8% spread against a real 0.9% (discard a warmup run);
`rg -c 'someName' file` answers "does this substring appear", not "does this identifier exist".
A code comment naming a real consideration buries the one it missed, because a wrong comment
gets challenged while a true-but-partial one gets trusted. And **review the instrument as code**:
scrutiny follows the thing under test while the tool rides in on borrowed trust, so both of that
session's instrument failures were in the measuring script (a lint error inside the walker, and a
same-file exclusion inside the dead-code sweep), each written by a different agent and neither
reviewed at all. The sharpest sub-case: an instrument earns extra trust from what it just got
right, so the report of a correct finding is believed as a report of a correct write. Re-read the
artifact, not the claim about it. Four of the five failures were by agents who had already
written this entry, which is the evidence that it does not generalize on its own.

**The dead-code sweep.** The natural way to find unreferenced symbols is to grep the tree and
exclude each symbol's own defining file. That exclusion also hides legitimate same-file use, so
any symbol exported for testability and consumed by its own module reports as dead. A sweep of
hundreds of exports flagged a React component as orphaned when it was rendered eleven lines below its own
definition by a live parent, one step from a cleanup lane deleting it. The filter answered
"referenced outside its own file", which is not "used". State the predicate your exclusion
implements, and hand-verify every positive hit; a "no results" list needs no check. In the same
sweep, "exported and imported only by tests" was not a defect signal at all (over a hundred hits,
nearly all healthy helpers and pure functions tested directly); the real signal for orphaned UI is that
no route or parent renders it.

**Unix sockets in a worktree.** `sockaddr_un.sun_path` is about 104 bytes on macOS, and an agent
worktree path plus a `tempfile` subdirectory overruns it. A suite that passes in the main
checkout failed dozens of tests in the worktree and passed them all with
`TMPDIR=/tmp/x python3 -m pytest` on the identical commit. It reads as "the delegated change
broke the tests" and invites reverting good work. Re-run with a short `TMPDIR` before trusting a
worktree failure on any project that opens Unix sockets.

**A test that passed because its subject did not exist.** A guard test for a config overlay's
symlink check "passed" because the overlay name did not exist, not because the check worked.
Run the test against the pre-fix code, see red, then trust green. Generalized: every new
assertion is unproven until you have watched it fail. Break the thing it guards, one mutation at
a time (copy the file, patch one anchor, run, restore). An adversarial reviewer once predicted
exactly which of six new assertions would survive a mutation and was right: the gap was
invisible until mutated, and the suite had been "passing" the whole time. (The later practical
bar is one mutation per new test, because per-assertion mutation runs were more than half of a
build lane's test runs.)

**A file that looks untouched.** An unchanged config four hours after a backup was read as "live
processes clobber external edits". A direct probe showed the opposite: the edits had been landing
on a file nothing reads. Probe the mechanism before designing around it, and pick the probe's
polarity to match the question: testing whether an addition survives says nothing about whether
a deletion does, because a union-merge preserves one and reverts the other.

**One gate, two verdicts.** ShellCheck 0.11 resolves `source` targets that 0.10 cannot, so the
same commit was green on one machine and red on another with 22 SC2218 errors; two builds of
gitleaks disagreed about what counts as a leak. Green on one box is not green: when a gate
result matters across machines, print the tool versions alongside the verdict.

**Inert suppressions and OR'd allowlists.** A three-code `# shellcheck disable=` placed after
`set -Eeuo pipefail` suppressed nothing and had been dead since the day it was written;
ShellCheck does not warn, and file-wide directives must precede everything except the shebang
and comments. gitleaks allowlist conditions are OR'd, so a bare regex clause next to a paths
clause exempts that pattern repo-wide, not just in those paths. When an artifact asserts a
property, strip it and watch the finding appear.

**Tests below the main guard.** Python test classes defined below `if __name__ == "__main__":`
never run on direct execution (`unittest.main()` collects before the class exists), while
discovery imports the module and sees them, so the suite looks green both ways and the direct
run silently drops cases (measured 12 versus 14). The general form: anything that makes test
collection depend on execution order. Keep the main guard last in the file.

**Linux-green, macOS-red.** A cross-platform suite green on Linux can be red on macOS for two
systematic reasons. (1) `/proc` (lock tables, per-pid liveness, fd listings) does not exist on
macOS: a `/proc`-probing helper "succeeds" instantly with empty or gone answers, so a
wait-for-death helper returns while the process still runs and downstream assertions fail
confusingly far from the cause. (2) Sub-second timing windows (kill a fake child 0.2 s after
spawn, asserting something it prints at startup was captured) lose to spawn latency under load;
give about 10x margin (a 1.5 s window against a 5 s sleep). Diagnose by running the same commit
on a Linux box before treating the failure as real.

**The wrapper that did not die.** Killing a `timeout` or `/usr/bin/time` wrapper reaps the
wrapper and leaves the real child alive, so a `143` exit proved only that the wrapper got the
signal: a "yield" that never yielded. Run the work in its own process group, signal the group,
re-enumerate by `ppid`, and confirm every descendant is gone before reporting it stopped.

**Cleanup that sweeps the box.** A test harness's cleanup is bound by the same rule as the thing
it tests: `pkill -f <pattern>`, `killall` and `kill -1` match across the whole host and will
eventually reap a process you did not create, so a red-proof whose teardown sweeps the box is a
worse defect than the bug it was written to catch. Every kill names a PID or process group the
script created. Prefer proving the owned tree is already gone and reporting a survivor.

**The red-proof over an empty set.** A detector or cleanup test that scans an empty set passes
and proves nothing. Assert the precondition that makes the test meaningful (the tree had two or
more members, the match set was non-empty, the file had the marker) and fail the test when it
does not hold. A green whose subject was absent is worse than a red.

**A log grep that fired before the event.** `grep -q 'agent_rejected|agent_timeout' journal.jsonl`
used as a liveness trigger fired immediately off history and named a failure that was not
happening. The tell was a detector firing faster than the event could possibly have occurred.
Baseline the length when you arm the check and read only what was appended after it.
