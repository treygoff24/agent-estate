# shellcheck shell=bash
# Shared helpers for module scripts. Source it first thing:
#   . "$ESTATE_ROOT/lib/estate.sh"
# It sets strict mode, parses --dry-run, and gives you:
#   cfg KEY            print a config value (estate config get KEY)
#   label              this module's launchd/systemd label
#   render TPL DEST    render templates/TPL to DEST (atomic); honours --dry-run
#   run CMD...         run a command, or just print it under --dry-run
#   say MSG            progress line to stderr
#   pin_python | pinned_python | render_pinned TPL DEST   a pinned Python 3.11+ (Mac launchd jobs; below)
#   pin_python | pinned_python | render_pinned TPL DEST   a pinned Python 3.11+ for launchd jobs (see below)
#   ok|warn|fail MSG [DONE_WHEN]   (check scripts) print status + "done when:" and exit 0|2|1

set -euo pipefail

: "${ESTATE_ROOT:?run this through estate (bin/estate install|doctor), not directly}"
: "${ESTATE_MODULE:?run this through estate, not directly}"

ESTATE_DRY_RUN=0
for _arg in "$@"; do
  [ "$_arg" = "--dry-run" ] && ESTATE_DRY_RUN=1
done
unset _arg
export ESTATE_DRY_RUN

estate() { "$ESTATE_ROOT/bin/estate" "$@"; }
cfg() { estate config get "$1"; }
label() { estate label "$ESTATE_MODULE"; }
say() { printf '%s: %s\n' "$ESTATE_MODULE" "$*" >&2; }

run() {
  if [ "$ESTATE_DRY_RUN" = 1 ]; then
    printf 'would run: %s\n' "$*" >&2
  else
    "$@"
  fi
}

render() {
  local tpl="$ESTATE_MODULE_DIR/templates/$1" dest="$2"
  if [ "$ESTATE_DRY_RUN" = 1 ]; then
    if [ -f "$dest" ] && estate render "$tpl" | cmp -s - "$dest"; then
      printf 'unchanged: %s\n' "$dest" >&2
    else
      printf 'would write: %s\n' "$dest" >&2
      estate render "$tpl" >/dev/null   # still fail on a bad template
    fi
  else
    estate render "$tpl" --out "$dest"
  fi
}

# Pinned Python. launchd starts jobs with a minimal PATH, where python3 is Apple's 3.9 or missing,
# so a Mac job must name its interpreter. Install calls pin_python (finds Python 3.11+, records it
# in $ESTATE_STATE/<module>/python3, sets PY; fails with a clear message if there is none). A check
# calls pinned_python (reads the record back, confirms it still works). Templates write @PYTHON@
# where the interpreter goes; render_pinned and rendered_pinned fill it in.
python_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; }
find_python() {
  local c p
  for c in ${ESTATE_PYTHON_SEARCH:-python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3.13 python3.12 python3.11}; do
    p="$(command -v "$c" 2>/dev/null)" || continue
    python_ok "$p" || continue
    p="$("$p" -c 'import sys; print(sys.executable)' 2>/dev/null)" || continue
    if [ -n "$p" ] && [ -x "$p" ]; then printf '%s\n' "$p"; return 0; fi
  done
  return 1
}
pin_file() { printf '%s/%s/python3' "$ESTATE_STATE" "$ESTATE_MODULE"; }
pin_python() {
  PY="$(find_python)" || {
    say "no Python 3.11 or newer found (looked for python3 on PATH, /opt/homebrew/bin, /usr/local/bin). Install one (macOS: brew install python) and run this again."
    exit 1
  }
  if [ "$ESTATE_DRY_RUN" != 1 ]; then
    mkdir -p "$(dirname "$(pin_file)")"
    printf '%s\n' "$PY" > "$(pin_file)"
  fi
  export PY
}
pinned_python() {
  PY="$(cat "$(pin_file)" 2>/dev/null)" || PY=""
  [ -n "$PY" ] && [ -x "$PY" ] && python_ok "$PY" && { export PY; return 0; }
  return 1
}
rendered_pinned() { # TEMPLATE: the rendered template with @PYTHON@ filled in, on stdout
  estate render "$ESTATE_MODULE_DIR/templates/$1" \
    | "$PY" -c 'import os, sys; sys.stdout.write(sys.stdin.read().replace("@PYTHON@", os.environ["PY"]))'
}
render_pinned() { # TEMPLATE DEST: like render, for a template that holds @PYTHON@
  local tmp
  if [ "$ESTATE_DRY_RUN" = 1 ]; then
    if [ -f "$2" ] && rendered_pinned "$1" | cmp -s - "$2"; then
      printf 'unchanged: %s\n' "$2" >&2
    else
      printf 'would write: %s\n' "$2" >&2
    fi
    return 0
  fi
  mkdir -p "$(dirname "$2")"
  tmp="$2.tmp.$$"
  if rendered_pinned "$1" > "$tmp"; then
    mv -f "$tmp" "$2"
  else
    rm -f "$tmp"
    return 1
  fi
}

_status() {
  local code="$1" word="$2" msg="$3" done_when="${4:-}"
  printf '%s: %s\n' "$word" "$msg"
  [ -n "$done_when" ] && printf 'done when: %s\n' "$done_when"
  exit "$code"
}
ok()   { _status 0 ok "$@"; }
fail() { _status 1 fail "$@"; }
warn() { _status 2 warn "$@"; }
