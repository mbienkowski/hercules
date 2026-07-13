# Releasing Hercules

Hercules is authored once in `src/` and compiled to per-ecosystem trees under `dist/` (`make build`).
CI regenerates and drift-checks `dist/` on every push, so `main` always carries an in-sync build.

## Automated pipeline

On every merge to `main`, `release.yml` runs after CI succeeds:

1. Computes the next version from Conventional Commits (`feat`/`fix`/`perf` bump the CHANGELOG).
2. `scripts/set_version.py` stamps that version into **every** file in the canonical list
   (`scripts/build/version_targets.py`): `pyproject.toml`, `dist/claude-code/.claude-plugin/plugin.json`,
   `package.json`. One version identifies the release everywhere.
3. Commits the bump (`chore(release): X.Y.Z [skip ci]`), tags `vX.Y.Z`, pushes.
4. Publishes the GitHub Release.
5. **Publishes the OpenCode plugin to npm** from the tagged tree (requires the `NPM_TOKEN` repo
   secret; the step self-skips if it is absent).

The `validate` CI job re-reads the canonical list and fails the build if any manifest disagrees, so a
release can never ship a split version.

## Manual smoke checklist (release-gating, once per release)

CI proves the artifacts are valid, in-sync, and regression-checked — it **cannot** prove the plugin
loads and behaves inside a live tool (no ecosystem offers a headless load-and-assert harness). Before
announcing a release, run this by hand and record the result (date, version, tester) in the release notes.

### Claude Code

- [ ] Install from the marketplace (`.claude-plugin/marketplace.json` → `dist/claude-code`).
- [ ] `hercules` is the default agent — "Hercules, where do I start?" answers in character.
- [ ] `/hercules:workflow` drives Discover → Design → Build → Ship and each phase writes its artifact
      in order (against a throwaway repo).
- [ ] The write-gate hook blocks an unapproved artifact write and allows it after `approved`.
- [ ] A specialist advisor spawns and replies in the A2A line format.

### OpenCode

- [ ] Install the published npm package; `plugin.js` loads with no missing-asset error.
- [ ] `default_agent` is `hercules` (primary); a subagent (e.g. `challenger`) spawns as a subagent.
- [ ] A skill auto-fires from its description.
- [ ] `CAPABILITIES.md` is present and discloses the write-gate and model-tier gaps.
- [ ] Commands are registered under the `hercules:` namespace.

### Cross-ecosystem

- [ ] `dist/claude-code/.claude-plugin/plugin.json`, `package.json`, and `pyproject.toml` all show the
      release version (matches the git tag).

v1 ships **Claude Code + OpenCode**. Codex and Cursor are TBD — add their smoke sections when delivered.
