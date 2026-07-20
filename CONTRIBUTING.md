# Contributing to Hercules

Hercules is authored once in `src/` and compiled to per-ecosystem trees under `dist/`
(`claude-code`, `opencode`, `cursor`) by the build pipeline in `scripts/build/`. CI regenerates and
drift-checks `dist/` on every push, so `main` always carries an in-sync build.

The deep rules for *extending the methodology itself* (commands, agents, skills, hooks, invariants)
live in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md); the release process is in [`RELEASE.md`](RELEASE.md).

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

The build is registry-driven: `parse`/`render`/`model_map`/`cli`/`emit` need **no** change — a target
is additive (a serializer + a target descriptor + a few config/manifest files, all listed below).
The two CI-hard-failing steps that are easy to forget — the write-gate declaration (step 6) and
`smoke.json` (step 7) — are called out so you don't pass local `make test` and then hit a late CI
failure. The procedure:

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

4. **Register a `Target`** in `scripts/build/targets/<name>.py` and import it from
   `scripts/build/targets/__init__.py`. The `Target` binds the ecosystem to its source→dest mapping
   (a `renames` dict, or a `dest_fn` for a load-bearing rename like Cursor's `.mdc` rule) and its
   `emit_extras` — the non-content artifacts it copies or generates (manifests, hooks, capability
   docs), built from the leaf helpers in `scripts/build/emit.py`. `cli.py` holds **zero**
   per-ecosystem branches — dispatch is registry-driven — so onboarding a target never edits the
   orchestrator.

5. **Rebuild and commit**: `make build` regenerates `dist/<name>/`; commit it alongside the source.

6. **Declare the write-gate** (CI-hard-failing): add an entry for the target to `GATE_EXPECTATIONS`
   in `tests/hooks/test_enforcement_gates.py`. `test_every_registered_target_declares_a_gate` fails
   for any registered ecosystem with no declared write-gate (or an explicit, reasoned waiver) — this
   is a deliberate security forcing-function, so a new target can't ship ungated by accident.

7. **Add `src/targets/<name>/smoke.json`** (CI-hard-failing): the CI smoke matrix derives from the
   target registry and `scripts/ci/smoke_matrix.py` raises on a registered ecosystem with no
   `smoke.json`. It declares the CLI, install method, and the smoke-test path.

8. **Add tests** under `tests/build/` pinning the new target's serializer output, and a conformance
   block in `tests/build/test_conformance.py` for any ecosystem-specific invariants. Add a
   mirror-parity test (see `test_opencode_mirror.py`) if the target has both standalone files and
   an inlined manifest.

9. **Add a smoke-checklist section** to `RELEASE.md` for the live (non-build-provable) behaviours
   the new target requires a human to confirm before release.

The keystone invariant: `make test` runs `--check` (renders to a temp dir, diffs against committed
`dist/`, fails on drift) plus the full suite — so a target that doesn't render deterministically, or
whose output diverges from committed `dist/`, fails CI immediately.

## Testing your changes as a live plugin

To try your checkout in Claude Code, add **your local directory** as a marketplace:
`/plugin marketplace add /path/to/your/checkout`. Its `marketplace.json` declares the name
`mbienkowski`, so `/plugin install hercules@mbienkowski` then resolves to **your checkout**. If you
already added the public marketplace under that same name, remove it first
(`/plugin marketplace remove mbienkowski`) so the name isn't ambiguous — otherwise you'd be testing
the released version, not your changes. After `git checkout`-ing the branch you want, run
`/reload-plugins` to apply.

**Testing a branch before release (maintainers).** To pull a branch straight from GitHub without a
local checkout, add a *temporary* marketplace entry in `~/.claude-priv/settings.json` (or
`~/.claude/settings.local.json`, so it stays off-project and out of git):

```json
{
  "extraKnownMarketplaces": {
    "hercules-dev": {
      "source": { "source": "github", "repo": "mbienkowski/hercules", "ref": "your-feature-branch" }
    }
  },
  "enabledPlugins": { "hercules@hercules-dev": true }
}
```

`ref` accepts a branch, tag, or commit SHA (omit it for the default branch). `hercules-dev` is a
throwaway local name — **remove the entry and restart Claude Code when you're done** to return to the
released version. Restart after any change; settings are read at startup.

## Conventions

- **No comments in code** unless explaining a non-obvious decision.
- All `.md` filenames must be **lowercase** — macOS is case-insensitive but Linux (CI) is not, so a
  mixed-case name that works locally breaks on CI.
- Tests live in `tests/`, organised by category (`build/`, `agents/`, `commands/`, `hooks/`, …).
  `tests/test_collection_integrity.py` guards that no test directory is hidden by `norecursedirs`.
- One version across all manifests — `scripts/build/version_targets.py` is the single canonical
  list; `scripts/set_version.py` writes it, CI's `validate` job reads it.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
  `refactor:`, `test:`, `docs:`, `ci:`) — the release pipeline derives the version bump from them.
