#!/usr/bin/env bash
# Report whether npm publish credentials are configured (invoked by `make npm-creds`). Emits only a
# boolean to $GITHUB_OUTPUT, so only this check and the publish step ever see NPM_TOKEN — never the
# third-party tag/release actions. Env: NPM_TOKEN.
set -euo pipefail
if [ -n "${NPM_TOKEN:-}" ]; then
  echo "enabled=true"  >> "$GITHUB_OUTPUT"
else
  echo "enabled=false" >> "$GITHUB_OUTPUT"
fi
