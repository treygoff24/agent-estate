# Installing agent-estate

For the person's own coding agent (Claude Code, Codex, Pi or another harness). Work through this top to bottom. Every step names the exact command, what you must ask the person for, and a **done when** check, which is almost always a row of `estate doctor`. Ask the person only for what you cannot read off the machine; never invent an email, host, account or key. Run the commands exactly as written; where a value is in `<angle brackets>`, it is one you collect or read, never a literal.

The whole job is finished when `estate doctor` exits 0 on **every** machine (the Mac and each Linux box). A warning (exit 2) is not done.

## 0. Before you start

Tell the person, in your own words, what is about to happen:

- **What gets installed.** A set of small tools and timers, per machine, under their home directory: nightly git sync, config sync (rules, hooks and settings for every harness kept in one private git repo), a key file, usage polling, test-load guardrails, an hourly health report, scratch cleanup. On a Linux VPS, one extra root-only step makes the box safe for agents (a login with no sudo, a firewall, security updates). Nothing is installed outside their home except that one step.
- **What you will ask of them**, so they can plan:
  1. Their name and email (for git), if the machine has none set.
  2. Where their private git repos live (GitHub is fine) and to create one empty private repo called `agent-env`.
  3. Run a few `sudo` commands on the VPS (one script, run twice, plus `sudo tailscale up --ssh` and `sudo estate-firewall confirm`; without Tailscale, one run and the confirm). On a minimal VPS image, first `sudo apt-get install -y git python3`.
  4. On the Mac, if they want the `skills` module: approve installing Rust (rustup) and, if missing, the Xcode command line tools. That module builds the `skillherd` tool from source.
  5. Sign in to Claude Code and/or Codex on each machine.
  6. Put any provider API keys in a file you create, themselves.
- **Rules you follow throughout.** Machines share state only through git; never `scp` or `rsync` config between them. The agents' login on the VPS has no sudo, and neither do you: when a step needs root, show the person the exact command and wait. Never open or print key files, `.env` files, `~/.ssh` private keys or harness credential files.

Which machines? Ask: "Which Mac, and which Linux boxes (usually one rented VPS)? Do you use Tailscale, or are you willing to? (It is free for personal use and it is how the boxes reach each other without opening ports.)" This guide assumes one Mac and one VPS; for more boxes repeat sections 4 and 5 for each, with one more `[[machines]]` entry apiece.

## 1. Check the machines

**On the Mac** (Apple silicon):

```sh
sw_vers -productVersion        # any current macOS
uname -m                       # arm64
git --version                  # if missing: xcode-select --install
python3 --version              # must be 3.11 or newer
```

For the `skills` module (it builds the `skillherd` tool from source) the Mac also needs Rust and a C linker. The linker comes with the Xcode command line tools (`xcode-select --install`, the same step as for git). Rust comes from rustup: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y`, then `. ~/.cargo/env` or open a new shell, and check `cargo --version`. Skip both if the person will not use `skills`.

The Python that ships with macOS is too old. If `python3 --version` says less than 3.11: `brew install python` (install Homebrew first from https://brew.sh if `brew` is missing; ask the person to approve that), open a new shell, and check again. `bin/estate` refuses to run on older Python and says so.

**On the VPS** (Debian 12+ or Ubuntu 24.04+, systemd), over ssh as whatever admin login the provider gave the person:

```sh
cat /etc/os-release | head -3
git --version                  # missing on minimal images: sudo apt-get install -y git python3
python3 --version              # 3.11+ (Debian 12 and Ubuntu 24.04 ship it; minimal images omit it)
systemctl --version | head -1
```

A minimal VPS image ships neither `git` nor `python3`: have the person run `sudo apt-get install -y git python3` (as root, drop `sudo`) before section 4a. The root script in section 4 installs them too, along with `curl`, `ca-certificates` and the toolchain the optional modules need (`build-essential`, `nodejs`, `npm`), so the agents' login, which has no sudo, never has to. The `skills` module also needs Rust for that login: after section 4, install it as the agents' login (the same rustup command as above) before `estate install skills`.

**Put the repo where every machine expects it.** On the Mac, if this repo is not already at `~/Code/agent-estate`, move it or re-clone it there now (`mkdir -p ~/Code`). Installed commands, timers and shims point into this checkout, so it must not move later. Then make `estate` a command:

```sh
mkdir -p ~/.local/bin
if [ -e ~/.local/bin/estate ] || [ -L ~/.local/bin/estate ]; then
  ls -ld ~/.local/bin/estate
else
  ln -s ~/Code/agent-estate/bin/estate ~/.local/bin/estate
