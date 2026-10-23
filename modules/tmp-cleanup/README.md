# tmp-cleanup

Ages out agent scratch under `/tmp` so a week of test runs cannot fill the disk (or, where `/tmp` is a tmpfs, memory). On a busy agent box, stock defaults let tens of gigabytes of test scratch pile up between reboots; in practice a one-day age on files nobody has touched is safe and keeps `/tmp` bounded.

This is also the reference module: it is small on purpose and shows every part of the contract in `modules/README.md` (settings with defaults, templates, `install --dry-run`, `check`, `uninstall`, a per-platform branch).

## What it does

**Linux.** Installs two files for the agents' login, with no sudo:

- `~/.config/user-tmpfiles.d/<label>.conf`, one `systemd-tmpfiles` line: `e /tmp - - - 1d`. The `e` type cleans an existing directory and never creates it or changes its mode or owner. Running as an ordinary user, the cleaner can remove only files that login owns (`/tmp` is sticky), and it skips anything read, written or changed within the age.
- `~/.config/systemd/user/systemd-tmpfiles-clean.timer.d/<label>.conf`, a drop-in that runs the stock user `systemd-tmpfiles-clean.timer` hourly instead of daily, so the age really bounds scratch at about one day plus an hour.

Then it reloads the user manager and enables the timer. Needs the user manager to be running with linger on (`estate doctor` checks both).

**macOS.** Nothing to install: macOS manages its own temp directories. The check passes.

## Settings

In `estate.toml` (defaults shown):

```toml
[modules.tmp-cleanup]
path = "/tmp"   # directory to age
age = "1d"      # s, m, h, d or w: 12h, 1d, 2w
```

## Done when

`estate doctor` shows `tmp-cleanup ok`: both files exist and match what `estate.toml` renders to now, and the timer is enabled and active.

## Commands

```sh
estate install tmp-cleanup --dry-run   # what would change
estate install tmp-cleanup
estate uninstall tmp-cleanup           # removes the two files; leaves the stock timer enabled
```
