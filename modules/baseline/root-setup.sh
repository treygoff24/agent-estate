#!/usr/bin/env bash
# One-time root setup for the agent-estate baseline. The person runs it once
# with sudo; `estate install baseline` prints the exact command. Idempotent:
# a second run changes nothing. --dry-run lists every step and changes nothing.
#
#   sudo bash root-setup.sh --agent-user agent [--tailscale true] [--public-ssh false]
#        [--ssh-port 22] [--zram false] [--backups false] [--toolchain true]
#        [--authorized-keys FILE] [--dry-run]
#
# Read it before you run it. It does: packages (git, python3 and curl always; with
# --toolchain true, the default, also build-essential, nodejs and npm, which the optional
# modules need and the agents' login cannot install), the agents' login (no sudo,
# linger, SSH keys only), Tailscale from the official repo, unattended security
# updates (no auto-reboot, needrestart report-only), time sync, optional zram,
# then the firewall with a 90 s dead-man revert.
# BASELINE_ROOT prefixes every system path (tests only).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="${BASELINE_ROOT:-}"
DRY=0 AGENT_USER=agent TAILSCALE=true PUBLIC_SSH=false SSH_PORT=22 ZRAM=false BACKUPS=false TOOLCHAIN=true KEYS_FILE=""

die() { printf 'root-setup: %s\n' "$*" >&2; exit 1; }
step() { printf '== %s\n' "$*"; }
note() { printf '   %s\n' "$*"; }
act() { # act CMD...: run it, or print it under --dry-run
  if [ "$DRY" = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi
}
put() { # put SRC DEST MODE: install a file only if it differs
  if [ -f "$2" ] && cmp -s "$1" "$2"; then note "unchanged: ${2#"$R"}"; return 0; fi
  if [ "$DRY" = 1 ]; then note "would write: ${2#"$R"}"; return 0; fi
  mkdir -p "$(dirname "$2")"
  install -m "$3" "$1" "$2"
  note "wrote: ${2#"$R"}"
}
is_bool() { case "$1" in true|false) ;; *) die "$2 must be true or false" ;; esac; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    --agent-user) AGENT_USER="${2:-}"; shift 2 ;;
    --tailscale) TAILSCALE="${2:-}"; shift 2 ;;
    --public-ssh) PUBLIC_SSH="${2:-}"; shift 2 ;;
    --ssh-port) SSH_PORT="${2:-}"; shift 2 ;;
    --zram) ZRAM="${2:-}"; shift 2 ;;
    --backups) BACKUPS="${2:-}"; shift 2 ;;
    --toolchain) TOOLCHAIN="${2:-}"; shift 2 ;;
    --authorized-keys) KEYS_FILE="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,16p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done
[[ "$AGENT_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || die "--agent-user: '$AGENT_USER' is not a valid login name"
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] || die "--ssh-port must be a number"
is_bool "$TAILSCALE" --tailscale; is_bool "$PUBLIC_SSH" --public-ssh
is_bool "$ZRAM" --zram; is_bool "$BACKUPS" --backups; is_bool "$TOOLCHAIN" --toolchain
[ "$DRY" = 1 ] || [ -n "$R" ] || [ "$(id -u)" = 0 ] || die "run as root: sudo bash $0 ... (or add --dry-run to preview)"
[ "$DRY" = 1 ] || [ -n "$R" ] || [ -r /etc/os-release ] || die "this script is for Debian and Ubuntu"

SUDO_HOME=""
if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != root ]; then
  SUDO_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6 || true)"
fi
[ -n "$KEYS_FILE" ] || { [ -z "$SUDO_HOME" ] || KEYS_FILE="$SUDO_HOME/.ssh/authorized_keys"; }

[ "$DRY" = 1 ] && echo "DRY RUN: nothing will be changed."

# ---- 1. packages -----------------------------------------------------------
step "packages"
pkgs=(nftables chrony unattended-upgrades needrestart curl gnupg openssh-server git python3 ca-certificates)
# What the optional modules build and run as the agents' login, which has no sudo to install it:
# a C linker for the skills tool's Rust build, Node.js for post's harness hooks.
[ "$TOOLCHAIN" = true ] && pkgs+=(build-essential nodejs npm)
[ "$ZRAM" = true ] && pkgs+=(zram-tools)
[ "$BACKUPS" = true ] && pkgs+=(restic)
missing=()
for p in "${pkgs[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p"); done
if [ "${#missing[@]}" -gt 0 ]; then
  act env DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
else
  note "all installed: ${pkgs[*]}"
fi

# ---- 2. the agents' login --------------------------------------------------
step "agents' login: $AGENT_USER (no sudo, systemd linger, SSH keys only)"
if id "$AGENT_USER" >/dev/null 2>&1; then
  note "exists: $AGENT_USER"
else
  act adduser --disabled-password --gecos "" "$AGENT_USER"
fi
for g in sudo wheel admin; do
  if id -nG "$AGENT_USER" 2>/dev/null | tr ' ' '\n' | grep -qx "$g"; then
    act gpasswd -d "$AGENT_USER" "$g"
  fi
done
if [ -e "$R/var/lib/systemd/linger/$AGENT_USER" ]; then
  note "linger already enabled"
else
  act loginctl enable-linger "$AGENT_USER"
