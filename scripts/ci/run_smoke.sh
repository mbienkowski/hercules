#!/usr/bin/env bash
# Run one ecosystem's live-CLI smoke test and fail CLOSED (invoked by `make smoke-run`). Env: TEST,
# TARGET, RESULT_PREFIX (smoke-results for ci.yml, smoke-latest for the nightly).
#
# `pipefail` makes a red pytest propagate through `tee` and fail the leg. If pytest instead
# all-SKIPPED (the CLI silently absent, or every test skipped), it exits 0 with only "N skipped" and
# no "N passed" — which would read as a green gate that loaded nothing; the grep below catches that.
set -eo pipefail
PREFIX="${RESULT_PREFIX:-smoke-results}"
RESULTS="$PREFIX-$TARGET.txt"

pytest "$TEST" -v -rs 2>&1 | tee "$RESULTS"
grep -qE '[0-9]+ passed' "$RESULTS" || {
  echo "::error::$TARGET smoke produced no passing checks (all skipped?) — the real CLI must run in CI, the gate did not actually load the plugin"
  exit 1
}
