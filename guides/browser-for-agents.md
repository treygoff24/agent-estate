# Giving agents a real browser

This guide gives your Linux box a browser that agents can drive, and, optionally, a path to the browser on your Mac that is already signed into your sites. It has three layers:

1. **A pinned system Chromium** on the box, with a root-owned URL policy that refuses everything except ordinary web pages, and a Python Playwright client pinned by hash. Agents use it to load pages, click, screenshot and test web apps.
2. **agent-browser**, a CLI for interactive browser work (navigate, fill, snapshot, screenshot), which runs against a browser on the same box.
3. **Aside**, a third-party remote browser service. Its CLI on the box can drive a browser that runs on your Mac, using your Mac's logged-in sessions. Your agent works in your sessions without the cookies being copied to the box.

The browser on the box is for work you can run cold. The Aside path is for work that needs your logins. No cookies, saved passwords or browser profiles are copied to the box in either case. Keep them separate in your agent instructions.

## Do you need this?

- **Skip it** if agents only need to search and read public pages (a web search tool or `curl` covers that), or if you never need agents to use a signed-in site.
- **Do layer 1** if agents must test a web app, render a page, or screenshot something on the box. It costs a few hundred MB of disk and one browser process per session, and one Chromium security update to re-pin every few weeks.
- **Do layer 3** only if you accept that an agent can act in your logged-in sessions on the Mac. It is a real capability, and it needs an explicit rule about what the agent may do with it (see "Keeping it healthy").

## Prerequisites

- A Debian 13 box, with a non-root agent user and no shared login profile. The steps pin Debian's `chromium` package. Ubuntu ships Chromium as a snap, which this pinning method does not cover, so do not follow these steps on Ubuntu without working out the snap equivalent first.
- Python 3.11+ on the box. Node is needed only for agent-browser.
- For layer 3: an Aside account, the Aside app signed in on the Mac with Remote Control turned on, and the Mac awake when the agent needs it.
- A decision, written down, on which accounts and sites agents may use through the browser.

## Steps

### 1. Install and hold a pinned Chromium

Choose one exact Debian Chromium version and write it to a file, for example `/usr/local/share/<you>/chromium-version.txt`. A pin looks like `<major>.0.<build>.<patch>-1~deb13u1`; use the version your distribution currently ships in its security channel, and pin that. Then:

```sh
PIN=$(cat /usr/local/share/<you>/chromium-version.txt)
sudo apt-get install -y "chromium=$PIN" "chromium-common=$PIN" "chromium-sandbox=$PIN"
sudo apt-mark hold chromium chromium-common chromium-sandbox
```

**Done when:** `apt-mark showhold` lists the three packages, and `chromium --version` prints the version in the pin file.

Holding stops unattended upgrades from moving Chromium under the probe. You must unhold, upgrade and re-hold deliberately (see step 5).

### 2. Install the Python Playwright client, hash-pinned

Do not use Playwright's own browser downloader. Install the client from a requirements file with hashes, into a root-owned venv that agents can read but not write:

```sh
sudo python3 -m venv /usr/local/lib/<you>-browser-venv
sudo /usr/local/lib/<you>-browser-venv/bin/pip install --require-hashes -r browser-requirements.txt
```

Pin `playwright==1.61.0` (with its `--hash` lines) in `browser-requirements.txt`, plus its small dependencies (`greenlet`, `pyee`, `typing-extensions`), each with a hash. Get the hashes from the package index and record them with the file; do not accept an unhashed install.

Launch Chromium through Playwright with `executable_path` pointing at the system binary (`/usr/bin/chromium`), never at a browser Playwright downloaded:

```python
browser = playwright.chromium.launch(executable_path="/usr/bin/chromium", headless=True)
```

**Done when:** `/usr/local/lib/<you>-browser-venv/bin/python -c "import playwright"` exits 0.

### 3. Write the root-owned URL policy

Chromium reads managed policy from `/etc/chromium/policies/managed/`. Write this file as root. It blocks every scheme except `http`, `https` and `about:blank`:

