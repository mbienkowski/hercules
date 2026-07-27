#!/usr/bin/env bash
# Commit the version bump, tag it, and push (invoked by `make release-commit`). Env: NEW_VERSION, NEW_TAG.
# Stages every file VERSION_TARGETS names (no hardcoded manifest paths), plus regenerated dist/ and
# CHANGELOG.md; the annotated tag with `--follow-tags` pushes the tag at that exact commit.
#
# Reads VERSION_TARGETS from the compiled .ts-out/ artifact the `release` job downloads from `prepare`
# (see release.yml) rather than running `npm ci`/`tsc` itself: this job holds contents:write, and
# `npm ci` must never run in a job holding a push-capable credential.
set -euo pipefail
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
FILES=$(node --input-type=module -e "
import { VERSION_TARGETS } from './.ts-out/builder/versionTargets.mjs';
console.log(VERSION_TARGETS.map(([rel]) => rel).join(' '));
")
git add $FILES dist CHANGELOG.md
git commit -m "chore(release): ${NEW_VERSION} [skip ci]"
git tag -a -m "Release ${NEW_TAG}" "${NEW_TAG}"
git push --follow-tags
