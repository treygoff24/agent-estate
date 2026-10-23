# shellcheck shell=bash
# Shared by install, check and uninstall. Sourced after lib/estate.sh.
LABEL="$(label)"
BIN_DIR="$(cfg paths.bin)"
STATE_DIR="$(cfg paths.state)"
REPOS_FILE="$(cfg modules.sync.repos_file)"
REPOS_FILE="${REPOS_FILE/#\~/$HOME}"
HOUR="$(cfg modules.sync.hour)"
MINUTE="$(cfg modules.sync.minute)"
CONF_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
UNIT_DIR="$CONF_HOME/systemd/user"
SERVICE="$UNIT_DIR/$LABEL.service"
TIMER_FILE="$UNIT_DIR/$LABEL.timer"
TIMER="$LABEL.timer"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SYNC_BIN="$BIN_DIR/estate-sync"
printf -v WHEN '%02d:%02d' "$HOUR" "$MINUTE" 2>/dev/null || WHEN="$HOUR:$MINUTE"
DONE_WHEN="the $LABEL timer is loaded and $SYNC_BIN finished OK within the last 36 hours (run it by hand: estate-sync)"
export LABEL BIN_DIR STATE_DIR REPOS_FILE SERVICE TIMER_FILE TIMER PLIST SYNC_BIN WHEN DONE_WHEN

valid_settings() {
  [[ "$HOUR" =~ ^[0-9]+$ ]] && [ "$HOUR" -le 23 ] \
    || { echo "modules.sync.hour: '$HOUR' is not a number from 0 to 23"; return 1; }
  [[ "$MINUTE" =~ ^[0-9]+$ ]] && [ "$MINUTE" -le 59 ] \
    || { echo "modules.sync.minute: '$MINUTE' is not a number from 0 to 59"; return 1; }
}
