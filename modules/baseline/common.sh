# shellcheck shell=bash
# Shared by install, check and uninstall. Sourced after lib/estate.sh.
# R prefixes system paths: always empty outside tests.
R="${BASELINE_ROOT:-}"
LABEL="$(label)"
AGENT_USER="$(cfg modules.baseline.agent_user)"
TAILSCALE="$(cfg modules.baseline.tailscale | tr '[:upper:]' '[:lower:]')"
PUBLIC_SSH="$(cfg modules.baseline.public_ssh | tr '[:upper:]' '[:lower:]')"
SSH_PORT="$(cfg modules.baseline.ssh_port)"
ZRAM="$(cfg modules.baseline.zram | tr '[:upper:]' '[:lower:]')"
BACKUPS="$(cfg modules.baseline.backups | tr '[:upper:]' '[:lower:]')"
TOOLCHAIN="$(cfg modules.baseline.toolchain | tr '[:upper:]' '[:lower:]')"
BACKUP_REPO="$(cfg modules.baseline.backup_repo)"
BACKUP_TIME="$(cfg modules.baseline.backup_time)"
KEYS_FILE="$(cfg keys.file)"
CONF_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
UNIT_DIR="$CONF_HOME/systemd/user"
BACKUP_UNITS="restic-backup.service restic-backup.timer restic-maintain.service restic-maintain.timer"
DONE_WHEN="the agent login, Tailscale, the firewall, security updates and (if enabled) backups all verify; on the VPS run the printed root-setup command once"
export LABEL DONE_WHEN

unit_name() { echo "$LABEL-${1}"; } # restic-backup.timer -> <label>-restic-backup.timer

