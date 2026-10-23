# Fanning work out to other model families and providers

This guide sets up a delegation CLI so your main agent can hand bounded jobs to other coding-agent runtimes and model families: a cross-family reviewer that does not share your lead model's blind spots, and cheap workers for mechanical work. It also carries rules worth adopting about where your data may go, and the rate-limit traps that bite when you run many agents at once.

## Do you need this?

**Skip it** if one model family does everything you need and you never want a second opinion. Your lead agent's own subagents already cover plain parallelism within one family.

**Do it** if you want any of: review by a different model family (the single highest-value use), cheap parallel workers for mechanical changes, or a fallback when a subscription hits its limit.

**Cost:** a small Python CLI (`delegate`), plus whatever the extra lanes cost: subscriptions you already pay for, or metered API spend. It runs no daemon. The real weight is policy: every new provider is a new place your code can go, so decide the data rules (step 4) before you add one.

## Prerequisites

- Python 3.11+ and `uv` or `pipx` on each machine that will delegate.
- At least two agent runtimes installed and signed in, from different model families (for example Claude Code and Codex, or either plus Pi, OpenCode or Oh My Pi). The CLI cannot log in for you.
- If you run several subscriptions, set up [many-subscriptions](many-subscriptions.md) first so each delegated run uses the account you intend.

## Steps

### 1. Install the delegation CLI

```bash
uv tool install delegate-agent-cli      # or: pipx install delegate-agent-cli
delegate --version
delegate setup                          # discovers runtimes on PATH, writes a private cache; never logs in or edits an existing config
delegate --json describe                # command index; start here when unsure
delegate --json models --summary        # what each runtime can actually run now
```

`delegate` builds the child command, adds safety framing, launches the runtime and records run metadata under `.delegate/` in the workspace. It never commits, pushes, merges or deploys, and runs no background service. Add `.delegate/` to your global gitignore.

**Done when:** `delegate --json capabilities` lists every runtime you installed, and `delegate --json dry-run codex safe "Review this repository. Do not edit files."` prints a planned command without launching anything (swap in a runtime you have).

### 2. Learn the three modes

| Mode | What it does | Use for |
| --- | --- | --- |
| `safe` | Read-only review in an isolated copy of your working tree (uncommitted changes included) | cross-family review, investigation |
| `work` | Edit-capable; runs in the real workspace unless you isolate it | implementation |
| `call` | One stateless prompt, no repo, no tracked run | summaries, quick answers |

```bash
delegate codex safe "Review my uncommitted changes for regressions. Do not edit files."
delegate --isolation worktree claude work "Implement the scoped change, run the named check, report changed files."
delegate --json codex call "Summarize this in three bullets: ..."
```

Use `--isolation worktree` for any edit-capable run that overlaps files with other work: it creates a persistent Git worktree and keeps your checkout untouched. It protects against ordinary relative-path edits only; it is not a security sandbox. `safe` mode has no network access, so a review that needs to fetch something will fail in a way that looks like "the lane could not fetch": give it the material in the prompt or use `work`.

**Done when:** a `safe` review returns findings for a real diff, and `delegate runs` lists it.

### 3. Give models stable local names

Real model ids drift; keep your own aliases in the CLI's config so prompts, scripts and notes name roles, not ids.

```bash
delegate config init            # writes an editable example config
```

In the config, each runtime has a `models` map of alias to model id, and `--model <alias>` or `--model <raw-id>` picks one. Alias keys must not equal a mode name or the runtime's own name. Before asserting what a lane runs, check `delegate --json models <runtime> --live`: aliases drift and live discovery is the truth.

Suggested roles (names are yours): `reviewer` (a strong model from a family other than your lead), `worker` (cheap, fast, good at mechanical edits), `scout` (cheapest, read-only fact-finding), `slow` (a cheap lane for runs where wall-clock does not matter).

**Done when:** `delegate --json dry-run <runtime> safe --model reviewer "x"` shows the resolved real model id.

### 4. Write down your data rules, then encode them in the config

Adopt these before adding a third-party lane:

