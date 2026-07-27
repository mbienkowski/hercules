#!/usr/bin/env bash
# Annotate a red mutation gate with its release impact (invoked by `make mutation-*-annotate` on
# failure). Env: RUNTIME (e.g. "mutation-ts").
set -euo pipefail
echo "::error::${RUNTIME} failed the kill-rate gate — no release will be cut from this commit until it is fixed."
