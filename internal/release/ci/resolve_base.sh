#!/usr/bin/env bash
# Shared BASE resolution for every PER-COMMIT CI gate walking `BASE..HEAD_SHA` (tripwire.sh,
# normative_gate.sh): validates the inputs, falls back to the merge base on a new branch's
# all-zeros "before" SHA, and fails loud on an unresolvable base (needs fetch-depth: 0).
# Source this — never execute it directly — so the resolved $BASE lands in the caller's shell.
# Inputs: $BASE (base ref/sha), $HEAD_SHA (tip, default HEAD).
set -euo pipefail

BASE="${BASE:?BASE ref is required}"
HEAD_SHA="${HEAD_SHA:-HEAD}"

# First push of a new branch: GitHub sends an all-zeros "before" SHA — fall back to the
# merge base with origin/main so the whole branch is judged.
if [[ "$BASE" =~ ^0+$ ]]; then
  BASE=$(git merge-base origin/main "$HEAD_SHA")
fi

git rev-parse --verify --quiet "$BASE^{commit}" >/dev/null || {
  echo "::error::base ref '$BASE' unresolvable — the gate job needs fetch-depth: 0 (or an explicit fetch of the base branch)" >&2
  exit 1
}