fi
```

If an `estate` entry already exists, inspect its target before using it.
Reuse it only if it points to this checkout. Leave another tool's entry in
place and use `~/Code/agent-estate/bin/estate` explicitly; replacing it is the
person's decision.

Make sure `~/.local/bin` is on `PATH` in the person's shell startup file and in your own session (`echo $PATH`). If it is not, add `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc` (Mac) or `~/.profile` (Linux) and also export it in the current session. Later steps, including the first nightly sync, depend on it. The rest of this guide writes plain `estate`; if the link is not in place, `~/Code/agent-estate/bin/estate` is the same command.

**Done when:** `estate --help` prints usage on the Mac.

## 2. Write estate.toml

`estate.toml` is the one file with the person's values. Every machine uses the same one; each machine finds itself in `[[machines]]`.

```sh
mkdir -p ~/.config/agent-estate
if [ -e ~/.config/agent-estate/estate.toml ] || [ -L ~/.config/agent-estate/estate.toml ]; then
  printf '%s\n' 'Existing estate.toml: preserve it and merge settings below.'
else
  cp ~/Code/agent-estate/estate.example.toml ~/.config/agent-estate/estate.toml
fi
```

Edit it with the values below. Preserve existing values and merge only the
settings this installation needs; the example is a starting point, not a
replacement for a configured file. Read what you can off the machine; ask for
the rest.

| Setting | Where the value comes from |
|---|---|
| `label_prefix` | Ask for a domain they own, written backwards (`com.theirdomain.estate`); if they have none, `local.<their-username>.estate` is fine. Used only to name timers and launch agents. |
| `tailnet` | Their Tailscale MagicDNS suffix (`something.ts.net`, shown in the Tailscale admin console under DNS). Ask. `""` if they do not use Tailscale. |
| `[user] name`, `email` | Ask. Used as the git author. Read the current ones from `git config --global user.name` / `user.email` and confirm; if either is empty (common on a clean Mac and on a new VPS), ask the person, then set them with `git config --global` on that machine. |
| `[git] remote_base` | Ask where their private repos live. GitHub: `git@github.com:<their-github-username>`. Self-hosted forges are an optional field guide ([guides/self-hosted-git-forgejo.md](guides/self-hosted-git-forgejo.md)); do not set one up now. |
| `[[machines]]` | One entry per machine. `name` is short and lowercase (`mac`, `vps`); `ssh` is the alias you will define in section 4 (`vps`); `os` is `mac` or `linux`; `role` is `workstation` for the Mac, `agents` for a VPS. Keep the example's two entries and rename them if the person wants. With two or more machines of the same OS, also set `hostname` on each so `estate doctor` can tell which one it is running on. |
| `[harnesses.*]` | Keep only the harnesses the person actually signs in to: delete `[harnesses.codex]` if they do not use Codex, add `[harnesses.<name>]` for others. `usage` polls every listed harness on every machine and warns where one is not signed in. |
| `[modules.config-sync] remote` | The URL of the empty private `agent-env` repo from step 3b (GitHub: `git@github.com:<their-github-username>/agent-env.git`). Add the table `[modules.config-sync]` with `remote = "..."` once you have it, on every machine. |
| `[modules.sync] hooks` | Uncomment the `[modules.sync]` block and its `hooks = ["estate-config-sync apply --pull", "skillherd sync"]` line in the example (drop `"skillherd sync"` if `skills` is not enabled). That makes the nightly sync apply config from `agent-env` after pulling and re-render the skills pool. No question for the person. |
| `[keys] names` | Ask which provider API keys their agents use (`EXA_API_KEY`, `OPENROUTER_API_KEY`, ...). `[]` is fine. Names only; values never go in this file. |
| `[modules] enabled` | See the next table. |

**The recommended first install** is the example's own list, the same on both machines (each module runs only where it applies):

| Module | Mac | VPS | What it does | Optional? |
|---|---|---|---|---|
| `baseline` | checks Tailscale | root setup + checks | The safe VPS: separate login with no sudo, Tailscale, default-drop firewall that cannot lock you out, security updates, optional backups. | Required on a VPS; on a Mac it only checks Tailscale. |
| `sync` | yes | yes | Nightly: pull the repos you list through git, then run hooks. | Core. |
| `config-sync` | yes | yes | Rules, hooks and settings for every harness, from one private git repo. | Core. |
| `keys` | yes | yes | One 0600 key file; keys are injected only into tools you name. | Core. |
| `usage` | yes | yes | Claude and Codex rate-limit usage in one snapshot (`usage-show`). | Drop it if no one uses Claude or Codex subscriptions. |
| `guardrails` | yes | yes | `testrun` for heavy commands, the shell-footgun hook, optional compile slots. | Core. |
| `health` | yes | yes | Hourly read-only report of disk, memory, failed units, doctor, runaway processes. | Core. |
| `cleanup` | yes | yes | Six-hourly age-gated sweep of old worktrees, build caches and logs. | Optional; recommended. |
| `tmp-cleanup` | no-op | yes | Ages out `/tmp` scratch. | Optional; recommended on a VPS. |
| `show` | skipped | yes | Publish a file or dev port as a tailnet-only link with a time limit. | Needs Tailscale and `tailnet` set; delete it from the list if not. |
| `post` | yes | yes | Agent-to-agent mail between sessions and machines: installs the `post` tool and its mail hooks for each harness you listed. | Optional; recommended when more than one agent runs. Needs Node.js for the hooks. |
| `skills` | yes | yes | One skills pool: seeded with a starter set, rendered into Claude Code and Codex by the `skillherd` tool. | Optional. Builds the `skillherd` tool from source: needs Rust and a C linker. |

Settings you are likely to change are shown commented out under `[modules.<name>]` in the example; the two this first install needs are the `sync` hook and the `config-sync` remote, above.

If the person does not use Tailscale: uncomment `[modules.baseline]` in the example and set `tailscale = false` and `public_ssh = true` (otherwise the firewall would admit nothing), remove `show` from `enabled`, and leave `tailnet = ""`. Section 4 has a "Without Tailscale" part: its steps differ. Say plainly that public SSH on a password-less key-only login is acceptable but Tailscale is better.

Check it:

```sh
estate config check            # prints ok: <path>
```

Fix every line it prints and run it again until it says `ok`.

**Known limit:** the timers and launch agents the modules install read the config at its default path, `~/.config/agent-estate/estate.toml`. A non-default `ESTATE_CONFIG` is not carried into them, so keep the file at the default path on every machine.

**Done when:** `estate config check` prints `ok:` and `estate list` shows each module you chose as `enabled`.

## 3. Connect the machines

**3a. Tailscale on the Mac.** Ask the person to install it from https://tailscale.com/download/mac (or `brew install --cask tailscale`), open it and log in. Check:

```sh
tailscale ip -4 || /Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4   # prints a 100.x.y.z address
```

The `baseline` row of `estate doctor` on the Mac is green when this works.

**3b. The git remote for the person's config.** Ask the person to create **one empty private repository named `agent-env`** in the account `remote_base` points at (GitHub: github.com/new, private, no README). Nothing in it yet. Put its URL in `estate.toml` as `[modules.config-sync] remote` (section 2) on the Mac now. Tell them this repo will hold their agent configuration, so it stays private. If the GitHub CLI is installed and signed in (`gh auth status`) you may create it for them with `gh repo create <their-username>/agent-env --private` after they say yes.

**3c. Git can push and pull on the Mac.** Check `ssh -T git@github.com` (it greets by username, then closes). If it fails, ask the person to add an SSH key to their GitHub account (`ssh-keygen -t ed25519` if they have none, then Settings → SSH keys); or use an HTTPS remote with their credential helper, setting `remote_base` to `https://github.com/<their-username>` instead.

