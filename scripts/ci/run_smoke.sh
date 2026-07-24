#!/usr/bin/env bash
# Run one ecosystem's live-CLI smoke test and fail CLOSED (invoked by `make smoke-run`). Env: TEST,
# TARGET, RESULT_PREFIX (smoke-results).
#
# `pipefail` makes a red vitest propagate through `tee` and fail the leg. If vitest instead
# all-SKIPPED (the CLI silently absent, or every test skipped), it exits 0 with only "N skipped" and
# no "N passed" — which would read as a green gate that loaded nothing; the grep below catches that.
# Runs directly against the .spec.ts source (Vitest transforms TypeScript on the fly, no separate
# `make compile` needed here — unlike `node .ts-out/...` entry points elsewhere in this repo).
set -eo pipefail
PREFIX="${RESULT_PREFIX:-smoke-results}"
RESULTS="$PREFIX-$TARGET.txt"

npx vitest run "$TEST" --reporter=verbose 2>&1 | tee "$RESULTS"
grep -qE '[0-9]+ passed' "$RESULTS" || {
  echo "::error::$TARGET smoke produced no passing checks (all skipped?) — the real CLI must run in CI, the gate did not actually load the plugin"
  exit 1
}
