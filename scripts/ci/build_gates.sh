#!/usr/bin/env bash
# Build-gate suite (invoked by `make ci-build`): drift, determinism, and the untracked-dist guard.
# Runs FIRST in CI so a src/ edit pushed without a rebuild fails here, before any test burns minutes.
set -euo pipefail

echo "== Drift gate: committed dist/ must match a fresh build =="
python -m scripts.build.cli --target all --check

echo "== Determinism gate: two builds are byte-identical =="
python -m scripts.build.cli --target all
A=$(mktemp -d); cp -a dist "$A/dist"
git checkout -- dist
python -m scripts.build.cli --target all
diff -r "$A/dist" dist && echo "build is deterministic"
git checkout -- dist

echo "== Untracked-dist guard: dist/ is tracked, nothing left un-committed =="
if git check-ignore -q dist; then
  echo "::error::dist/ is git-ignored — tags would snapshot an empty tree"; exit 1
fi
python -m scripts.build.cli --target all
if [ -n "$(git status --porcelain --untracked-files=all dist)" ]; then
  echo "::error::dist/ has uncommitted output — run 'make build' and commit it"
  git status --porcelain --untracked-files=all dist; exit 1
fi
