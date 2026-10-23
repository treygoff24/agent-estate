# shellcheck shell=bash
# Shared by install, check and uninstall. Sourced after lib/estate.sh.
BIN="$(cfg paths.bin)"
CONF_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CONF_DIR="$CONF_HOME/agent-estate"
CONF_JSON="$CONF_DIR/guardrails.json"
SKIP_FILE="$CONF_DIR/footgun-skip-guardrails"
LABEL="$(label)"
# systemd reads a dash in a unit name as a parent slice, so the slice name swaps dashes for underscores.
SLICE="$(printf '%s' "$LABEL" | tr '-' '_').slice"
SLICE_FILE="$CONF_HOME/systemd/user/$SLICE"
COMPILE_SLOTS="$(cfg modules.guardrails.compile_slots)"
RUSTC_SLOTS="$(cfg modules.guardrails.rustc_slots)"
RUSTC_BASE="$(cfg modules.guardrails.rustc_base)"
HEADROOM="$(cfg modules.guardrails.rustc_headroom_gb)"
CPU_WEIGHT="$(cfg modules.guardrails.cpu_weight)"
REFUSE_TESTS="$(cfg modules.guardrails.refuse_unwrapped_tests)"
TOOLS=(testrun footgun-hook)
[ "$COMPILE_SLOTS" = true ] && TOOLS+=(compile-slot-gate rustc-gate)
DONE_WHEN="testrun, footgun-hook are executable in $BIN and match this repo, the test slice limits are installed (Linux), and the footgun hook is in your harness settings"
export BIN CONF_JSON SKIP_FILE SLICE SLICE_FILE DONE_WHEN

valid_settings() {
  local k v
  for k in rustc_slots rustc_base rustc_headroom_gb cpu_weight; do
    v="$(cfg "modules.guardrails.$k")"
    [[ "$v" =~ ^[0-9]+$ ]] || { echo "modules.guardrails.$k: '$v' must be a whole number"; return 1; }
  done
  [ "$CPU_WEIGHT" -ge 1 ] && [ "$CPU_WEIGHT" -le 10000 ] || { echo "modules.guardrails.cpu_weight: $CPU_WEIGHT must be 1-10000"; return 1; }
  for k in memory_high memory_max; do
    v="$(cfg "modules.guardrails.$k")"
    [[ "$v" =~ ^([0-9]+[KMGT]?|[0-9]{1,3}%|infinity)$ ]] || { echo "modules.guardrails.$k: '$v' is not a systemd size like 8G, 80% or infinity"; return 1; }
  done
  for k in compile_slots refuse_unwrapped_tests; do
    v="$(cfg "modules.guardrails.$k")"
    [[ "$v" = true || "$v" = false ]] || { echo "modules.guardrails.$k: '$v' must be true or false"; return 1; }
  done
}

# The JSON the tools read at run time: the slice name and the compile-slot settings.
conf_json() {
  python3 - "$SLICE" "$ESTATE_PLATFORM" "$RUSTC_SLOTS" "$RUSTC_BASE" "$HEADROOM" <<'PY'
import json, sys
slice_name, platform, slots, base, headroom = sys.argv[1:6]
data = {"rustc_slots": int(slots), "rustc_base": int(base), "headroom_gb": int(headroom)}
if platform == "linux":
    data["slice"] = slice_name
print(json.dumps(data, indent=2, sort_keys=True))
PY
}

skip_text() {
  if [ "$REFUSE_TESTS" = false ]; then
    printf '# written by estate install guardrails (modules.guardrails.refuse_unwrapped_tests = false)\nheavy-test-unwrapped\n'
  fi
}
