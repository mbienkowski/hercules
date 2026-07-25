#!/usr/bin/env bash
# Detect whether this is the first release and capture the previous tag for the changelog range
# (invoked by `make release-meta`). Writes is_first/prev_tag to $GITHUB_OUTPUT.
set -euo pipefail
PREV_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
if [ -z "$PREV_TAG" ]; then
  { echo "is_first=true"; echo "prev_tag="; } >> "$GITHUB_OUTPUT"
else
  { echo "is_first=false"; echo "prev_tag=$PREV_TAG"; } >> "$GITHUB_OUTPUT"
fi
