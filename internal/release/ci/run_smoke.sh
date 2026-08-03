#!/usr/bin/env bash
# Run one ecosystem's live-CLI smoke test and fail CLOSED (invoked by `make smoke-run`). Env: TEST,
# TARGET, RESULT_PREFIX (smoke-results).
#
# `pipefail` makes a red vitest propagate through `tee` and fail the leg. An all-skipped run (the CLI
# silently absent) exits 0 with "N skipped" and no "N passed" — a green gate that loaded nothing, which
# the grep below catches. Runs against the .spec.ts source; Vitest transforms TypeScript on the fly.
#
# `--config` is REQUIRED. The default config excludes every live-CLI `smoke.spec.ts` under tests/dist/
# so the everyday suite stays deterministic, and that exclusion beats an explicit file path on the
# command line: without this flag every leg exits 1 with "No test files found". That is exactly what
# happened when the exclusion was introduced and this script was not updated alongside it, taking all
# seven CI smoke legs red.
set -eo pipefail
PREFIX="${RESULT_PREFIX:-smoke-results}"
RESULTS="$PREFIX-$TARGET.txt"

npx vitest run --config vitest.smoke.config.mts "$TEST" --reporter=verbose 2>&1 | tee "$RESULTS"
grep -qE '[0-9]+ passed' "$RESULTS" || {
  echo "::error::$TARGET smoke produced no passing checks (all skipped?) — the real CLI must run in CI, the gate did not actually load the plugin"
  exit 1
}
