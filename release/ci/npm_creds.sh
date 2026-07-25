#!/usr/bin/env bash
# Report whether npm publish credentials are configured (invoked by `make npm-creds`). Emits only a
# boolean to $GITHUB_OUTPUT so the NPM_TOKEN is never in scope for the third-party tag/release actions —
# only this check and the publish step see it. Env: NPM_TOKEN.
set -euo pipefail
if [ -n "${NPM_TOKEN:-}" ]; then
  echo "enabled=true"  >> "$GITHUB_OUTPUT"
else
  echo "enabled=false" >> "$GITHUB_OUTPUT"
fi