```json
{
  "URLBlocklist": [
    "*", "about:*", "blob:*", "chrome://*", "chrome://net-export", "chrome://policy",
    "chrome://settings", "cid:*", "content:*", "data:*", "devtools://*", "file://*",
    "filesystem:*", "ftp://*", "gopher://*", "javascript:*", "mailto:*",
    "view-source:*", "ws://*", "wss://*"
  ],
  "URLAllowlist": ["http://*", "https://*", "about:blank"]
}
```

Save it as `/etc/chromium/policies/managed/<you>-browser.json`, owned by root, mode 0644.

**Done when:** a probe that navigates to `file:///etc/passwd`, `data:text/html,x` and `chrome://policy` through the managed browser is refused every time, and a navigation to a local `http://127.0.0.1` fixture succeeds. Test the refusals, not just the file's presence.

### 4. Run the acceptance probe

Keep a probe directory on the box that does three things with one launch: starts Chromium with a fresh temporary profile (never a home-directory profile), connects over loopback CDP, and runs a click and a screenshot against a local fixture page. It should also run the policy refusals from step 3. Write the output as one JSON object with a schema version, and exit non-zero on any failure.

Two rules for the probe:

- It must **not** inherit the parent's environment wholesale. Pass only `HOME` and `TMPDIR` pointing at a temporary root, plus `PATH` and locale variables.
- It must refuse to start unless a root-owned file lists exactly one agent principal. For example, the launcher reads `/etc/estate/cell-principals` and refuses a missing file or one with more than one line. The reason: loopback CDP is visible to every user in the same network namespace, so a loopback port is not a boundary between users. Give each agent user its own box, or put the browser behind a mediated capability.

**Done when:** the probe prints `ok` with a screenshot file in the artifact directory, and the policy refusals are listed as blocked.

### 5. Re-probe on every Chromium change

Any change to the Chromium pin or the policy file means the probe runs again before you trust the browser. The steps for a security bump:

```sh
sudo apt-mark unhold chromium chromium-common chromium-sandbox
sudo apt-get install -y "chromium=$NEW" "chromium-common=$NEW" "chromium-sandbox=$NEW"
sudo apt-mark hold chromium chromium-common chromium-sandbox
echo "$NEW" | sudo tee /usr/local/share/<you>/chromium-version.txt
# then run the probe from step 4
```

**Done when:** the probe passes against the new version and the version file matches `chromium --version`.

### 6. Install agent-browser (interactive work)

```sh
npm install -g agent-browser
agent-browser install
```

Read its current workflow with `agent-browser skills get core`; the CLI serves docs that match its installed version, so do not copy them into your agent instructions.

Before the first command in every agent session, set a session name unique to that agent:

```sh
export AGENT_BROWSER_SESSION=<unique-name-for-this-agent>
```

Close only that session. Never `close --all`.

**Done when:** `agent-browser skills get core` prints, and a `open` to a local fixture followed by a `snapshot` lists the fixture's elements. If `agent-browser` reports that it cannot find a browser, point it at the system Chromium from step 1 (check its `install` and config options for the binary setting) rather than letting it download its own.

### 7. Connect the logged-in Mac browser through Aside (optional, layer 3)

Install the official CLI as the signed-in user, not as root:

```sh
curl -fsSL https://releases.aside.com/install.sh | bash
aside guide
```

Read `aside guide` before you do anything else. It is the authority for the CLI's current commands, and it changes between versions.

Authenticate interactively, on the box, never in an agent session and never with a password in a command line or a log. Get the account owner's explicit go-ahead before you generate a new CLI credential.

The CLI supports email and password login only when the Aside app is not local to that machine. If your account signs in with Google, the CLI instead derives a separate CLI credential from the signed-in app, and it needs no Aside password. One method: on the Mac, run the login with `ASIDE_CLI_AUTH_PATH` pointing at a new private temporary directory, so the Mac's own login is untouched; copy only that credential file to the box over SSH into a `0600` file under the agent user's home; then delete the temporary Mac copy. Do not log out of the temporary copy, because logging out revokes the token family you just copied.

Point the CLI at your Mac's host and verify:

```sh
aside host list --json        # the Mac should show online with Remote Control enabled
aside host use <mac-host-id>  # saves the default for ordinary CLI commands
```

