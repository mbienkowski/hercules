# Contributing to Hercules

Hercules is authored once in `src/` and compiled to per-ecosystem trees under `dist/`
(`claude-code`, `opencode`, `cursor`) by the build pipeline in `scripts/build/`. CI regenerates and
drift-checks `dist/` on every push, so `main` always carries an in-sync build.

## Quick start

```bash
make install        # editable install with the dev toolchain
make build          # regenerate dist/ for every target
make test           # drift-check dist/ + run the suite with coverage
make test-mutation  # mutation testing (slower; gates on a 90% kill rate)
```

After editing anything under `src/`, rebuild and commit `dist/` alongside the source change.
An optional pre-commit hook regenerates `dist/` automatically:

```bash
git config core.hooksPath .githooks
```

## Where things live

- `src/content/` — neutral source: agents, commands, skills, protocols, and `persona.md`.
  Content uses `${token}` placeholders and `${target:…}` switches so one file compiles for every
  ecosystem.
- `src/targets/<name>/config.json` — per-target token vars (e.g. `product`, `ns`, `plan_enter`).
- `src/models.json` — `model_tier` (high/medium/low) → per-target model id. `null` means omit the
  field for that target.
- `scripts/build/` — the compiler: `parse` → `render` → `serialize` (per-target) → `cli` (FS write).
- `dist/` — generated output, committed and tracked (never git-ignored).

## Adding a new target (e.g. Codex, Cursor)

The build is registry-driven, so adding a target touches the build code in exactly one place and
adds one config file — `parse`/`render`/`model_map`/`cli` need no change. The procedure:

1. **Add a `Serializer` subclass + `register()` it** in `scripts/build/serialize.py`.
   A `Serializer` turns a parsed `(frontmatter, body)` into one target's output bytes. See
   `ClaudeCodeSerializer` and `OpenCodeSerializer` for the two live patterns: how frontmatter is
   rebuilt (which keys kept/dropped/aliased) and how the body is rendered.

2. **Add `src/targets/<name>/config.json`** with the target's token `vars` (e.g. `product`,
   `host`, `ns`, `instructions_file`, `plan_enter`, `plan_exit`). These are substituted into
   `${token}` placeholders in source content at build time.

3. **Add a `models.json` row** mapping `model_tier` → the target's model id (or `null` to omit
   per-agent models, as OpenCode does). `model_map.resolve` falls back toward higher tiers when a
   tier is unset.

4. **Optional build-driver entries** in `scripts/build/cli.py`:
   - `_RENAMES` — per-target source→dest filename remaps (e.g. `persona.md` → `CLAUDE.md`).
   - A target-specific branch in `build_target` — if the target needs byte-copied non-markdown
     assets (like Claude's `hooks/*.py`) or generated extras (like OpenCode's `plugin.js`), add a
     branch mirroring the `_CLAUDE_COPIES` / `_emit_opencode_extras` patterns.

5. **Rebuild and commit**: `make build` regenerates `dist/<name>/`; commit it alongside the source.

6. **Add tests** under `tests/build/` pinning the new target's serializer output, and a conformance
   block in `tests/build/test_conformance.py` for any ecosystem-specific invariants. Add a
   mirror-parity test (see `test_opencode_mirror.py`) if the target has both standalone files and
   an inlined manifest.

7. **Add a smoke-checklist section** to `RELEASE.md` for the live (non-build-provable) behaviours
   the new target requires a human to confirm before release.

The keystone invariant: `make test` runs `--check` (renders to a temp dir, diffs against committed
`dist/`, fails on drift) plus the full suite — so a target that doesn't render deterministically, or
whose output diverges from committed `dist/`, fails CI immediately.

## Conventions

- **No comments in code** unless explaining a non-obvious decision.
- Tests live in `tests/`, organised by category (`build/`, `agents/`, `commands/`, `hooks/`, …).
  `tests/test_collection_integrity.py` guards that no test directory is hidden by `norecursedirs`.
- One version across all manifests — `scripts/build/version_targets.py` is the single canonical
  list; `scripts/set_version.py` writes it, CI's `validate` job reads it.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
  `refactor:`, `test:`, `docs:`, `ci:`) — the release pipeline derives the version bump from them.
