#!/usr/bin/env bash
# Install an ecosystem's real CLI for its smoke leg (invoked by `make smoke-install`). Driven by env
# from the smoke matrix: INSTALL_METHOD (npm|script), NPM_PACKAGE, NPM_VERSION, INSTALL_URL,
# INSTALL_FLAGS, CLI.
#
# Matrix values arrive via env (never interpolated into the shell), so a fork PR that edits a
# smoke.json cannot inject a command here. A non-npm (curl) installer is DOWNLOADED to a file then
# executed — never streamed straight to bash. Ends in `$CLI --version`, so an absent binary fails the
# job.
set -euo pipefail

if [ "$INSTALL_METHOD" = "npm" ]; then
  SPEC="$NPM_PACKAGE@$NPM_VERSION"
  for i in 1 2 3; do
    timeout 120 npm install -g "$SPEC" && break
    echo "::warning::npm install of $SPEC failed (attempt $i/3), retrying..."
    sleep $((i * 5))
  done
else
  curl $INSTALL_FLAGS "$INSTALL_URL" -o /tmp/cli-install.sh
  bash /tmp/cli-install.sh
  echo "$HOME/.local/bin" >> "$GITHUB_PATH"
  echo "$HOME/.cursor/bin" >> "$GITHUB_PATH"
  export PATH="$HOME/.local/bin:$HOME/.cursor/bin:$PATH"
fi
"$CLI" --version
