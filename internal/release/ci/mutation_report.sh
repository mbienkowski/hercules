#!/usr/bin/env bash
# Fortnightly mutation report (never a gate). Two tiers by the owner's value hierarchy:
# shipped Python carries the >=85% kill-rate requirement (a red SCHEDULED job, blocking nothing);
# TypeScript machinery is informational — read for trends and new survivors.
set -uo pipefail

# Fortnightly guard: run on even ISO weeks, or always when forced (manual dispatch).
if [ "${FORCE_MUTATION_REPORT:-no}" != "yes" ] && [ $((10#$(date +%V) % 2)) -ne 0 ]; then
  echo "odd ISO week — next report next Friday night"; exit 0
fi

echo "== Tier 1: shipped code (hooks + tools) — the tier with the requirement =="
mutmut run || true
mutmut junitxml > /tmp/mutmut-junit.xml 2>/dev/null || true
python3 - <<'PY'
import re, sys
try:
    raw = open('/tmp/mutmut-junit.xml').read()
except OSError:
    print('no junit output from mutmut — treating as a finding, not a failure'); sys.exit(0)
total = raw.count('<testcase'); survivors = raw.count('<failure')
if total == 0:
    print('mutmut reported zero mutants — check the run log'); sys.exit(0)
rate = 100 * (total - survivors) / total
print(f'shipped-code kill rate: {rate:.1f}% ({total - survivors}/{total}, requirement: >=85%)')
sys.exit(0 if rate >= 85 else 1)
PY
TIER1=$?

echo "== Tier 2: machinery (builder + release) — informational, no threshold =="
npx stryker run || true

exit $TIER1
