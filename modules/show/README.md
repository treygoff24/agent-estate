# show

Lets an agent hand you a link: publish a file, a directory or a live local dev port on this machine's tailnet address, with a time limit, and open it from your phone or laptop. Tailnet only: it uses Tailscale Serve and never turns on Funnel, so nothing is reachable from the public internet.

**Why a small script, not the Rust tool it came from.** The original is a crate with its own loopback pages daemon. For this kit the useful core is "copy it somewhere stable, tell Tailscale Serve to serve it, remember when to take it down", which is about 300 lines of standard-library Python on top of `tailscale serve` and needs no build step.

## Requirements

- Linux (a VPS is the usual place). Tailscale installed and up, with MagicDNS and HTTPS certificates enabled in the Tailscale admin console.
- `tailnet` set in `estate.toml`. `estate doctor` warns (it does not fail) if it is empty or Tailscale is not running.
- One-time, by an admin: `sudo tailscale set --operator=$USER`, so the agents' login may change Serve settings without sudo.

## Use

```sh
estate-show report.html                  # a file: copied, then published
estate-show ./dist --name preview --ttl 2h   # a built directory
estate-show 3000 --name app --ttl 8h     # a dev server already listening on 127.0.0.1:3000
estate-show ls                           # what is up, and when it expires
estate-show rm preview                   # take it down now
estate-show reap                         # take down everything past its TTL
```

Every command takes `--json` (a `{"version":1,"ok":...}` envelope; errors go to stderr) and `--dry-run` (say what would happen, change nothing). An existing path wins over the digits-mean-a-port shorthand; `estate-show publish` and `estate-show port` are the explicit forms. Exit codes: 0 ok, 2 bad input, 3 Tailscale unavailable or refused, 4 other.

- **Files and directories are copied** into `$ESTATE_STATE/show/pages/<name>/` and served at `https://<machine>.<tailnet>:8443/<name>/` (a single file appears at `.../<name>/<file>`). Editing the original does not change the link; publish again to refresh it. A directory that contains a symlink resolving outside it is refused (exit 2) so a link can never expose a private file; symlinks that stay inside the directory are kept in the copy, retargeted relative to it. Default cap 500 MB (`--max-size`).
- **A port** is mapped to its own HTTPS port in 8450-8499 and proxies to `127.0.0.1:<port>`. It does not start your server, and warns if nothing is listening.
- **Time limit:** `--ttl` takes `90m`, `24h`, `7d` (default 24h, at most 30d). Expiry is recorded in `$ESTATE_STATE/show/state.json`. A user timer runs `estate-show reap` every minute, and every command reaps first, so a link never outlives its TTL by much. If Tailscale refuses a removal, the entry is kept and retried.
- Publishing a name that exists replaces it, whatever kind it was: a port publication replaced by a page (or the reverse) is turned off in Tailscale first, and if Tailscale refuses, the old entry stays tracked and the command fails.

## Settings

```toml
[modules.show]
reap_minutes = 1   # how often the timer takes down expired links
```

## Install and done when

`estate install show` links `estate-show` into `paths.bin` and enables the reaping timer. `estate uninstall show` takes down every link, confirms none is left, and only then removes the timer and the link. If a link cannot be confirmed gone (Tailscale refuses, or the listing fails), uninstall fails, prints what is still published and leaves the timer, link and state in place so expiry keeps working; fix Tailscale and run it again. `ESTATE_SHOW_FORCE=1 estate uninstall show` removes the machinery anyway and prints the surviving links (they will no longer expire; take them down with `tailscale serve`).

Done when `estate doctor` shows `show ok`: `tailnet` is set, `tailscale status` says Running, and the timer is installed, enabled and active.
