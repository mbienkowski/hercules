# Contributing to Hercules

Hercules is authored once (in `src/content/`, `src/targets/`, and `src/hooks/`) and compiled to per-ecosystem
trees under `dist/` (`claude-code`, `opencode`, `cursor`) by the build pipeline in `src/builder/`. CI
regenerates and drift-checks `dist/` on every push, so `main` always carries an in-sync build.

The deep rules for *extending the methodology itself* (commands, agents, skills, hooks, invariants)
live in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md); the release process is in [`RELEASE.md`](RELEASE.md).

## Quick start

```bash
make install        # editable pip install + npm ci — both runtimes' dev toolchains
make build          # regenerate dist/ for every target
make test           # drift-check dist/ + run the suite with coverage (both runtimes)
make test-mutation  # mutation testing (slower; gates on a 90% kill rate, both runtimes)
```

> **Run `make test-mutation` locally before opening a PR.** Mutation is **not** run on PRs (to keep PR
> feedback fast) — it runs as the **release gate on `main`**: a merge whose kill rate drops below 90%
> produces a red CI conclusion and **blocks the release**. So a mutation regression you don't catch
> locally won't surface on your PR — it will stop the next release *after* merge. Catch it here first.

After editing anything under `src/content/`, `src/targets/`, or `src/hooks/`, rebuild and commit `dist/`
alongside the source change. An optional pre-commit hook regenerates `dist/` automatically:

```bash
git config core.hooksPath .githooks
```

## Where things live

Every top-level directory is a domain, not a language or category — nothing is named `ts`, `py`, or
`scripts`. Each domain that has code owns its own `tests/` alongside it.

- `src/content/` — the product: neutral source agents, commands, skills, protocols, and `persona.md`.
  Content uses `${token}` placeholders and `${target:…}` switches so one file compiles for every
  ecosystem. Capability disclosures are compiled from the shared `src/content/capabilities.md` — no
  per-ecosystem directories, no per-ecosystem code. `src/content/tests/` covers the built plugin content
  itself (commands, agents, skills, protocols, docs, the plugin manifest).
- `src/targets/<name>.json` — ONE descriptor per ecosystem (the filename is the registry key):
  token `vars`, `models` tiers, the `smoke` matrix entry, per-role output shapes (`roles`),
  destination `routes`, inline JSON `artifacts` (manifests, settings, hook wiring), shared-`guard`
  modules, write-`gate` params, and rendered `templates`. Siblings follow a filename schema:
  `<name>.dist.<dest>` (byte-copied to plugin-root `<dest>`) for binary/marketplace assets, and
  `<name>.template.<dest>` (rendered from named computed values) for generated text like OpenCode's
  `plugin.js`; the directory layout is schema-validated — a stray file fails the build. Kept as its
  own top-level directory rather than nested under `src/content/`: the builder's content walk is
  recursive, so an ecosystem descriptor sitting inside `src/content/` would be swept up as if it were
  content to render.
- `src/hooks/` — the shared enforcement code, authored once and byte-copied to every ecosystem:
  the canonical frozen-test guard + the ONE generic write-gate adapter (`hercules_gate.py`). This is
  the one domain that stays Python permanently — it ships to and runs on the end user's machine, so
  it can't carry a Node runtime dependency. `src/hooks/tests/` is its own island (see § Testing below).
- `src/builder/` — the generic compiler: `parse` → `render` → `genSerialize` (descriptor-driven)
  → `genExtras` → the `bin/cli` entry point (filesystem write). `descriptor.mts` validates the closed
  vocabulary. `src/builder/tests/` covers the compiler itself.
- `src/release/` — ships the builder's output: versioning, changelog, npm packaging, CI smoke/validate
  checks, and the mutation-kill-rate gate (both its TypeScript and Python halves — see
  `src/release/mutation-gate.json`). `src/release/ci/` holds the bash glue the GitHub workflows call through
  `make`. `src/release/tests/` covers all of it.
- `src/metrics/` — instruction/token budgets, A2A (agent-to-agent) grammar checks, loading-chain gates. `src/metrics/tests/`
  covers it.
- `dist/` — generated output, committed and tracked (never git-ignored).
- `src/commons/` — cross-cutting test infrastructure that belongs to no single domain: repo-wide
  meta-guards (`src/commons/repo/`) plus the TypeScript test helpers shared across every domain's own
  `tests/` (`src/commons/support/`).

## Adding a new target