1. **Never send private data to a tier that trains on prompts.** Some providers sell a much cheaper tier (often an order of magnitude below standard) in exchange for training on traffic. It is fine for open-source or throwaway code; it is not fine for client work, legal or policy drafts, personal data or secrets. If a tier is cheap and its terms are vague, assume it trains.
2. **Keep a standard-price twin for sensitive work.** Where a provider offers the same model at a no-training price, give it its own alias (`<name>-std`) and route private material only there.
3. **Choose where open-weight models run.** Hosts of the same open model differ in country and retention. Decide which hosts you accept (for example, US-hosted inference only) and pin those providers; route those models through nothing else. Verify hosting claims from the provider's documentation or by behavior (with a "allow China-hosted models" account toggle off, a China-only model id should be refused with an error, not quietly served). A founder's statement in chat is not a record.
4. **No silent escalation.** Do not configure a fallback that moves a cheap lane to a model 10x the price. A run that fails loudly on the cheap tier is better than a surprise bill. If a lane fails on a "data policy" error, the fix is the provider's privacy setting, not a fallback.
5. **Know what bills by the token.** A subscription lane and a metered API lane can look identical from the CLI. One runtime posted chat turns to a metered API while only reading quota from the subscription, which would have spent real money when the subscription was exhausted. Read the runtime's source or docs for the billing path before you rely on "free".
6. **Secrets stay out of config.** Delegate profile `env` blocks hold routing pointers only (like `CODEX_HOME`); secret-shaped keys are rejected at load. Keep real keys in your shell or a key store, and see the profile section of [many-subscriptions](many-subscriptions.md) for per-profile key files.

**Done when:** you have a written table of every lane: its provider, whether it trains on prompts, whether it bills per token, and which data classes may use it. Every lane marked "trains" or "unknown" is excluded from private repositories.

### 5. Pin or allow failover per run

Some runtimes (Oh My Pi) can fail over to another provider or model mid-run. Delegate marks a run **pinned** when you type a raw `provider/model-id`, and **fungible** when you use an alias or nothing. A pinned run that gets served a different model fails with `model_continuity_paused` naming what it tried to serve. A fungible run records a `model_substitution` warning. Use `--continuity-mode pinned` when the exact model matters (reviews you will compare across families), `fungible` when you only need an answer.

Codex runs can also fail over across credentials: `codex.fallbackProfile` names a second profile used when the first hits a quota. Set it only to a profile your data rules allow.

**Done when:** a pinned run on an alias-free raw id refuses a substituted provider in a dry-run or a forced failure test.

### 6. Make cross-family review the habit

- Review needs a different model *family* from the author, not just a different model. A reviewer from the same family shares the author's blind spots.
- Reviewer quality varies a lot between lanes. Scoring candidate reviewers by verified findings on one codebase showed a wide spread: one lane produced nearly all the verified findings, including real blockers, while others were mixed or unreliable (one called a revision "production-ready" whose success path could not persist). Measure your own: keep a short log of findings each reviewer made and how many were real.
- A child's report is a claim, not evidence. Open the artifact, rerun the check, then accept.
- Ask a worker for tests and red-proof, but do not trust that it did them: in practice workers in some lanes shipped implementation twice without the briefed tests, even after being asked again. Keep verification with the coordinator or a separate lane.
- Cluster related work into one richer delegation instead of many narrow ones. Fan out only across independent units with disjoint files.
- When a delegated run is long, use `--progress` for heartbeats and `--notify` for a one-line completion message if you run the Post mailer. Do not cancel a run because its `current` string still shows an old error: check fresh events and output-byte progress first (healthy fallback reviews get cancelled that way).

**Done when:** your lead agent's instructions say: "before merging non-trivial work, run `delegate <other-family> safe` review, verify each finding, and fix the real ones".

### 7. Cap parallelism per lane

Set per-lane concurrency from the provider's *token* limit, not its request limit (see the first papercut). In the delegate workflow config, `engineCaps` takes a positive integer cap per engine name. For launches outside a workflow, cap by hand: start two agents at a time on any fast lane and raise only after you have watched a full minute of its throttle headers.

**Done when:** each lane in your table has a concurrency number and a source for it (a header reading, a published limit or a provider answer).

## What bit us (papercuts)