**3d. Reach the VPS.** Ask: "What is the VPS's address, and the admin login your provider gave you (often `root`, `ubuntu` or `debian`)? Can you ssh in with `ssh <admin>@<address>`?" Confirm it works from the Mac with `ssh <admin>@<address> true`. You will make the permanent `vps` alias in section 4, after the agents' login exists.

**Done when:** the Mac has Tailscale up, the empty `agent-env` repo exists, and you can ssh to the VPS.

## 4. Set up the Linux box

The `baseline` module does this. It has a root half (the person runs it, with sudo) and a check half (`estate doctor`, no root). Background: [modules/baseline/README.md](modules/baseline/README.md). Do these in order, from the Mac, over ssh as the admin login.

**4a. Get the repo onto the VPS** as the admin, long enough to run the root script. Use the same URL the Mac checkout came from (`git -C ~/Code/agent-estate remote get-url origin`):

```sh
ssh <admin>@<address> 'git clone <repo-url> ~/agent-estate-bootstrap'
```

If that repo is private, the person must give the VPS read access (a deploy key); ask them to run the clone themselves in an ssh session instead.

**4b. Preview, then ask the person to run the root half.** The flags mirror `[modules.baseline]` in `estate.toml` (defaults shown: `agent`, `true`, `false`, `22`, `false`, `false`, `true`; the last is `--toolchain`). Show the person this and wait:

> "Please open an ssh session to the VPS as your admin login and run these two commands, then tell me what the second one printed at the end. The first only previews; the second makes the change."
>
> ```sh
> sudo bash ~/agent-estate-bootstrap/modules/baseline/root-setup.sh --agent-user agent --tailscale true --public-ssh false --ssh-port 22 --zram false --backups false --toolchain true --dry-run
> sudo bash ~/agent-estate-bootstrap/modules/baseline/root-setup.sh --agent-user agent --tailscale true --public-ssh false --ssh-port 22 --zram false --backups false --toolchain true
> ```
>
> If you log in as `root` rather than a sudo user, drop `sudo` and add `--authorized-keys ~/.ssh/authorized_keys` so the new login gets your key.

