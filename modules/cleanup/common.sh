# shellcheck shell=bash
# Shared by install, check and uninstall. Sourced after lib/estate.sh.
LABEL="$(label)"
BIN="$(cfg paths.bin)"
STATE="$ESTATE_STATE/cleanup"
CONF_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
UNIT_DIR="$CONF_HOME/systemd/user"
SERVICE="$UNIT_DIR/$LABEL.service"
TIMER_FILE="$UNIT_DIR/$LABEL.timer"
TIMER="$LABEL.timer"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
MAX_AGE_MIN=840   # six-hourly run, with slack for a sleeping laptop and a missed slot
DONE_WHEN="the $LABEL job runs every six hours and $STATE/last-run.json is under ${MAX_AGE_MIN} minutes old"
export LABEL BIN STATE DONE_WHEN SERVICE TIMER_FILE TIMER PLIST DOMAIN
