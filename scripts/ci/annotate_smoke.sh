#!/usr/bin/env bash
# Annotate a red smoke leg with an actionable hint (invoked by `make smoke-annotate` on failure).
# Env: TARGET, CLI.
set -euo pipefail
echo "::error::${TARGET} ecosystem smoke failed — the built plugin did not install/load the way a real ${CLI} session would. Download the smoke-results-${TARGET} artifact for the raw subprocess output. If ${TARGET} is opencode and the failure mentions issues/15, that is the known OpenCode loader bug (fixed in scripts/build/manifests.py) regressing — anything else is an unreviewed finding."
