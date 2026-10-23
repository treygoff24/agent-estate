# shellcheck shell=bash
# Shared by install and check. Sourced after lib/estate.sh.
# shellcheck disable=SC2034
BIN="$(cfg paths.bin)"; BIN="${BIN/#\~/$HOME}"
CODE="$(cfg paths.code)"; CODE="${CODE/#\~/$HOME}"
STATE_DIR="$(cfg paths.state)"; STATE_DIR="${STATE_DIR/#\~/$HOME}"
REPO_URL="$(cfg modules.skills.repo_url)"
CHECKOUT="$(cfg modules.skills.checkout)"; CHECKOUT="${CHECKOUT/#\~/$HOME}"
[ -n "$CHECKOUT" ] || CHECKOUT="$CODE/skillherd"
POOL="$(cfg modules.skills.pool)"
[ -n "$POOL" ] || POOL="$(cfg paths.skills)"
POOL="${POOL/#\~/$HOME}"; POOL="${POOL%/}"
# The tool renders into ~/.agents/skills (the shared Agents surface). A library there
# would overlap its own output, which the tool refuses, so use a sibling folder instead.
AGENTS_SURFACE="${SKILLHERD_AGENTS_DIR:-$HOME/.agents/skills}"; AGENTS_SURFACE="${AGENTS_SURFACE%/}"
POOL_NOTE=""
if [ "$POOL" = "$AGENTS_SURFACE" ]; then
  POOL="$(dirname "$POOL")/skill-library"
  POOL_NOTE="paths.skills is the shared Agents output folder, so the library is $POOL"
fi
REMOTE="$(cfg modules.skills.pool_remote)"
SEED="$(cfg modules.skills.seed)"
REGISTER="$(cfg modules.skills.register_sync)"
REPOS_FILE="$(cfg modules.sync.repos_file)"; REPOS_FILE="${REPOS_FILE/#\~/$HOME}"
HERD_STATE="$STATE_DIR/skills"
STAMP="$HERD_STATE/installed"
HERD_CONFIG_FILE="${SKILLHERD_CONFIG:-${XDG_CONFIG_HOME:+$XDG_CONFIG_HOME/skillherd/config.json}}"
[ -n "$HERD_CONFIG_FILE" ] || HERD_CONFIG_FILE="$HOME/.config/skillherd/config.json"
# Where skill-cli, the tool's earlier name, kept its config; read once to carry it over.
OLD_CONFIG_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/skill/config.json"
# The sync row and hook this module wrote under the earlier name.
OLD_ROW_NAME="skill-cli"
OLD_HOOK_LINE="skill sync"
STARTER="$ESTATE_ROOT/skills"
HEALTH_SKILL="$ESTATE_ROOT/modules/health/skill/estate-health"
HOOK_LINE="skillherd sync"
DONE_WHEN="skillherd is on PATH, the pool $POOL exists, and 'skillherd doctor' reports no findings"
export PATH="$BIN:$PATH"

valid_settings() {
  [ -n "$REPO_URL" ] || { echo "modules.skills.repo_url is empty"; return 1; }
  case "$(basename "$BIN")" in bin) ;; *) echo "paths.bin ($BIN) must end in /bin: the skillherd installer puts its tools in <prefix>/bin"; return 1 ;; esac
}

# Names of the starter skills (folders holding a SKILL.md), plus the health triage skill.
starter_skills() {
  local d
  for d in "$STARTER"/*/ "$HEALTH_SKILL"/; do
    [ -f "${d}SKILL.md" ] && basename "$d"
  done
  return 0
}
