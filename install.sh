#!/usr/bin/env bash
# install.sh — install the optional `hercules` launcher from its GitHub repo.
#
# The Hercules PLUGIN installs via the Claude Code marketplace (no Python needed):
#   /plugin marketplace add mbienkowski/hercules
#   /plugin install hercules@hercules
#
# This script only installs the optional branded `hercules` command (a thin launcher
# that execs `claude`, with `--claude-dir` config isolation). Installs from a pinned
# git URL over HTTPS via pipx (preferred) or pip — no package index involved.
set -euo pipefail

PACKAGE="hercules"
GIT_SPEC="git+https://github.com/mbienkowski/hercules.git"
UPGRADE="${1:-}"

# ── Python >= 3.9 check ───────────────────────────────────────────────────────
PYTHON=""
for candidate in python3.9 python3.10 python3.11 python3.12 python3.13 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    version=$("$candidate" -c "import sys; print(sys.version_info >= (3, 9))" 2>/dev/null || echo "False")
    if [[ "$version" == "True" ]]; then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo "Error: Python 3.9 or later is required for the hercules launcher." >&2
  echo "Most systems already ship 3.9+ (incl. macOS 12+). The plugin itself needs no Python —" >&2
  echo "install it via the Claude Code marketplace instead (see the README)." >&2
  exit 1
fi

echo "Using: $($PYTHON --version)"

# ── Install via pipx (preferred) or pip ──────────────────────────────────────
if command -v pipx >/dev/null 2>&1; then
  if [[ "$UPGRADE" == "--upgrade" ]]; then
    pipx upgrade "$PACKAGE"
  else
    pipx install "$GIT_SPEC"
  fi
elif command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1; then
  PIP=$(command -v pip3 2>/dev/null || command -v pip)
  FLAG=""
  [[ "$UPGRADE" == "--upgrade" ]] && FLAG="--upgrade"
  "$PIP" install --user $FLAG "$GIT_SPEC"
  LOCAL_BIN="$HOME/.local/bin"
  if ! echo "$PATH" | tr ':' '\n' | grep -qx "$LOCAL_BIN"; then
    echo ""
    echo "  Note: add the following to your shell profile (~/.zshrc or ~/.bash_profile):"
    echo "    export PATH=\"${LOCAL_BIN}:\$PATH\""
  fi
else
  echo "Error: neither pipx nor pip found." >&2
  echo "Install pipx first: https://pipx.pypa.io/stable/installation/" >&2
  exit 1
fi

echo ""
echo "Installed the 'hercules' launcher: $(command -v hercules 2>/dev/null || echo "$HOME/.local/bin/hercules")"
echo ""
echo "Next — install the plugin in Claude Code:"
echo "  /plugin marketplace add mbienkowski/hercules"
echo "  /plugin install hercules@hercules"
echo ""
echo "Then launch with:  hercules        (or: hercules --claude-dir ~/.claude-work)"
echo "Upgrade later with: $0 --upgrade"
