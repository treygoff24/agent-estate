# shellcheck shell=bash
# Shared by install, check and uninstall. Sourced after lib/estate.sh.
TOOL_NAME="estate-config-sync"
TOOL="$ESTATE_MODULE_DIR/$TOOL_NAME"
BIN="$(cfg paths.bin)"
REPO="$(cfg modules.config-sync.repo)"
[ -n "$REPO" ] || REPO="$(cfg paths.code)/agent-env"
REPO="${REPO/#\~/$HOME}"
REMOTE="$(cfg modules.config-sync.remote)"
export TOOL_NAME TOOL BIN REPO REMOTE
