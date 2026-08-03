#!/usr/bin/env bash
# Install an ecosystem's real CLI for its smoke leg (invoked by `make smoke-install`). Env from the
# smoke matrix: INSTALL_METHOD (package|script), NPM_PACKAGE, NPM_VERSION, INSTALL_URL, INSTALL_FLAGS, CLI.
#
# Matrix values arrive via env, never interpolated into the shell, so a fork pull request editing a
# smoke config cannot inject a command here. A curl installer is DOWNLOADED to a file then executed,
# never streamed straight to bash. Ends in `$CLI --version`, so an absent binary fails the job.
set -euo pipefail

if [ "$INSTALL_METHOD" = "package" ]; then
  SPEC="$NPM_PACKAGE@$NPM_VERSION"
  # 300s: some CLIs ship a ~350MB platform binary in the npm tarball (codex), which routinely
  # outran the old 120s ceiling on a cold cache — turning one slow download into a guaranteed
  # retry. The workflow's npm-download cache (ci.yml) makes a warm run seconds, not minutes.
  for i in 1 2 3; do
    timeout 300 npm install -g "$SPEC" && break
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
