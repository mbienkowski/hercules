#!/usr/bin/env bash
# Annotate a red @latest nightly leg (invoked by `make smoke-annotate-nightly` on failure). Env:
# TARGET, CLI. Non-blocking signal — the nightly never gates a merge.
set -euo pipefail
echo "::warning::${TARGET} smoke FAILED against ${CLI}@latest while the pinned version in src/targets/${TARGET}/smoke.json still passes CI. Either ${CLI} shipped a breaking change (file upstream / adapt the plugin) or the pin is simply stale (bump it). Non-blocking — this nightly never gates a merge."
