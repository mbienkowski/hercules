#!/usr/bin/env bash
# Normative-change declaration gate: every commit touching shipped content
# (src/content/**, which now also holds each tool's own files under src/content/targets/) must declare its normative
# impact in its OWN commit message — "Normative-change: <one sentence>" or
# "Normative-change: none — wording only". The gate then surfaces the commit's
# content diff right beside the declaration, so review sees the real change,
# not just the claim. PER-COMMIT: an early declaration never excuses a later
# undeclared content commit. Honest limit (recorded in CODE_OF_CONDUCT.md):
# the declaration is self-attested; the gate forces the deliberate statement
# and the visible diff, not comprehension.
# Inputs: $BASE (base ref/sha), $HEAD_SHA (tip, default HEAD).
source "$(dirname "${BASH_SOURCE[0]}")/resolve_base.sh"

for c in $(git rev-list --reverse "$BASE..$HEAD_SHA"); do
  changed=$(git diff-tree --no-commit-id --name-only -r "$c" -- 'src/content' || true)
  [ -z "$changed" ] && continue
  if ! git log -1 --format=%B "$c" | grep -q '^Normative-change:'; then
    echo "::error::commit $c changes shipped content without a declaration; add 'Normative-change: <sentence>' or 'Normative-change: none — wording only' to its message" >&2
    exit 1
  fi
  echo "--- normative diff of $c (review this against its declaration) ---"
  git log -1 --format='%B' "$c" | grep '^Normative-change:'
  git diff-tree --no-commit-id -r -p "$c" -- 'src/content'
done