1. **Seven parallel agents on a fast provider throttled within a minute.** The provider generated several hundred tokens per second per agent and capped the key at about 1M tokens per minute, counting cached input at full weight. Every agent step re-sends its whole conversation, so tokens per minute is roughly agents × steps per minute × context size, far above what the output speed suggests. Measured: one agent alone sent hundreds of thousands of input tokens in its first minute (about 17 steps of roughly 50K tokens each), and most of the input across the run was cache hits that the cap still counted in full; output was a few percent of input. Two agents at once still hit the cap within a dozen steps each, and even one agent alone hit it once its context grew. The retries backed off for seconds, which cannot clear a window that is measured per minute, so they kept hitting the same full window. → What worked: one agent at a time on that key, told to start every shell command with `sleep 20 &&` so it stepped a few times a minute instead of every few seconds; it then finished in one clean run. Otherwise ask the provider for a higher cap. Size concurrency from token arithmetic (agents × steps per minute × context), not from agent count or output speed.
2. **The binding limit is usually tokens per minute, not requests.** On one provider the request allowance (thousands per minute) sat far above observed peaks (under a hundred per minute) while token peaks ran past the token allowance, and the failover layer masked the overruns. On another, a 450 requests/min limit was never touched while 150K tokens/min was the wall. → Wide-and-shallow (many small-context calls) is nearly free; a few token-heavy agentic lanes saturate the cap. A handful of heavy lanes is a sane ceiling at a few M tokens/min. A rate-limited client should read the `x-ratelimit-remaining-tokens-minute` header, sleep when it is low (a floor of roughly 10K works), and honor `retry-after`.
3. **Dozens of concurrent agentic lanes hit 429 within minutes.** → Stagger launches or cap concurrency; a 429 here means window saturation, so wait for the next minute window rather than abandoning the lane.
4. **A run reported `succeeded, exit 0` after its provider session ended in a 429 error after ten auto-retries.** The only hint was an "empty result" quality flag. → Check `resultQuality` and the final stop reason, not just exit status. (Fixed in current delegate-agent, but verify any wrapper you build the same way.)
5. **A degenerate review looped on markdown backticks for tens of thousands of characters and exhausted the shared token quota within minutes.** → Put a wall-clock and output cap on review lanes; a long run with no new substantive output is stuck, not thorough.
6. **A cancelled lane launched with `--isolation none` wrote into the source checkout.** → Isolate any lane you might cancel.
7. **Credentials and config precedence surprise.** An environment variable from the current profile can override `--auth-profile`; strip it explicitly (`env -u DELEGATE_CONFIG`) when you mean the other profile. A managed config file that your sync tool owns will lose hand edits on the next install: edit the source of truth.
8. **Another runtime's profile directory was ignored.** Oh My Pi read per-profile config files and never the shared ones, so shared files edited by the sync tool were dead copies until both machines symlinked the per-profile paths to them. → After editing shared config, run one real delegated call and confirm the change took effect.
9. **A model "at capacity" error can kill long runs mid-verification.** The sessions were resumable and worktree state intact. → Commit the worktree by file name and resume or take over; do not restart from scratch.
10. **A fast, cheap model that scored near the frontier on coding benchmarks scored half of it on long-horizon terminal tasks.** → Use such models as fast bounded workers, never as the lead.
11. **A flat-rate lane failed over to a pay-per-token lane when its window ran out.** An exhausted flat-rate window answered 402 "insufficient account funds" because the pay-per-token balance behind it was zero, and the runtime then used its configured fallback; with a funded balance it would have billed silently. → Know the next lane in the ladder and its cost before you exhaust the first, and keep unwanted balances at zero.

## Reference snippets

Per-engine caps for delegate workflows (`workflows.engineCaps` in the delegate config; engines without an entry are uncapped):

```json
{"workflows": {"engineCaps": {"codex": 4, "claude": 2, "omp": 2}}}
```

Shape of a lane table (keep it in your repo's docs):

| Lane | Provider | Trains on prompts | Billing | Concurrency | Allowed data |
| --- | --- | --- | --- | --- | --- |
| reviewer | family B subscription | no | flat | 2 | all |
| worker | cheap fast subscription | no | flat | 4 | all |
| bargain | contributor tier | yes | per token | 4 | open-source and throwaway only |

## Keeping it healthy

- `delegate --json models --live` after any runtime upgrade; aliases that point at removed ids fail at launch.
- Review the lane table monthly and whenever a provider changes terms or hosting.
- Clean up `.delegate/` runs and worktrees: `delegate worktree list`, then `delegate worktree remove <alias>`; retention defaults prune raw logs after 7 days and scratch after 3.
- Re-measure each fast lane's token limit with its headers when you change concurrency, model or context size.
- Record changes to the data rules with a date and the reason, so the next person knows why a lane is excluded.

Last checked: 2026-10, Debian 12 and macOS.
