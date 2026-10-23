# shellcheck shell=bash
# Shared by install, check and uninstall. Sourced after lib/estate.sh.
LABEL="$(label)"
BIN="$(cfg paths.bin)"
STATE="$ESTATE_STATE/health"
CONF_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
UNIT_DIR="$CONF_HOME/systemd/user"
SERVICE="$UNIT_DIR/$LABEL.service"
TIMER_FILE="$UNIT_DIR/$LABEL.timer"
TIMER="$LABEL.timer"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
MAX_AGE_MIN=150   # hourly run plus slack for a sleeping laptop or a randomized start
DONE_WHEN="the $LABEL job runs hourly and $STATE/latest.json is under ${MAX_AGE_MIN} minutes old"
export LABEL BIN STATE DONE_WHEN SERVICE TIMER_FILE TIMER PLIST DOMAIN
