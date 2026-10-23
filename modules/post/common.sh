# shellcheck shell=bash
# Shared by install and check. Sourced after lib/estate.sh.
# shellcheck disable=SC2034
BIN="$(cfg paths.bin)"; BIN="${BIN/#\~/$HOME}"
CODE="$(cfg paths.code)"; CODE="${CODE/#\~/$HOME}"
STATE_DIR="$(cfg paths.state)"; STATE_DIR="${STATE_DIR/#\~/$HOME}"
REPO_URL="$(cfg modules.post.repo_url)"
CHECKOUT="$(cfg modules.post.checkout)"
CHECKOUT="${CHECKOUT/#\~/$HOME}"
[ -n "$CHECKOUT" ] || CHECKOUT="$CODE/post"
METHOD="$(cfg modules.post.install_method)"
HOOKS="$(cfg modules.post.hooks)"
REGISTER="$(cfg modules.post.register_sync)"
BRIDGE="$(cfg modules.post.bridge)"
RELAY_URL="$(cfg modules.post.relay_url)"
SSH_KEY="$(cfg modules.post.ssh_key)"; SSH_KEY="${SSH_KEY/#\~/$HOME}"
INTERVAL="$(cfg modules.post.bridge_interval)"
REPOS_FILE="$(cfg modules.sync.repos_file)"; REPOS_FILE="${REPOS_FILE/#\~/$HOME}"
POST_STATE="$STATE_DIR/post"
CARGO_ROOT="$POST_STATE/cargo"
STAMP="$POST_STATE/installed"
HOOK_DIR="$CHECKOUT/skills/post/hooks"
CLAUDE_SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
CODEX_HOOKS="${CODEX_HOME:-$HOME/.codex}/hooks.json"
PI_EXT="$HOME/.pi/agent/extensions/post-mail"
CURSOR_HOOKS="$HOME/.cursor/hooks.json"
GROK_HOOKS="$HOME/.grok/hooks/post-mail.json"
BRIDGE_LABEL_MAC="org.post.bridge"
BRIDGE_TIMER="post-bridge.timer"
DONE_WHEN="post is on PATH, 'post doctor' reports no findings, and the mail hook is in each harness you listed"
export PATH="$BIN:$PATH"

valid_settings() {
  case "$METHOD" in auto|release|source) ;; *) echo "modules.post.install_method: '$METHOD' is not auto, release or source"; return 1 ;; esac
  [ -n "$REPO_URL" ] || { echo "modules.post.repo_url is empty"; return 1; }
  if [ "$BRIDGE" = true ]; then
    [ -n "$RELAY_URL" ] || { echo "modules.post.relay_url is required when bridge = true (the private relay repo's git URL; see modules/post/README.md)"; return 1; }
    [ -n "${ESTATE_MACHINE:-}" ] || { echo "bridge = true needs this machine's name in [[machines]] (set hostname there, or export ESTATE_MACHINE)"; return 1; }
    [[ "$ESTATE_MACHINE" =~ ^[a-z0-9-]{1,32}$ ]] || { echo "machine name '$ESTATE_MACHINE' is not valid for the bridge (lowercase letters, digits, dashes; at most 32)"; return 1; }
  fi
}

# The harnesses listed in estate.toml that post has an adapter for.
harnesses() {
  local h
  for h in claude codex pi cursor grok; do
    cfg "harnesses.$h" >/dev/null 2>&1 && echo "$h"
  done
  return 0
}

find_post() {
  if [ -x "$BIN/post" ]; then echo "$BIN/post"; else command -v post || true; fi
}

# Is the adapter for harness $1 registered?
hook_present() {
  case "$1" in
    claude) [ -f "$CLAUDE_SETTINGS" ] && grep -q 'post-claude-mail' "$CLAUDE_SETTINGS" ;;
    codex)  [ -f "$CODEX_HOOKS" ] && grep -q 'post-codex-mail' "$CODEX_HOOKS" ;;
    pi)     [ -f "$PI_EXT/index.js" ] ;;
    cursor) [ -f "$CURSOR_HOOKS" ] && grep -q 'post' "$CURSOR_HOOKS" ;;
    grok)   [ -f "$GROK_HOOKS" ] ;;
  esac
}