What it does: installs packages (including `git`, `python3`, and, with `--toolchain true`, `build-essential`, `nodejs` and `npm`, which the optional modules need and the agents' login cannot install), creates the `agent` login (no sudo, systemd linger on, SSH keys only, passwords off only once a key is in place), installs Tailscale, sets up security updates and time sync, and **skips the firewall** until Tailscale is connected, saying so. That skip is expected on this first pass.

> **Without Tailscale** (`tailscale = false`, `public_ssh = true`): the differences are these. The first root-setup run already loads the firewall (public SSH only) with the 90-second revert, so there is no second pass: skip 4c, and in 4e the person confirms that same first run. Nothing prints "skipped". In 4d, `HostName` is the VPS's public address or DNS name, not a tailnet name. Do not run `ssh` checks before the firewall is confirmed from a **new** connection (see 4e). The root-setup flags are `--tailscale false --public-ssh true`; its dry-run says the firewall has no Tailscale interface rule.

**4c. Tailscale login.** (Skip without Tailscale.) Ask the person to run on the VPS: `sudo tailscale up --ssh`, open the URL it prints, and approve the machine. Then, from the Mac, find the VPS's tailnet name (`tailscale status`, or the admin console) and confirm: `ssh agent@<vps-tailnet-name> true`. If that fails, stop: do not continue to the firewall.

**4d. Make the alias.** Add to `~/.ssh/config` on the Mac (append; keep what is there):

```
Host vps
  HostName <vps-tailnet-name>      # without Tailscale: the VPS's public address
  User agent
```

(If the person uses a specific key, add an `IdentityFile ~/.ssh/<key>` line.) Check: `ssh vps true` and `ssh vps 'id -nG'` (the groups must not include `sudo`). If you named the machine something other than `vps` in `estate.toml`, use that name.

**4e. Firewall, with its safety net.** The firewall closes every inbound port except what you chose. A wrong rule on a remote box would lock everyone out, so it arms a **90-second timer that deletes the rules** unless the person confirms. Ask the person to run, in the admin ssh session:

> ```sh
> sudo bash ~/agent-estate-bootstrap/modules/baseline/root-setup.sh --agent-user agent --tailscale true --public-ssh false --ssh-port 22 --zram false --backups false --toolchain true
> ```
>
> "It will print `firewall LOADED; it reverts in 90s`. As soon as it does, tell me."

(This is the same command as in 4b, run a second time after Tailscale is up; without Tailscale it was already loaded by the first run, so just confirm in a new session.) The moment they say so, open a **new** connection (an existing one survives on conntrack and proves nothing): `ssh vps true` through Tailscale, from the Mac. If it works within the 90 seconds, tell the person: "It works. Please run `sudo estate-firewall confirm`." If it does not work or time runs out, do nothing; the rules vanish on their own, you lose nothing, and you debug from the provider's web console.

**4f. Check out and configure estate for the agents' login**, now as `agent`. Over `ssh vps`:

```sh
ssh vps 'mkdir -p ~/Code ~/.config/agent-estate ~/.local/bin && git clone <repo-url> ~/Code/agent-estate'
ssh vps 'ln -sfn ~/Code/agent-estate/bin/estate ~/.local/bin/estate'
```

Non-interactive ssh does not read the login profile, so `~/.local/bin` is not on `PATH` there. In every `ssh vps '...'` command from here on, either use full paths (`~/.local/bin/estate`) or prefix `export PATH="$HOME/.local/bin:$HOME/.local/bin/estate-shims:$PATH";`. Add `export PATH="$HOME/.local/bin:$PATH"` to `~/.profile` on the VPS too, for the person's own sessions.

Write the **same** `estate.toml` on the VPS, with the same values as on the Mac: send the text on ssh's standard input with `ssh vps 'cat > ~/.config/agent-estate/estate.toml'` and a here-document. That is writing the same text once, not syncing state; do not `scp` or `rsync` files in general. Section 9 shows how to carry the file in git afterwards. Then set the git identity (the person's name and email; ask if you do not have them) and check:

```sh
ssh vps 'git config --global user.name "<name>" && git config --global user.email "<email>"'
ssh vps '~/.local/bin/estate config check'
```

Give the VPS its own way to reach git. Over `ssh vps`: `ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519` (skip if one exists), print the **public** half (`cat ~/.ssh/id_ed25519.pub`) and ask the person to add it to GitHub. Two choices to put to them: a **deploy key with write access** on `agent-env` (least privilege; a deploy key serves one repo only), or an SSH key on their account (reaches all their repos, so use a dedicated key they can revoke). Check: `ssh vps 'ssh -T git@github.com'`.

Once the VPS has its own checkout, the person can delete `~/agent-estate-bootstrap`. **Done when:** `ssh vps true` works through Tailscale; the person confirmed the firewall; `ssh vps '~/.local/bin/estate doctor'` prints `core:python`, `core:git`, `core:systemd-user`, `core:linger`, `core:config` and `core:machine` as `ok` (the module rows are not green yet; that is section 5). The `baseline` row is green after the firewall is confirmed and `tailscale ip -4` works on the VPS.

## 5. Install the core modules

Run on the Mac first, then on each Linux box (`ssh vps '~/.local/bin/estate ...'`). **First, create the key file** (only if it does not exist yet; this never touches an existing one) so the `keys` row can go green:

```sh
f="$(estate config get keys.file)"; [ -e "$f" ] || install -m 600 /dev/null "$f"
```

