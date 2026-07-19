#!/usr/bin/env bash
# Verify the checkout is the exact commit whose CI passed (invoked by `make release-verify`). On a
# workflow_run event the checkout resolves to main's CURRENT tip, which may have advanced past the
# validated commit; releasing that unvalidated tree would defeat the green-CI gate. Env: WANT_SHA.
set -euo pipefail
HEAD_SHA=$(git rev-parse HEAD)
if [ "$HEAD_SHA" != "$WANT_SHA" ]; then
  echo "::error::main advanced ($HEAD_SHA) past the CI-validated commit ($WANT_SHA); aborting so the newer commit's own green-CI release runs instead."
  exit 1
fi
