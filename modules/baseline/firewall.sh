#!/usr/bin/env bash
# The estate's host firewall: render, apply with a dead-man revert, confirm.
#
#   firewall.sh render  [flags]   print the nftables ruleset (no root, changes nothing)
#   firewall.sh apply   [flags]   load it, then arm a revert that deletes it after
#                                 90 s unless `confirm` runs first (root)
#   firewall.sh confirm           disarm the revert; persist the ruleset to
#                                 /etc/nftables.conf and enable it at boot (root)
#   firewall.sh revert            what the timer runs: delete the ruleset if unconfirmed
#
# Flags: --public-ssh true|false  --ssh-port N  --tailscale-iface NAME ("" for none)
#        --dead-man-seconds N
#
# Why the dead-man: a wrong rule on a remote box locks the person out. After
# `apply`, open a FRESH ssh connection; only if it works run `confirm`.
# BASELINE_ROOT prefixes every system path (tests only).
set -euo pipefail

R="${BASELINE_ROOT:-}"
ETC="$R/etc/agent-estate"
PENDING="$R/run/agent-estate-nft-pending"
INSTALLED="$R/usr/local/sbin/estate-firewall"
UNIT="estate-nft-revert"

die() { printf 'firewall: %s\n' "$*" >&2; exit 1; }
need_root() { [ -n "$R" ] || [ "$(id -u)" = 0 ] || die "run as root (sudo)"; }

cmd="${1:-}"; [ $# -eq 0 ] || shift
public_ssh=false ssh_port=22 iface=tailscale0 delay=90
while [ $# -gt 0 ]; do
  case "$1" in
    --public-ssh) public_ssh="${2:-}"; shift 2 ;;
    --ssh-port) ssh_port="${2:-}"; shift 2 ;;
    --tailscale-iface) iface="${2-}"; shift 2 ;;
    --dead-man-seconds) delay="${2:-}"; shift 2 ;;
    *) die "unknown flag: $1" ;;
  esac
done
case "$public_ssh" in true|false) ;; *) die "--public-ssh must be true or false" ;; esac
[[ "$ssh_port" =~ ^[0-9]+$ ]] && [ "$ssh_port" -ge 1 ] && [ "$ssh_port" -le 65535 ] || die "bad --ssh-port"
[[ "$iface" =~ ^[A-Za-z0-9_.-]*$ ]] || die "bad --tailscale-iface"
[[ "$delay" =~ ^[0-9]+$ ]] || die "bad --dead-man-seconds"

render() {
  cat <<RULES
# agent-estate baseline: host ingress policy. Default-drop; admitted:
# loopback, established traffic, ICMP, DHCP, Tailscale's direct-path UDP,
# the tailnet interface, and SSH from anywhere only if public_ssh is set.
# Our own table, so other tools' tables (container managers) are left alone.
table inet estate
delete table inet estate

table inet estate {
  chain input {
    type filter hook input priority 0; policy drop;

    iif lo accept
    ct state established,related accept
    ct state invalid drop
RULES
  if [ -n "$iface" ]; then
    printf '\n    iifname "%s" accept\n' "$iface"
  fi
  cat <<'RULES'

    icmp type echo-request accept
    icmpv6 type { echo-request, nd-neighbor-solicit, nd-neighbor-advert, nd-router-advert, mld-listener-query } accept
    udp dport 41641 accept
    udp dport 68 accept
RULES
  if [ "$public_ssh" = true ]; then
    printf '\n    tcp dport %s accept\n' "$ssh_port"
  fi
  printf '  }\n}\n'
}

# ---- the pending-apply marker -------------------------------------------------
# `apply` writes $PENDING (on /run, so a reboot clears it) holding the deadline and a hash of
# `nft list table inet estate` as loaded. `revert` removes it. `confirm` persists only while the
# marker is there, unexpired, and the table loaded right now still hashes the same: a confirm that
# arrives after the dead-man fired (or while it is firing) must not save rules that were rejected.
LOCK="$R/run/agent-estate-nft.lock"
NEW="$ETC/nftables.conf.new"

now() { echo "${BASELINE_NOW:-$(date +%s)}"; }
digest() { if command -v sha256sum >/dev/null 2>&1; then sha256sum; else shasum -a 256; fi | cut -d' ' -f1; }
loaded_hash() { local out; out="$(nft list table inet estate 2>/dev/null)" || return 0; printf '%s\n' "$out" | digest; }
marker() { sed -n "s/^$1=//p" "$PENDING" 2>/dev/null | head -n 1; }
lock() {
  command -v flock >/dev/null 2>&1 || die "flock is required (util-linux)"
  mkdir -p "$(dirname "$LOCK")"
  exec 9>"$LOCK"
  flock -w 30 9 || die "another firewall apply, confirm or revert is running; wait and try again"
}
stale() {
  die "$1. The rules were not saved. Run apply again, open a FRESH ssh connection, and only then run confirm."
}

case "$cmd" in
  render) render ;;
  apply)
    need_root
    lock
    mkdir -p "$ETC" "$(dirname "$PENDING")" "$(dirname "$INSTALLED")"
    rm -f "$PENDING"
    render > "$NEW"
    nft -c -f "$NEW" || die "ruleset failed the syntax check; nothing loaded"
    install -m 0755 "${BASH_SOURCE[0]}" "$INSTALLED"
    systemctl stop "$UNIT.timer" 2>/dev/null || true
    if ! nft -f "$NEW"; then
      die "load failed"
    fi
    {
      echo "deadline=$(( $(now) + delay ))"
      echo "ruleset=$(loaded_hash)"
    } > "$PENDING"
    if ! systemd-run --on-active="${delay}s" --unit="$UNIT" "$INSTALLED" revert >/dev/null 2>&1; then
      nft delete table inet estate 2>/dev/null || true
      rm -f "$PENDING" "$NEW"
      die "could not arm the ${delay}s revert, so the ruleset was removed again"
    fi
    echo "firewall LOADED; it reverts in ${delay}s unless confirmed."
    echo "Open a FRESH ssh connection now. If it works, run: sudo estate-firewall confirm"
    ;;
  confirm)
    need_root
    lock
    [ -f "$PENDING" ] || stale "nothing is waiting for confirmation (never applied, already confirmed, or the dead-man revert already removed the rules)"
    deadline="$(marker deadline)"; want="$(marker ruleset)"
    [[ "$deadline" =~ ^[0-9]+$ ]] && [ -n "$want" ] || stale "the pending marker is unreadable"
    [ "$(now)" -le "$deadline" ] || stale "the dead-man deadline passed (the revert is due or has run)"
    [ -f "$NEW" ] || stale "the pending ruleset file is gone"
    have="$(loaded_hash)"
    [ -n "$have" ] && [ "$have" = "$want" ] \
      || stale "the loaded inet estate table is not the ruleset that was applied (it was reverted or changed)"
    install -m 0644 "$NEW" "$R/etc/nftables.conf"
    systemctl stop "$UNIT.timer" 2>/dev/null || true
    rm -f "$PENDING" "$NEW"
    systemctl enable nftables >/dev/null 2>&1 || true
    echo "confirmed: ruleset persisted to /etc/nftables.conf and enabled at boot"
    ;;
  revert)
    need_root
    lock
    if [ -f "$PENDING" ]; then
      nft delete table inet estate || true
      rm -f "$PENDING" "$NEW"
      echo "reverted: the unconfirmed firewall ruleset was removed"
    fi
    ;;
  *) die "usage: firewall.sh render|apply|confirm|revert [flags]" ;;
esac
