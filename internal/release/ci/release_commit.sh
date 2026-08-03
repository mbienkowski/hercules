#!/usr/bin/env bash
# Commit the version bump, tag it, and push (invoked by `make release-commit`). Env: NEW_VERSION, NEW_TAG.
# Stages every file VERSION_TARGETS names (no hardcoded manifest paths), plus regenerated dist/ and
# CHANGELOG.md; the annotated tag with `--follow-tags` pushes the tag at that exact commit.
#
# Reads VERSION_TARGETS from .local/ts-out/, compiled earlier in the same `release` job (see release.yml).
set -euo pipefail
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
FILES=$(node --input-type=module -e "
import { VERSION_TARGETS } from './.local/ts-out/release/version-files.mjs';
console.log(VERSION_TARGETS.map(([rel]) => rel).join(' '));
")
git add $FILES dist CHANGELOG.md
git commit -m "chore(release): ${NEW_VERSION} [skip ci]"
git tag -a -m "Release ${NEW_TAG}" "${NEW_TAG}"
git push --follow-tags
