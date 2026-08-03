#!/usr/bin/env bash
# Tripwire: every commit that changes production code must carry a test change.
# PER-COMMIT contract — a push is judged one commit at a time, so an early compliant
# commit never excuses a later violating one. Escape hatch: a pure rename marked
# [rename-only] in its own commit message. Fails LOUD on an unresolvable base
# (shallow checkout) — the gate job needs fetch-depth: 0.
# Inputs: $BASE (base ref/sha), $HEAD_SHA (tip, default HEAD).
source "$(dirname "${BASH_SOURCE[0]}")/resolve_base.sh"

for c in $(git rev-list --reverse "$BASE..$HEAD_SHA"); do
  # Production code is not only the engine. A recipe (`src/targets/*.json`) IS the build's source of
  # truth — an entry added there ships a file — and `src/content/targets/*/*.js` is executable code
  # shipped to users. Both were outside this pattern until the recipe vocabulary made them load-bearing.
  prod=$(git diff-tree --no-commit-id --name-only -r "$c" -- 'internal/**/*.mts' 'src/**/*.py' 'src/targets/*.json' 'src/content/targets/**/*.js' | grep -vE '(^|/)tests/' || true)
  tst=$(git diff-tree --no-commit-id --name-only -r "$c" | grep -E '(^|/)tests/|\.spec\.ts$|(^|/)test_[^/]*\.py$' || true)
  if [ -n "$prod" ] && [ -z "$tst" ]; then
    if git log -1 --format=%B "$c" | grep -qF '[rename-only]'; then
      continue
    fi
    echo "::error::commit $c changes production code without any test change; add a test in the same commit or mark a pure rename with [rename-only]" >&2
    exit 1
  fi
done