Then do one read-only check through the remote REPL (follow `aside guide repl`): count the tabs with `listBrowserTabs()` without printing titles or URLs, open a disposable public page, read it, and close only that page. Do not touch an existing user tab.

**Done when:** `aside host list --json` shows the Mac online, and the read-only REPL check passes.

Register the MCP server if your harness uses one. It is a connection, not proof of access:

```sh
claude mcp add --scope user aside -- aside mcp --host <mac-host-id>
codex mcp add aside -- aside mcp --host <mac-host-id>
```

Set the MCP tool timeout in each harness to at least 180 seconds: Aside's remote REPL operations can run for 120 seconds, and a shorter harness timeout kills them mid-operation. Existing agent sessions may need their MCP connection reloaded or a fresh session before they see the tool.

## What bit us

- **Playwright's bundled browser ignores the managed policy.** Playwright downloads Chrome-for-Testing, and that build does not honour `/etc/chromium/policies`. Debian's system Chromium does honour it, so the probe launches the system binary. Do instead: launch the system Chromium with `executable_path` and prove the policy with refused navigations.
- **A security bump can be verified by hand instead of by the probe.** A box that lacks the probe's venv gets its bump checked by loading a loopback page and reading the CDP version. Do instead: put the probe's runtime in the base image for every box, and do not call a bump done until the probe passes on it.
- **`npx playwright install chromium-headless-shell` hung forever** after reaching 100 percent of its download, during extraction, on a recent Node. Workaround that worked: download the zip from the CDN URL the install log prints, and unzip it into the cache path it names. Better: skip Playwright's installer and use the pinned system Chromium (steps 1 and 2).
- **agent-browser's default session is shared between agents.** Another agent's `open` changed the active tab under a running agent, so a screenshot captured someone else's page. `close --all` killed another agent's live run. Do instead: set `AGENT_BROWSER_SESSION` to a unique name first, and close only your own session.
- **`agent-browser screenshot --full` wraps silently** at Chrome's 16384-pixel texture cap. On a page taller than that, the lower part of the capture repeats earlier content, with no error. Do instead: scroll and take viewport screenshots of the tail sections.
- **Screenshots freeze animations.** agent-browser captures with the page set to `visibility:hidden`, so animations stop between captures. Trigger the state you want by scrolling or hovering first, or accept the frozen frame.
- **A connected MCP server is not proof of remote browser access.** Checking the MCP server over stdio and seeing its tools listed did not show the remote browser was reachable. Only the authenticated host list did. Do instead: check `aside host list --json` and run the read-only REPL check before you count Aside as working.
- **Aside reaches the Mac only while it is online with Remote Control enabled.** When Aside calls fail, check `aside host list --json` first; it shows whether the Mac is online and Remote Control is on.
- **Logging out of a copied credential revokes the token family it came from.** Do not run logout against the temporary copy, because that revokes the family that was transferred. Do instead: delete the temporary copy without logging out.
- **Aside's remote access is not an authorization.** The capability it adds does not authorize sends, purchases, password changes, or other unrelated account actions. Write down what the agent may do (read, navigate, draft) and what it may not (send messages, make purchases, change passwords), and put that in the agent's instructions.

## Reference: what the layers look like

- `/usr/local/share/<you>/chromium-version.txt`: the one pinned version string.
- `/etc/chromium/policies/managed/<you>-browser.json`: the policy in step 3.
- `apt-mark showhold`: lists the three Chromium packages.
- `~/.local/bin/aside` (or wherever the installer puts it): the Aside CLI. Its credentials live under the agent user's home, mode 0600, and nothing else from the Mac is copied.

## Keeping it healthy

- After every Chromium security update, re-run the probe (step 5). Set a weekly reminder to check the Debian security channel.
- After an Aside CLI update, read `aside guide` again before using the CLI; then run `aside host list --json`.
- Keep the rule about what the agent may do with logged-in sessions current, and review it when you add a new site.
- Review `agent-browser` and Playwright versions when you update the Python pin. Update them together with the probe, not separately.
- Remove the Aside credential and the MCP entry from any agent user you retire.

Last checked: 2026-10, Debian 13.
