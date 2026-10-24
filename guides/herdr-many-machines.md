# One window for every machine's agents (Herdr)

This guide puts the agents on your Mac and on each Linux box into a single terminal window, with one combined list that shows which agent is working, which is blocked waiting for you, and which is idle. The tool is [Herdr](https://github.com/herdrdev/herdr) (docs at [herdr.dev/docs](https://herdr.dev/docs)), a third-party terminal workspace manager for coding agents. This guide only describes how to wire it into an agent-estate setup.

How it works: every machine runs a small background Herdr server that owns its terminals and agents, so they keep running when your window closes or SSH drops. Your Mac runs the Herdr client and saves each Linux box as a "machine" reached over SSH. The sidebar then shows Local plus every saved machine, each with its own workspaces, and the agent list spans all of them. A lost connection to one machine does not disconnect the others. Agents can drive Herdr too, through its CLI and socket API: spawn panes, prompt each other, wait for each other.

## Do you need this?

- **Skip it** if you run agents on one machine, or you are happy opening one SSH session and one terminal per box. Nothing else in agent-estate depends on it.
- **Do it** if you run agents on a Mac and a Linux box at once and keep hunting through terminals for the one that needs an answer. Adding the next machine is a single command.
- **Cost:** one idle Herdr server per machine and one SSH connection per saved machine from the client. Weight is low. The real cost is keeping versions close and not replacing a running server (see "What bit us").

## Prerequisites

- **SSH key login** from the Mac to each Linux box as the agent user, never root, over your private network (Tailscale, for example). Check it first: `ssh <you>@vps.example.ts.net true`. Herdr uses plain OpenSSH, so your `~/.ssh/config` host aliases work. A passphrase-protected key must be loaded with `ssh-add` before Herdr's background connections can use it.
- **Herdr installed on the Mac**, per the project README. `herdr --version` should answer. The remote install can be done by `machine add` in step 2, with your confirmation.
- **A Linux box with the agent user and systemd lingering** (the `baseline` module does this), so its Herdr server survives logout.
- Supported pairs per the docs: macOS, Linux or Windows clients connecting to Linux or macOS servers on x86_64 or aarch64.

## Steps

### 1. Check the local CLI without opening the UI

```sh
herdr --version
herdr machine list
```

Never run bare `herdr` for discovery: it attaches the terminal UI. Run it only when you want the window.

**Done when:** `herdr --version` prints a version and `herdr machine list` prints nothing (no machines yet) or your saved machines, without launching a UI.

### 2. Add each Linux box as a saved machine

In an interactive terminal, so Herdr can ask before it installs or replaces anything:

```sh
herdr machine add <you>@vps.example.ts.net --label vps
```

Setup checks the remote install and the running server, offers to install or update the remote package if needed, starts the remote server, then saves the machine. Cancelling or failing leaves nothing saved. If several sessions are already running on the box it asks which one; `--remote-session <name>` skips that question. A saved machine targets exactly one remote session. Non-interactive runs use the `default` session unless you pass the flag.

If setup offers to stop a running server to replace it, the default answer is No, and Yes ends every pane process in that server. Say No unless you mean it.

**Done when:** `herdr machine list` shows the box with its label, SSH target, session and `enabled`, and `herdr machine status` reports it `reachable` (a fresh, non-interactive check).

### 3. Open the window

Run `herdr` on the Mac. Local opens immediately; saved machines connect in the background and appear in the sidebar with their workspaces. The agent list includes every connected machine, and default rows carry a `machine` token so you can tell where each agent runs. Choose a machine or workspace in the sidebar to send your input and terminal size there. If the window is already open when you add a machine, it appears within a second without a restart.

**Done when:** an agent you started on the box (in a pane there) shows in the combined agent list from the Mac, with its working, blocked or idle state.

### 4. Add the next machine

Repeat step 2 with the new SSH target and a new label. That is the whole procedure. Manage machines with `herdr machine disable|enable|remove <id>` and `herdr machine rename <id> --label "New name"`; read the id from `herdr machine list` (`--json` is available for scripts). Removing or disabling a machine disconnects only that machine from your client. Its sessions and agents keep running, even if the host is unreachable.

**Done when:** the new machine appears in the open window and in `herdr machine status`, and removing a test machine leaves the others connected.

### 5. Recover a machine that shows `! auth` or `! error`

Other machines stay usable. Fix ordinary SSH first (`ssh <you>@vps.example.ts.net true`). Then, in a terminal, `herdr machine reconnect vps` completes SSH authentication and verifies the machine; it never installs or updates Herdr. Open clients retry failed connections within 30 seconds. For a problem that needs setup, such as a missing or incompatible remote install, run `herdr --remote <you>@vps.example.ts.net` (add `--session <name>` for a named session) and answer its prompts. Reconnects after a network drop or sleep retry on their own with growing delay, capped at two minutes.

**Done when:** `herdr machine status` reports the machine `reachable` and the sidebar badge is gone.

### 6. Let agents drive a remote machine

Workspace, tab and pane IDs and agent names are scoped to one server: two machines can both hold `w1:p1`. Choosing a machine in the UI does not retarget the CLI inside an existing pane. To act on a remote machine from a script or an agent, route by machine:

```sh
herdr --machine vps agent list
herdr --machine vps agent prompt w1:p1 "review this change"
```

The selector must be an enabled saved machine's id or exact label. It uses the saved SSH target and session directly; no open window is needed. It targets one machine per command and never falls back to Local when the machine is unavailable.

**Done when:** `herdr --machine vps agent list` returns the box's agents from a plain shell.

## What bit us

- **Replacing the binary under a live server causes a protocol outage.** In practice, swapping a Herdr binary while its server was running left the client and server unable to speak. Do instead: upgrade with `herdr update` (or `herdr update --handoff`), never by copying a new binary over the old one. `--handoff` is experimental and opt-in: it asks the old server to pass live panes to the new one so agent processes survive. In-flight requests and waits may be interrupted, so retry them. It applies only to installs managed by Herdr's own updater; Homebrew, mise and Nix installs update through their package manager, where `herdr update` is disabled. Update the remote server on its own schedule: updating a compatible client does not touch the remote server or stop its agents.
- **Keep client and server versions close.** The docs say compatible versions need not match, but saved machines additionally require newer server capabilities; an older remote server shows `! error` until you update it explicitly. Do not stop a running server only because its version differs from the client.
- **Herdr launches an agent by its bare kind if you ask it to.** `herdr agent start --kind claude` runs the bare binary. If your setup needs a launcher (an account launcher or alias), start the agent through that launcher in a pane, then name it. Check with `herdr pane process-info --pane <id>`.
- **A phone left attached shrinks tabs.** Tab geometry follows the attached client, so a phone client leaves tabs phone-sized on your desk. See [phone-access.md](phone-access.md) for the sweep that retires quiet phone transports.
- **`machine add` does not do live handoff.** If it must replace a running server, it asks first and stops that server's pane processes. Pick a moment when nothing on that box is mid-task.
- **Git over SSH inside remote panes needs forwarding.** Herdr does not turn on agent forwarding. Set `ForwardAgent yes` for the trusted host in your SSH config, or give the box its own git credentials.
- **Saved machines hold no secrets.** The catalog keeps an id, label, SSH target, session name and enabled flag. Keys stay with OpenSSH; Herdr copies no config, plugins or secrets to the box. Local keybindings and theme apply to remote machines too.
- **A wrapped agent may not be detected.** In practice Herdr recognises an agent by the name of the process it launched, so an agent started under a wrapper script or alias can show as a plain shell. The docs do not spell this rule out, so check that a wrapped agent shows a status in the list before you rely on it.

## Keeping it healthy

- After each Herdr upgrade on any machine, run `herdr --version` on each, then `herdr machine status`. All saved machines should read `reachable`.
- Update one machine at a time, remote servers deliberately, and prefer `herdr update --handoff` when agents are mid-task.
- When a box is rebuilt, its saved machine entry may need `herdr machine reconnect <label>`, or `herdr --remote <ssh-target>` if the remote install is gone.
- Remove machines you no longer use with `herdr machine remove`; this does not stop anything on them.

Last checked: 2026-10, herdr 0.9.5 on macOS and Linux; behavior taken from herdr.dev/docs (Connecting machines, CLI reference, Session state).
