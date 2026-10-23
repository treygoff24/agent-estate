# shellcheck shell=bash
# Shared by install, check and uninstall. Sourced after lib/estate.sh.
LABEL="$(label)"
INTERVAL="$(cfg modules.usage.interval_seconds)"
USAGE_DIR="$ESTATE_STATE/usage"
WRAPPER="$USAGE_DIR/poll.sh"
SHOW_BIN="$(cfg paths.bin)/usage-show"
CONF_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
if [ "$ESTATE_PLATFORM" = mac ]; then
  UNITS=("launchd.plist:$HOME/Library/LaunchAgents/$LABEL.plist")
else
  UNITS=("service:$CONF_HOME/systemd/user/$LABEL.service" "timer:$CONF_HOME/systemd/user/$LABEL.timer")
fi
DONE_WHEN="every $((INTERVAL / 60 > 0 ? INTERVAL / 60 : 1)) minutes the timer polls each configured harness account and rewrites $USAGE_DIR/snapshot.json; every account reads ok; run usage-show to see it"
export LABEL INTERVAL USAGE_DIR WRAPPER SHOW_BIN UNITS DONE_WHEN

valid_settings() {
  [[ "$INTERVAL" =~ ^[0-9]+$ ]] && [ "$INTERVAL" -ge 60 ] \
    || { echo "modules.usage.interval_seconds: '$INTERVAL' must be a whole number of seconds, 60 or more"; return 1; }
}

wrapper_text() {
  printf '#!/usr/bin/env bash\n# Written by agent-estate (usage module). Sets the environment the poller needs.\n'
  printf 'export ESTATE_ROOT=%q ESTATE_CONFIG=%q ESTATE_STATE=%q ESTATE_MACHINE=%q\n' \
    "$ESTATE_ROOT" "$ESTATE_CONFIG" "$ESTATE_STATE" "${ESTATE_MACHINE:-}"
  # The interpreter is pinned: launchd's PATH has no usable python3. $PY comes from pin_python
  # (install) or pinned_python (check).
  # shellcheck disable=SC2016  # the script path is written literally; the wrapper expands it
  printf 'exec %q "$ESTATE_ROOT/modules/usage/usage-poll" "$@"\n' "$PY"
}
show_text() {
  printf '#!/usr/bin/env bash\n# Written by agent-estate (usage module): print the usage snapshot.\n'
  printf 'exec %q show "$@"\n' "$WRAPPER"
}
