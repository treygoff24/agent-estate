# shellcheck shell=bash
# Shared by install, check and uninstall. Sourced after lib/estate.sh.
LABEL="$(label)"
AGE="$(cfg modules.tmp-cleanup.age)"
DIR="$(cfg modules.tmp-cleanup.path)"
CONF_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
TMPFILES_CONF="$CONF_HOME/user-tmpfiles.d/$LABEL.conf"
TIMER_DROPIN="$CONF_HOME/systemd/user/systemd-tmpfiles-clean.timer.d/$LABEL.conf"
TIMER="systemd-tmpfiles-clean.timer"
DONE_WHEN="files this login owns under $DIR, untouched for $AGE, are removed by the hourly $TIMER user timer"
export LABEL AGE DIR TMPFILES_CONF TIMER_DROPIN TIMER DONE_WHEN

valid_settings() {
  [[ "$AGE" =~ ^[0-9]+(s|m|min|h|d|w)$ ]] || { echo "modules.tmp-cleanup.age: '$AGE' is not an age like 12h, 1d or 2w"; return 1; }
  [[ "$DIR" = /* ]] || { echo "modules.tmp-cleanup.path: '$DIR' must be an absolute path"; return 1; }
  [ "$DIR" != / ] || { echo "modules.tmp-cleanup.path: refusing to age /"; return 1; }
}
