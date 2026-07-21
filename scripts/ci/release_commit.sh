#!/usr/bin/env bash
# Commit the version bump, tag it, and push (invoked by `make release-commit`). Env: NEW_VERSION, NEW_TAG.
# Stages every file the canonical version list touches (no hardcoded manifest paths — a target added to
# VERSION_TARGETS is committed automatically) plus dist/ (regenerated so published artifacts carry the
# new version) and CHANGELOG.md. The annotated tag + `--follow-tags` pushes the tag at the exact commit.
set -euo pipefail
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
FILES=$(python -c "from scripts.build.version_targets import VERSION_TARGETS; print(' '.join(rel for rel, _ in VERSION_TARGETS))")
git add $FILES dist CHANGELOG.md
git commit -m "chore(release): ${NEW_VERSION} [skip ci]"
git tag -a -m "Release ${NEW_TAG}" "${NEW_TAG}"
git push --follow-tags
