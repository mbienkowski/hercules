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
- [ ] The `hercules-reference` skill loads and its `§` sections (e.g. Artifact root resolution) are
      available — the operational reference lives there, not in the (unloaded) plugin `CLAUDE.md`.
- [ ] At Design's coverage gate, a **fresh `cynical-reviewer`** is actually spawned (not the main
      session) and its coverage findings reach you at Plan-approval — the judgment is independent, not
      self-review. (Cannot be proven by the build; this is the live check.)
- [ ] A command that reads `${CLAUDE_PLUGIN_ROOT}/protocols/…` resolves the path (docs say it expands
      in agent/skill content; *command* content is the one case unverified without this run).

### OpenCode

**Install:** OpenCode does not auto-discover an npm plugin — after `npm install hercules`, the user
must add it to their `opencode.json`:

```json
{ "plugin": ["hercules"] }
```

OpenCode then resolves the package `main` (`dist/opencode/plugin.js`) and runs its `config` hook.
These load-time behaviours are **not** provable by the build (no headless OpenCode harness exists) —
they must be confirmed live before release:

- [ ] With `"plugin": ["hercules"]` set, the `config` hook actually fires (agents/commands register).
      *If it does not, nothing inline registers — the whole plugin is inert.*
- [ ] `plugin.js` loads with no missing-asset throw (`instructions.md` + `skills/` present as siblings).
- [ ] `default_agent` is `hercules` (primary); a subagent (e.g. `challenger`) spawns as a subagent.
- [ ] `/hercules:discover` resolves and runs as the `hercules` agent (confirm the `:` in the command
      name is honoured in the slash menu).
- [ ] A skill auto-fires from its description (skills are reachable via `cfg.skills.paths`).
- [ ] Command prompts contain **no** leaked YAML frontmatter and show a real description in the UI.
- [ ] "Which version are you?" reports the package version (reads `package.json`, not a Claude path).
- [ ] `CAPABILITIES.md` discloses the write-gate and model-tier gaps.
- [ ] The Build phase's Spec-Sync spawns the **bare** `cynical-reviewer` id (not `hercules:cynical-reviewer`).
- [ ] Protocol references resolve — the 3 protocols are injected into `cfg.instructions` (confirm the
      config-hook mutation to `instructions` is applied before the model runs; documented for skills).
- [ ] The `hercules-reference` skill is model-invoked and its `§` sections are reachable.

### Cross-ecosystem

- [ ] `dist/claude-code/.claude-plugin/plugin.json`, `package.json`, and `pyproject.toml` all show the
      release version (matches the git tag).

v1 ships **Claude Code + OpenCode**. Codex and Cursor are TBD — add their smoke sections when delivered.