Then preview and install everything enabled:

```sh
estate install --dry-run       # what would change; changes nothing
estate install                 # installs each enabled module, dependencies first
```

`estate install` is idempotent: run it again any time. It stops at the first failure and says which module; fix that and run it again. Then work through the modules below, in this order, doing what each asks. After each, `estate doctor` (section 7) shows its row.

**config-sync** — with `remote` set, it clones the empty `agent-env` repo to `~/Code/agent-env`, fills it from a starter (rules for Claude and Codex, the shell doctrine pack, base settings, and the shell-footgun hook wired into both harnesses), makes one commit, and installs it into `~/.claude` and `~/.codex`. If it says it cannot clone, the repo does not exist yet or git access is not working (section 3). **On the Mac, publish the starter once:**

```sh
git -C ~/Code/agent-env push -u origin HEAD:main
```

Tell the person what is in it, and that `home/doctrine/house-register.md` has blanks under "About me" which they should fill in (it shapes every reply they get) and `home/.codex/config.base.toml` sets Codex's `approval_policy` and `sandbox_mode`, which they should read and set to the posture they want before relying on it.

*Existing rules files.* If the person already had `~/.claude/CLAUDE.md` or `~/.codex/AGENTS.md`, the first install **keeps theirs** and leaves a warning, `local-edit  .claude/CLAUDE.md ...`, and the `config-sync` row warns until you resolve it. Choose with the person: to keep their version as the shared one, adopt it into the repo, commit and push; to take the starter's version instead, delete the local file and run `estate-config-sync apply`.

```sh
estate-config-sync --harvest ~/.claude/CLAUDE.md      # also ~/.codex/AGENTS.md if it warned
git -C ~/Code/agent-env add -A && git -C ~/Code/agent-env commit -m "adopt existing rules" && git -C ~/Code/agent-env push
```

*The hook.* The footgun hook (from `guardrails`) is merged into `~/.claude/settings.json` and `~/.codex/hooks.json` by config-sync, per command, so the person's own hooks stay. Codex ignores an unreviewed hook: ask the person to start Codex once, open `/hooks` and trust it.

*On the VPS* the same `remote` makes install clone what the Mac pushed (so push from the Mac first). Done when the `config-sync` row says the managed files match.

**sync** — the nightly job: for each repo in `~/.config/agent-estate/sync-repos.tsv` (one per line, `name`, tab, `path` or `-`, tab, optional install command) it clones if missing, otherwise fast-forwards, then runs `hooks`. Ask the person which repos should be on every machine and add them. The nightly hook that applies config (`hooks = ["estate-config-sync apply --pull"]` under `[modules.sync]`, set in section 2) runs after the repo table. Run `estate install sync` again if you change `hour`/`minute`. Run the first sync by hand so the row can turn green: `estate-sync`. It prints each repo and hook and `== done: ok`. Done when the `sync` row says "daily at 04:00; last sync Nh ago".

**keys** — shims that scrub provider keys from the environment and inject only the ones a tool is mapped to. Ask the person for the key values, but do **not** take them in chat: tell them "Please put the keys in `<keys.file path>` yourself, one `NAME=value` per line, no quotes and no `export`, and tell me when done." Then (still without reading it) `estate doctor` checks names, mode and ownership. If tools should receive keys, add them under `[modules.keys.tools]` (see the example) and run `estate install keys`. Add the shim directory first on `PATH` in the environment each harness is started from:

```sh
export PATH="$HOME/.local/bin/estate-shims:$PATH"       # before ~/.local/bin; shell startup file on each machine
```

To send the same key file to the VPS without copying it by hand: `~/.local/bin/estate-shims/estate-keys push vps` (needs `ssh vps` to work and the VPS checkout at `~/Code/agent-estate`). Done when the `keys` row says `key file and shims current`. A `warn: add: export PATH=...` means the shim directory is not first on `PATH` in the shell running doctor.

**usage** — polls Claude and Codex rate-limit usage every 10 minutes. It needs each listed harness **signed in on that machine**, which is the person's step: Claude Code — start `claude` and follow its login; Codex — `codex login` (on a headless box `codex login --device-auth`, or see `codex login --help`). Ask them to do this on the Mac and on the VPS. `usage` reads subscription logins; a harness used only with an API key has none, so remove it from `[harnesses.*]`. Check `usage-show`. Done when the `usage` row is ok (every account `ok`). Leave `refresh_login = false` unless the person rarely uses Claude Code on a box; see the example.

**guardrails** — installs `testrun`, `footgun-hook` and the test slice (Linux). Agents run tests, gates and builds as `testrun <repo> <kind> -- <command...>`; the hook, wired by config-sync above, refuses unwrapped heavy commands and the common shell footguns. Rust users: set `compile_slots = true` under `[modules.guardrails]`, re-run `estate install guardrails`, and follow [modules/guardrails/README.md](modules/guardrails/README.md) for the `~/.cargo/config.toml` line. Hands-on check: `testrun demo unit -- sh -c 'ps -o ni= -p $$'` prints 19 on a Mac, and `echo '{"tool_name":"Bash","tool_input":{"command":"pkill -f x"}}' | footgun-hook` prints a refusal. Done when the `guardrails` row is ok, which includes the hook being in each harness's settings.