The authoritative contract is [`CODE_OF_CONDUCT.md` § Adding an ecosystem](CODE_OF_CONDUCT.md); this
is the practical checklist. **A new ecosystem is one new JSON file** — the engine has zero
per-ecosystem branches, classes, or modules. The CI-hard-failing steps that are easy to forget — the
write-gate declaration (step 4) — are called out so you don't pass local `make test` and then hit a
late CI failure. The procedure:

1. **Add `src/targets/<name>.json`** — copy the closest existing descriptor and adjust. Every
   section is validated against a closed vocabulary (`src/builder/descriptor.mts`): an unknown key
   or enum value fails the build loudly, naming the allowed set. The sections:
   - `vars` — token substitutions for `${token}` placeholders in source content.
   - `models` — `model_tier` (high/medium/low) → model id, or `null` to omit per-agent models.
   - `smoke` — the CLI, install method, and smoke-test path (feeds the CI smoke matrix directly;
     schema-required, so a target can't exist without it).
   - `dispatch` + `roles` — how sources map to roles and how each role serializes (named modes:
     `preserve`, `fields`, `wrap`, `plain`, `toml_command`; named field generators).
   - `routes` — src→dest relocations (`exact`, `suffix_swap`) for load-bearing renames like
     Gemini's `.toml` commands or Copilot's `.agent.md`.
   - `artifacts` — host manifests/settings/hook wiring as inline JSON, emitted canonically;
     `"versioned": true` injects the canonical version into a `${version}` token (fail-loud).
   - `guard` + `gate` — which `src/hooks/` modules ship, and the write-gate parameters the ONE
     generic adapter reads (`pre_tool` tool maps + decision shapes, or `event_guards`).
   - `templates` — for genuinely generated text (e.g. OpenCode's `plugin.js`): a
     `<name>.template.<dest>` sibling whose `__PLACEHOLDER__`s are filled from closed, named
     computed-value kinds (`js_string`, `js_string_list`, `js_root_joins`, `role_entries_js` — the
     computations are mutation-covered functions in `genExtras.mts`). A need the vocabulary can't
     express = a new NAMED value kind in `src/builder/` with tests, then referenced by name —
     never logic in the JSON.
2. **Disclose capability gaps** — add a `${target:<name>}` branch to the shared
   `src/content/capabilities.md` (compiled per ecosystem; shared claims stay on shared lines) and
   route it with `{"kind": "exact", "src": "capabilities.md", "dest": "CAPABILITIES.md"}`. For
   binary/marketplace assets use the sibling filename schema: `src/targets/<name>.dist.<dest>`
   ships byte-identically at `dist/<name>/<dest>`; a mis-prefixed or stray file fails discovery.
3. **Rebuild and commit**: `make build` regenerates `dist/<name>/`; commit it alongside the source.
4. **Declare the write-gate** (CI-hard-failing): add an entry for the target to `GATE_EXPECTATIONS`
   in `src/hooks/tests/test_enforcement_gates.py`. `test_every_registered_target_declares_a_gate` fails
   for any registered ecosystem with no declared write-gate (or an explicit, reasoned waiver) — this
   is a deliberate security forcing-function, so a new target can't ship ungated by accident.
5. **Add tests** under `src/builder/tests/` pinning the new target's output (see any
   `<name>Build.spec.ts`), and a conformance block in `src/builder/tests/guards/universalConformance.spec.ts`
   (or `conformance.spec.ts`) for any ecosystem-specific invariants.
6. **Add a smoke-checklist section** to `RELEASE.md` for the live (non-build-provable) behaviours
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
- Tests live alongside the domain they cover — `src/builder/tests/`, `src/release/tests/`, `src/metrics/tests/`,
  `src/content/tests/` (organised into `commands/`, `skillsAndAgents/`, `docsAndPlugin/`,
  `workflowAndProtocols/` subdirectories) — everything except the shipped `src/hooks/` island, whose own
  tests live in `src/hooks/tests/`. `src/commons/repo/test_collection_integrity.py` guards that no Python test
  directory is hidden by `norecursedirs`.
- One version, single-sourced — `package.json` is canonical; `pyproject.toml` is the only other
  literal (setuptools needs it) and is cross-checked against it. Both are the whole list in
  `src/builder/versionTargets.mts`; `src/release/setVersion.mts` writes them, CI's `validate` job
  checks them. The plugin manifests (versioned `artifacts` in each `src/targets/<eco>.json`) carry a
  `${version}` **token** — the build injects the canonical version into `dist/…/plugin.json`, so
  there's nothing to hand-bump in the source.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
  `refactor:`, `test:`, `docs:`, `ci:`) — the release pipeline derives the version bump from them.
