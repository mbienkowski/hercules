#!/usr/bin/env bash
# install.sh — Install the hercules CLI from its GitHub repo via pip or pipx.
# Installs from a pinned git URL over HTTPS; pip/pipx build the wheel locally. No package index.
set -euo pipefail

# Command/package name is `hercules`; installed from the git repo over HTTPS.
# Always install from the repo, never `pip install hercules`.
PACKAGE="hercules"
GIT_SPEC="git+https://github.com/mbienkowski/hercules.git"
UPGRADE="${1:-}"

# ── Python version check ──────────────────────────────────────────────────────
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
  echo "Error: Python 3.9 or later is required." >&2
  echo "" >&2
  echo "Most systems already ship 3.9+ (incl. macOS 12+). If yours is older, install via:" >&2
  echo "  https://www.python.org/downloads/  (or your package manager)" >&2
  exit 1
fi

echo "Using: $($PYTHON --version)"

# ── Install via pipx (preferred) or pip ──────────────────────────────────────
if command -v pipx >/dev/null 2>&1; then
  if [[ "$UPGRADE" == "--upgrade" ]]; then
    echo "Upgrading $PACKAGE via pipx..."
    pipx upgrade "$PACKAGE"
  else
    echo "Installing $PACKAGE via pipx..."
    pipx install "$GIT_SPEC"
  fi
  echo ""
  echo "Installed: $(command -v hercules)"
elif command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1; then
  PIP=$(command -v pip3 2>/dev/null || command -v pip)
  FLAG=""
  [[ "$UPGRADE" == "--upgrade" ]] && FLAG="--upgrade"
  echo "Installing $PACKAGE via pip..."
  "$PIP" install --user $FLAG "$GIT_SPEC"
  echo ""
  # Warn if ~/.local/bin is not on PATH.
  LOCAL_BIN="$HOME/.local/bin"
  if ! echo "$PATH" | tr ':' '\n' | grep -qx "$LOCAL_BIN"; then
    echo "  Note: add the following to your shell profile (~/.zshrc or ~/.bash_profile):"
    echo ""
    echo "    export PATH=\"${LOCAL_BIN}:\$PATH\""
    echo ""
  fi
else
  echo "Error: neither pipx nor pip found." >&2
  echo "Install pipx first: https://pipx.pypa.io/stable/installation/" >&2
  exit 1
fi

echo "Usage:"
echo "  hercules                        # launch claude with auto-updated plugins"
echo "  hercules --sync                 # force an immediate plugin refresh and exit"
echo "  hercules --branch feature-x     # test a plugin branch"
echo "  hercules --setup                # configure plugin repository"
echo "  hercules --self-update          # upgrade hercules itself"
echo ""
echo "To upgrade later:"
echo "  $0 --upgrade"