valid_settings() {
  local b
  for b in "$TAILSCALE" "$PUBLIC_SSH" "$ZRAM" "$BACKUPS" "$TOOLCHAIN"; do
    case "$b" in true|false) ;; *) echo "modules.baseline: tailscale, public_ssh, zram, toolchain and backups must be true or false"; return 1 ;; esac
  done
  [[ "$AGENT_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || { echo "modules.baseline.agent_user: '$AGENT_USER' is not a valid login name"; return 1; }
  [[ "$SSH_PORT" =~ ^[0-9]+$ ]] || { echo "modules.baseline.ssh_port: '$SSH_PORT' is not a port number"; return 1; }
  if [ "$BACKUPS" = true ]; then
    [ -n "$BACKUP_REPO" ] || { echo "modules.baseline.backups is true but backup_repo is empty (e.g. s3:s3.amazonaws.com/bucket, b2:bucket:path, sftp:user@host:/path)"; return 1; }
    [[ "$BACKUP_TIME" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || { echo "modules.baseline.backup_time: '$BACKUP_TIME' is not HH:MM"; return 1; }
  fi
}

FW_ARGS=(--public-ssh "$PUBLIC_SSH" --ssh-port "$SSH_PORT")
[ "$TAILSCALE" = true ] || FW_ARGS+=(--tailscale-iface "")

root_setup_command() {
  printf 'sudo bash %s/root-setup.sh --agent-user %s --tailscale %s --public-ssh %s --ssh-port %s --zram %s --backups %s --toolchain %s\n' \
    "$ESTATE_MODULE_DIR" "$AGENT_USER" "$TAILSCALE" "$PUBLIC_SSH" "$SSH_PORT" "$ZRAM" "$BACKUPS" "$TOOLCHAIN"
}

FAILS="" WARNS=""
bad() { FAILS="$FAILS$1"$'\n'; }
meh() { WARNS="$WARNS$1"$'\n'; }
same_file() { [ -f "$2" ] && cmp -s "$1" "$2"; }

# Linux: everything the root setup puts in place, verified without root.
linux_root_problems() {
  local g fixroot="re-run the root-setup command"
  if ! id "$AGENT_USER" >/dev/null 2>&1; then
    bad "agents' login '$AGENT_USER' does not exist ($fixroot)"
  else
    for g in $(id -nG "$AGENT_USER" 2>/dev/null); do
      case "$g" in sudo|wheel|admin|root) bad "'$AGENT_USER' is in group $g; agents must not have sudo ($fixroot)" ;; esac
    done
    [ -e "$R/var/lib/systemd/linger/$AGENT_USER" ] || bad "linger is off for '$AGENT_USER', so its services stop at logout ($fixroot)"
  fi
  same_file "$ESTATE_MODULE_DIR/files/sshd-estate.conf" "$R/etc/ssh/sshd_config.d/00-estate.conf" \
    || bad "SSH is not key-only: /etc/ssh/sshd_config.d/00-estate.conf missing or changed ($fixroot; it needs an authorized key first)"
  same_file "$ESTATE_MODULE_DIR/files/52estate-updates" "$R/etc/apt/apt.conf.d/52estate-updates" \
    || bad "unattended security updates are not configured ($fixroot)"
  same_file "$ESTATE_MODULE_DIR/files/needrestart-list-only.conf" "$R/etc/needrestart/conf.d/50-estate-list-only.conf" \
    || bad "needrestart is not set to report-only ($fixroot)"
  systemctl is-enabled --quiet unattended-upgrades 2>/dev/null || bad "unattended-upgrades is not enabled ($fixroot)"
  systemctl is-active --quiet chrony 2>/dev/null || bad "time sync (chrony) is not running ($fixroot)"
  if [ "$ZRAM" = true ] && ! swapon --show=NAME --noheadings 2>/dev/null | grep -q zram; then
    bad "zram swap is enabled in the config but not active ($fixroot)"
  fi
  if [ "$TAILSCALE" = true ]; then
    if ! command -v tailscale >/dev/null 2>&1; then
      bad "Tailscale is not installed ($fixroot)"
    elif ! tailscale ip -4 >/dev/null 2>&1; then
      meh "Tailscale is installed but not connected: run 'sudo tailscale up --ssh' and log in"
    fi
  fi
  if [ -e "$R/run/agent-estate-nft-pending" ]; then
    meh "a firewall change is applied but not confirmed (it reverts itself): after a fresh ssh works, run 'sudo estate-firewall confirm'"
  elif ! "$ESTATE_MODULE_DIR/firewall.sh" render "${FW_ARGS[@]}" 2>/dev/null | cmp -s - "$R/etc/nftables.conf"; then
    bad "firewall ruleset at /etc/nftables.conf is missing or differs from the config ($fixroot; apply needs Tailscale up first)"
  else
    systemctl is-enabled --quiet nftables 2>/dev/null || bad "nftables is not enabled at boot ($fixroot)"
  fi
}

backup_problems() {
  local u stamp now age
  command -v restic >/dev/null 2>&1 || bad "restic is not installed (root-setup installs it when backups = true)"
  for u in $BACKUP_UNITS; do
    same_file <(estate render "$ESTATE_MODULE_DIR/templates/$u" 2>/dev/null) "$UNIT_DIR/$(unit_name "$u")" \
      || { bad "backup unit $u is missing or differs from the config (run: estate install baseline)"; break; }
  done
  for u in restic-backup.timer restic-maintain.timer; do
    systemctl --user is-active --quiet "$(unit_name "$u")" 2>/dev/null || bad "$(unit_name "$u") is not active (run: estate install baseline)"
  done
  if [ ! -f "$KEYS_FILE" ]; then
    bad "key file $KEYS_FILE is missing; it must define RESTIC_PASSWORD and the repository's access keys"
  elif ! grep -Eq '^(export[[:space:]]+)?RESTIC_PASSWORD=' "$KEYS_FILE"; then
    bad "RESTIC_PASSWORD is not defined in $KEYS_FILE"
  fi
  stamp="$ESTATE_STATE/baseline/last-backup"
  if [ -f "$stamp" ]; then
    now="$(date +%s)"; age=$(( now - $(cat "$stamp") ))
    [ "$age" -lt 172800 ] || meh "the last successful backup was $(( age / 86400 )) days ago (journalctl --user -u $(unit_name restic-backup.service))"
  else
    meh "no backup has completed yet (first run: systemctl --user start $(unit_name restic-backup.service))"
  fi
}