**health, cleanup, tmp-cleanup** — nothing to ask. `estate install` starts the jobs and takes a first report. Done when each row is ok. Read the report with `estate-health`; preview the cleanup with `estate-cleanup run --dry-run`. The optional triage skill for the health report is `modules/health/skill/estate-health/`: the `skills` module adds it to the pool it seeds, so an agent can read the report each morning.

**show** (VPS) — publishes a file, directory or local dev port on the tailnet with a time limit. One thing needs an admin, once: ask the person to run on the VPS `sudo tailscale set --operator=agent` (their agents' login name), and to enable MagicDNS and HTTPS certificates in the Tailscale admin console. Try it: `estate-show report.html --ttl 2h` prints a tailnet URL. Done when the `show` row is ok.

**baseline** (VPS) — `estate install baseline` as the agents' login prints the exact root command with the current settings if anything is out of date, and installs the backup timers if `backups = true`. To turn backups on: set `backups = true` and `backup_repo` under `[modules.baseline]`, put `RESTIC_PASSWORD` and the repository's access keys in the key file (the person writes the password down somewhere else too), then rerun `estate install baseline` and the root command it prints. Changing `public_ssh`/`ssh_port` also needs the root command run again.

**post** — agent-to-agent mail. The module clones the `post` tool to `~/Code/post`, installs the binary (the release if one exists for the platform, else `cargo install --locked` from the checkout, which needs Rust), runs `post doctor --fix --brief`, and installs the mail hook for each harness in `[harnesses.*]` (Claude Code, Codex, Pi, Cursor, Grok) with post's own installers, which keep the person's other hooks. The hooks need Node.js; without it the module says so and mail still works from the command line. Codex asks the person to approve the hook once: start `codex`, open `/hooks`. It also adds a row for the checkout to the sync repo table, so the tool updates nightly. Nothing to ask for local mail. Try it: `post doctor`, and the two-terminal demo in `~/Code/post/README.md`. **The cross-machine bridge is off.** Turn it on only if the person wants agents on the Mac and the VPS to mail each other; it needs a **private** git repo as the relay with one restricted SSH key per machine, which the person provisions (follow [modules/post/README.md](modules/post/README.md), "The bridge"), then `bridge = true` and `relay_url = "..."` under `[modules.post]` on every machine and `estate install post`. Done when the `post` row is ok: `post` on `PATH`, `post doctor` clean, the hook present for each listed harness.

**skills** — one skills pool. **It builds the `skillherd` tool from source**, so the machine needs `cargo` (Rust, from rustup) and a C linker first: on the Mac, rustup and the Xcode command line tools (section 1); on the VPS, rustup for the agents' login plus `build-essential`, which root-setup installs (`--toolchain true`). Without them install stops with "cargo is not available". The module clones [skillherd](https://github.com/treygoff24/skillherd) to `~/Code/skillherd` (if the person already has a clone, set `checkout` under `[modules.skills]` to that folder), installs it with the tool's own `install.sh --prefix ~/.local`, and writes `~/.config/skillherd/config.json` pointing at the pool. skillherd serves Claude Code skills into `~/.claude/skills` unless `CLAUDE_SHARED` or `CLAUDE_CONFIG_DIR` is set, so run the install from a shell with the same environment the person's agents get. The pool is `paths.skills` (default `~/.agents/skill-library`; if you point it at the tool's own output folder `~/.agents/skills`, install uses `~/.agents/skill-library` instead and says so). A **new, empty** pool is seeded once with this repo's 34 starter skills plus the `estate-health` triage skill (copied, never linked), switched on, and rendered into the harnesses; an existing pool is never touched. To use the person's own skills repo as the pool, set `pool_remote` and the tool clones it. Add `"skillherd sync"` to the `[modules.sync] hooks` list (section 2) so the nightly sync pulls and re-renders; the `skills` row warns until you do. Seeding also lists every seeded skill in the pool's `.globals/house` file, which is how the tool knows they are ours; without that line `skillherd doctor` warns `unknown_provenance`. Done when the `skills` row is ok: `skillherd` on `PATH`, the pool exists, `skillherd doctor` clean. On a machine set up when the tool was called skill-cli (command `skill`), re-running the install moves it over; [modules/skills/README.md](modules/skills/README.md#moving-from-skill-cli) lists the config edits left to you. Edit skills in the pool, never in a harness's folder.

**Done when:** `estate install` exits 0 on every machine and nothing in it printed an `error`.

## 6. Your harnesses

config-sync installs into the default directories:

