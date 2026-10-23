# shellcheck shell=bash
# Shared by install, check and uninstall. Sourced after lib/estate.sh.
LABEL="$(label)"
BIN="$(cfg paths.bin)"
CONF_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
UNIT_DIR="$CONF_HOME/systemd/user"
SERVICE="$UNIT_DIR/$LABEL.service"
TIMER_FILE="$UNIT_DIR/$LABEL.timer"
TIMER="$LABEL.timer"
DONE_WHEN="tailnet is set in estate.toml, Tailscale is running here, and the $TIMER user timer is active so expired links come down"
export LABEL BIN SERVICE TIMER_FILE TIMER DONE_WHEN