fi
AGENT_HOME="$(getent passwd "$AGENT_USER" | cut -d: -f6 || true)"
[ -n "$AGENT_HOME" ] || AGENT_HOME="/home/$AGENT_USER"
AK="$AGENT_HOME/.ssh/authorized_keys"
if [ -s "$R$AK" ]; then
  note "authorized_keys present for $AGENT_USER"
elif [ -n "$KEYS_FILE" ] && [ -s "$KEYS_FILE" ]; then
  if [ "$DRY" = 1 ]; then
    note "would copy the public keys in $KEYS_FILE to $AK"
  else
    install -d -m 700 -o "$AGENT_USER" -g "$AGENT_USER" "$R$AGENT_HOME/.ssh" 2>/dev/null || install -d -m 700 "$R$AGENT_HOME/.ssh"
    install -m 600 "$KEYS_FILE" "$R$AK"
    chown "$AGENT_USER:$AGENT_USER" "$R$AK" 2>/dev/null || true
    note "copied public keys from $KEYS_FILE to $AK"
  fi
else
  note "WARNING: $AGENT_USER has no authorized_keys and none could be copied (pass --authorized-keys FILE)"
fi
# Turn passwords off only when some key login exists, or this locks everyone out.
if [ -s "$R$AK" ] || { [ -n "$KEYS_FILE" ] && [ -s "$KEYS_FILE" ]; }; then
  put "$HERE/files/sshd-estate.conf" "$R/etc/ssh/sshd_config.d/00-estate.conf" 644
  if [ "$DRY" != 1 ] && [ -z "$R" ]; then
    sshd -t || { rm -f /etc/ssh/sshd_config.d/00-estate.conf; die "sshd rejected the new config; removed it"; }
    systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
  fi
else
  note "WARNING: no SSH key found anywhere; leaving password login alone so you are not locked out"
fi

# ---- 3. Tailscale ----------------------------------------------------------
if [ "$TAILSCALE" = true ]; then
  step "Tailscale (official apt repo)"
  if command -v tailscale >/dev/null 2>&1; then
    note "installed already"
  else
    # shellcheck disable=SC1091
    . "$R/etc/os-release"
    case "${ID:-}" in debian|ubuntu) ;; *) die "no Tailscale repo mapping for ${ID:-unknown}; install it by hand" ;; esac
    base="https://pkgs.tailscale.com/stable/$ID"
    act curl -fsSL "$base/${VERSION_CODENAME}.noarmor.gpg" -o "$R/usr/share/keyrings/tailscale-archive-keyring.gpg"
    act curl -fsSL "$base/${VERSION_CODENAME}.tailscale-keyring.list" -o "$R/etc/apt/sources.list.d/tailscale.list"
    act apt-get update
    act env DEBIAN_FRONTEND=noninteractive apt-get install -y tailscale
  fi
  act systemctl enable --now tailscaled
  if [ "$DRY" != 1 ] && ! tailscale ip -4 >/dev/null 2>&1; then
    note "NEXT (yours to do, it needs your login): sudo tailscale up --ssh"
  fi
fi

# ---- 4. updates and time ---------------------------------------------------
step "unattended security updates (never reboot), needrestart report-only, time sync"
put "$HERE/files/52estate-updates" "$R/etc/apt/apt.conf.d/52estate-updates" 644
put "$HERE/files/needrestart-list-only.conf" "$R/etc/needrestart/conf.d/50-estate-list-only.conf" 644
act systemctl enable --now unattended-upgrades
# Time sync can fail where the clock is not ours to set (a container without CAP_SYS_TIME):
# that must not stop the firewall step, so warn and go on.
act systemctl enable --now chrony \
  || note "WARNING: time sync (chrony) could not start (a container often cannot set the clock); continuing"

if [ "$ZRAM" = true ]; then
  step "zram swap"
  put "$HERE/files/zramswap" "$R/etc/default/zramswap" 644
  act systemctl enable --now zramswap
fi

# ---- 5. firewall -----------------------------------------------------------
step "firewall (nftables, default-drop ingress, 90 s dead-man revert)"
fw=(--public-ssh "$PUBLIC_SSH" --ssh-port "$SSH_PORT")
[ "$TAILSCALE" = true ] || fw+=(--tailscale-iface "")
want="$("$HERE/firewall.sh" render "${fw[@]}")"
if [ -f "$R/etc/nftables.conf" ] && [ "$(cat "$R/etc/nftables.conf")" = "$want" ]; then
  note "unchanged: ruleset already applied and confirmed"
elif [ "$PUBLIC_SSH" != true ] && { [ "$TAILSCALE" != true ] || { [ "$DRY" != 1 ] && ! tailscale ip -4 >/dev/null 2>&1; }; }; then
  note "NOT applied: with public SSH off and Tailscale not connected, the firewall would lock you out."
  note "Run 'sudo tailscale up --ssh', prove you can ssh in over the tailnet, then run this script again."
elif [ "$DRY" = 1 ]; then
  shown="${fw[*]}"; [ "$TAILSCALE" = true ] || shown="--public-ssh $PUBLIC_SSH --ssh-port $SSH_PORT (no Tailscale interface rule)"
  note "would run: firewall.sh apply $shown  (then you open a fresh ssh and run: sudo estate-firewall confirm)"
else
  "$HERE/firewall.sh" apply "${fw[@]}"
fi

echo
[ "$DRY" = 1 ] && echo "dry run complete; nothing changed." || echo "root-setup done. Next, as the agents' login: put the agent-estate checkout in its ~/Code, write estate.toml, run estate install, then estate doctor (INSTALL.md sections 4f and 5)"