| Harness | Rules | Settings and hooks | Notes |
|---|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md`, `~/.claude/rules/*.md` | `~/.claude/settings.json` (hooks, permissions) | Account-specific `CLAUDE_CONFIG_DIR` directories are not managed. |
| Codex | `~/.codex/AGENTS.md` | `~/.codex/config.toml`, `~/.codex/hooks.json` | Trust the hook once (`/hooks`). |
| Pi and others | add a `file` row to `agent-env/manifest.tsv` for the harness's global instructions file (for Pi, `AGENTS.md`; check its docs for the path) | no hook support assumed | `testrun` and the doctrine pack still apply: tell the agent to read the rules and use `testrun`. |

To add a file to every machine, put it in the `agent-env` checkout, add a row to `manifest.tsv` (`kind`, `source`, `dest`, tab-separated; see [modules/config-sync/README.md](modules/config-sync/README.md)), commit and push; the nightly sync applies it. Extra accounts of one harness (listed under `accounts` in `estate.toml`, for usage) are polled but their config directories are yours to link to the shared files; [guides/many-subscriptions.md](guides/many-subscriptions.md) covers rotating several logins.

**Done when:** in a new Claude Code or Codex session the person sees the shared rules, and a deliberately bad command (`pkill -f anything`) is refused by the hook.

## 7. Verify

```sh
estate doctor                  # a table; exit 0 ok, 2 warn, 1 fail
estate doctor --json           # the same rows for a script
```

Run it on the Mac, then `ssh vps '~/.local/bin/estate doctor'`. Under any row that is not ok it prints `done when: ...`; act on that line. Repeat until both exit 0. The common red rows:

| Row | What it says | Fix |
|---|---|---|
| `core:python` | python 3.9.x | Install Python 3.11+ (`brew install python`) and make it first on `PATH`. |
| `core:systemd-user` | unreachable / offline | The agents' login has no user manager running. Log in over ssh (not `su`); an admin runs `sudo loginctl enable-linger agent`. |
| `core:linger` | linger off | An admin runs `sudo loginctl enable-linger agent`, or re-runs the baseline root command. |
| `core:config` | a validation message | Run `estate config check`, fix each line. |
| `core:machine` | cannot tell which machine this is | Set `hostname` on this machine's `[[machines]]` entry, or `export ESTATE_MACHINE=<name>`. |
| `baseline` (VPS) | login, SSH, updates, firewall or time sync "missing" / "does not exist" / "not key-only" | Run the root command `estate install baseline` prints, as admin; it is idempotent. |
| `baseline` | Tailscale installed but not connected | The person runs `sudo tailscale up --ssh` (VPS) or opens the app and logs in (Mac). |
| `baseline` | a firewall change is applied but not confirmed | After a fresh ssh works, the person runs `sudo estate-firewall confirm`. |
| `baseline` | firewall ruleset missing or differs from the config | Bring Tailscale up first, then run the root command again; confirm in a fresh ssh session. |
| `sync` | no sync has run yet | Run `estate-sync` once. |
| `sync` | last sync failed: `<hook>` | Run `estate-sync` and read it. Usually `command not found` (put `~/.local/bin` on `PATH`) or a repo that cannot be cloned (git access). |
| `sync` | repos skipped | Commit, push or merge that checkout by hand; the next run clears it. |
| `config-sync` | checkout missing / never applied | `estate install config-sync`. |
| `config-sync` | N local edit(s) not in the repo | `estate-config-sync --harvest <path>`, then commit and push the agent-env repo. |
| `config-sync` | changes waiting / uncommitted changes | `estate-config-sync apply`; commit and push the agent-env checkout. |
| `keys` | `keys operation failed` | Check the configured path, ownership and mode without printing the contents. If missing, have the person create it privately with mode 0600. If it exists, preserve its contents: correct the permissions or ownership, then have the person fill only missing values. Never recreate an existing key file from `/dev/null`. |
| `keys` | `add: export PATH=...` | Put the shim directory before `~/.local/bin` on `PATH` for the shell that runs doctor and for each harness. |
| `usage` | `no_login` | Sign in to that harness on this machine, or remove it from `[harnesses.*]`. |
| `usage` | `expired` | Use that harness once on this machine so it refreshes, or set `refresh_login = true` (Claude file logins only). |
| `guardrails` | footgun hook is not in the settings of: ... | Run `estate-config-sync apply` (it merges the hook), or merge `modules/guardrails/settings/*.json` by hand. |
| `guardrails` | out of date with the repo | `estate install guardrails` after pulling. |
| `health`, `cleanup` | N minutes old: the job is not running | Check the job (`systemctl --user status <label>-health.timer` / `launchctl list` and look for your `label_prefix`); `estate install <module>`; on Linux check linger. |
| `health`, `cleanup` | no report yet | Run `estate-health` / `estate-cleanup run` once. |
| `show` | tailnet empty / Tailscale not running | Set `tailnet` in `estate.toml`; `sudo tailscale up --ssh`. |
| `tmp-cleanup`, any timer module | timer not enabled or not active | `estate install <module>`; if the user manager is down, see `core:systemd-user`. |
| `post` | post is not on PATH | `estate install post` (needs `git`, and `cargo` if no release binary exists); put `~/.local/bin` on `PATH`. |
| `post` | mail hook is not installed for: ... | Install Node.js, then `estate install post`. |
| `post` | post doctor has findings | `post doctor`, then `post doctor --fix --brief`. |
| `skills` | cargo is not available | Install Rust with rustup as this user, plus a C linker (Mac: `xcode-select --install`; VPS: root runs `apt-get install -y build-essential`). Re-run `estate install skills`. |
| `skills` | cannot clone ... | Check the network and `[modules.skills] repo_url`; or clone https://github.com/treygoff24/skillherd yourself and set `[modules.skills] checkout` to it. |
| `skills` | the nightly sync does not render the pool | Add `"skillherd sync"` to `[modules.sync] hooks`. |
| `skills` | the nightly sync still runs "skill sync" | Replace `"skill sync"` with `"skillherd sync"` in `[modules.sync] hooks`: the tool was renamed. |

Any row can also say `does not match estate.toml (run: estate install <module>)` after you edit the config; do that and re-check.

**Done when:** `estate doctor` prints `doctor: ok` and exits 0 on the Mac and on every Linux box. Tell the person which machines you verified.

## 8. Optional: add-ons and field guides

- **Add-ons** ([addons/README.md](addons/README.md)): standalone public tools (cited research, search, voice, delegating a task to a second model). Each is its own install; suggest them only when the person asks for the capability.
- **Field guides** ([guides/](guides/)): long guides for heavy optional machinery. Do not start one unprompted. Offer what fits what they said:
  - many agents building at once, a full disk, or a laggy Mac — [many-agents-compiling.md](guides/many-agents-compiling.md), [disk-hygiene.md](guides/disk-hygiene.md)
  - several Claude/Codex logins — [many-subscriptions.md](guides/many-subscriptions.md)
  - a self-hosted git server — [self-hosted-git-forgejo.md](guides/self-hosted-git-forgejo.md)
  - one container per person or project, an egress policy, a key broker — [agent-cells-incus.md](guides/agent-cells-incus.md), [egress-control.md](guides/egress-control.md), [credential-broker.md](guides/credential-broker.md)
  - watching and steering agents on every machine from one terminal window — [herdr-many-machines.md](guides/herdr-many-machines.md)
  - an unattended morning check — [morning-maintainer-agent.md](guides/morning-maintainer-agent.md)
  - the rest are listed in the `guides/` folder.

## 9. Keeping it running

- **Nightly.** At 04:00 local `sync` pulls the repos you listed and runs the hooks, including `estate-config-sync apply --pull`, so a change committed to `agent-env` from any machine reaches the others by morning. To apply right now: `estate-config-sync apply --pull`. A Mac asleep at 04:00 runs it on wake.
- **Updating agent-estate itself.** `git -C ~/Code/agent-estate pull --ff-only && estate install` on each machine (idempotent; it refreshes installed commands and units). `estate doctor` will report `out of date with the repo` for anything you forgot.
- **Reading health.** `estate-health` prints the latest report (exit 0 ok, 1 warn, 2 crit); `estate-health ack --by <name>` marks it triaged so the next report shows only what is new. `estate-cleanup run --dry-run` shows what the sweep would delete; nothing here ever kills a process.
- **Carry `estate.toml` in git (optional).** So a new machine can start from the same file: copy it into the agent-env checkout, add a row, and let config-sync own it:

  ```sh
  mkdir -p ~/Code/agent-env/estate
  cp ~/.config/agent-estate/estate.toml ~/Code/agent-env/estate/estate.toml
  printf 'file\testate/estate.toml\t.config/agent-estate/estate.toml\n' >> ~/Code/agent-env/manifest.tsv
  estate-config-sync apply
  git -C ~/Code/agent-env add estate/estate.toml manifest.tsv
  git -C ~/Code/agent-env diff --cached --stat
  git -C ~/Code/agent-env commit -m "carry estate.toml" -- estate/estate.toml manifest.tsv
  git -C ~/Code/agent-env push
  ```

  On a new machine: clone `agent-env`, copy `estate/estate.toml` from it to `~/.config/agent-estate/estate.toml`, and continue from section 4.
- **A new machine.** Add a `[[machines]]` entry to `estate.toml`, then sections 1, 4 and 5 on it. On Linux the root step is the same command.
- **Uninstalling.** `estate uninstall <module>` removes that module's timers and links and leaves your data: `config-sync` leaves the checkout and installed files, `baseline` removes only the backup timers (the firewall and SSH policy stay, because removing them blindly is how people lock themselves out; the baseline README says how to remove them by hand), `health` and `cleanup` keep their reports. `post` and `skills` have no uninstall: they install standalone tools (binaries in `~/.local/bin`, checkouts under `~/Code`, the mail store `~/.claude-mail`, the pool); remove those by hand if you want them gone, and the bridge timer with `systemctl --user disable --now post-bridge.timer` (Linux) or `launchctl bootout gui/$(id -u)/org.post.bridge` (Mac).
