#!/usr/bin/env bash
# The repo gate: run before every commit you hand on.
#   1. shellcheck every shell script in the repo
#   2. the Python tests (python3 -m unittest)
#   3. gitleaks over this branch's history and the work tree, if installed (--redact)
#   4. the private-marker scan (scripts/scan-private.py)
# Prints one verdict line with tool versions; exits 1 if any step failed.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

failed=()
versions=()
step() { printf '\n== %s\n' "$*"; }

# Shell scripts: *.sh plus any extensionless file with a sh/bash shebang
# (module install/check/uninstall scripts, bin/ tools).
shell_files=()
while IFS= read -r -d '' f; do
  [ -f "$f" ] || continue
  case "$f" in
    *.sh) shell_files+=("$f") ;;
    *.*) ;;
    *) head -n1 "$f" 2>/dev/null | grep -Eq '^#!.*\b(ba)?sh\b' && shell_files+=("$f") ;;
  esac
done < <(git ls-files -z --cached --others --exclude-standard)

step "shellcheck (${#shell_files[@]} files)"
if command -v shellcheck >/dev/null; then
  versions+=("shellcheck $(shellcheck --version | awk '/^version:/ {print $2}')")
  if [ "${#shell_files[@]}" -gt 0 ]; then
    shellcheck -x "${shell_files[@]}" || failed+=(shellcheck)
  fi
else
  echo "shellcheck not installed (brew install shellcheck / apt install shellcheck)"
  failed+=("shellcheck-missing")
fi

step "python tests"
versions+=("python $(python3 -c 'import platform; print(platform.python_version())')")
python3 -m unittest discover -s tests -t . || failed+=(tests)

step "gitleaks"
if command -v gitleaks >/dev/null; then
  versions+=("gitleaks $(gitleaks version)")
  gitleaks git --redact --no-banner --log-opts=HEAD . || failed+=(gitleaks-history)
  gitleaks dir --redact --no-banner . || failed+=(gitleaks-tree)
else
  echo "gitleaks not installed; skipped (brew install gitleaks)"
  versions+=("gitleaks skipped")
fi

step "private-marker scan"
scan_out="$(python3 scripts/scan-private.py 2>&1)" || failed+=(private-markers)
printf '%s\n' "$scan_out"
case "$scan_out" in
  *"(builtin only)"*) versions+=("private markers SKIPPED: no marker file") ;;
  *) versions+=("private markers: $(printf '%s\n' "$scan_out" | sed -n 's/.*(\([0-9]*\) markers.*/\1/p') patterns") ;;
esac

joined="$(IFS='|'; echo "${versions[*]}")"
joined="${joined//|/, }"
echo
if [ "${#failed[@]}" -eq 0 ]; then
  echo "gate: PASS ($joined)"
else
  echo "gate: FAIL: ${failed[*]} ($joined)"
  exit 1
fi
