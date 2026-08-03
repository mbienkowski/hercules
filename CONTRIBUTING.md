# Contributing to Hercules

Hercules is authored once (in `src/content/`, `src/targets/`, `src/scripts/hooks/`, and `src/scripts/tools/`) and compiled to per-ecosystem
trees under `dist/` (`claude-code`, `opencode`, `cursor`, `codex`, and the other supported hosts) by the build pipeline in `internal/builder/`. CI
regenerates and drift-checks `dist/` on every push, so `main` always carries an in-sync build.

The deep rules for *extending the methodology itself* (commands, agents, skills, hooks, invariants)
live in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md); the release process is in [`RELEASE.md`](RELEASE.md).

## Quick start

```bash
make install        # editable pip install + npm ci — both runtimes' dev toolchains
make build          # regenerate dist/ for every target
make test           # drift-check dist/ + run the suite with coverage (both runtimes)
make test-mutation  # mutation testing — never a job that can block a merge or a release
```

> **`make test-mutation` is a tool, not a gate.** Mutation testing reaches CI only as the scheduled
> `mutation-report.yml` (`make mutation-report`), and no kill rate blocks a merge or
> a release — it prints the score and the surviving mutants, and you decide what a survivor is worth
> (a missing test, a better behaviour, or nothing). Worth running on code you are hardening; never
> something that stands between a green merge and the version it ships.

After editing anything under `src/content/`, `src/targets/`, `src/scripts/hooks/`, or `src/scripts/tools/`, rebuild and commit `dist/`
alongside the source change. An optional pre-commit hook regenerates `dist/` automatically:

```bash
git config core.hooksPath .githooks
```

## Where things live

Five top-level directories: `src/` (what we ship), `internal/` (what we build with, never shipped),
`tests/` (what we defend), `dist/` (what a user gets, generated), `.local/` (transient tool output,
regenerable, never committed). Every second-level directory under `src/` and `internal/` is a domain,
not a language or category — nothing is named `ts` or `py`. Tests live outside both entirely, in a
top-level `tests/` tree that
mirrors each domain by name (`tests/builder/` tests `internal/builder/`, and so on).

- `src/content/` — the product: neutral source agents, commands, skills, protocols, and `persona.md`.
  Content is a TEMPLATE, whole: `{{ token }}` substitutions and `{% if capability == "value" %}`
  blocks so one file renders for every ecosystem — the conditions ask what a tool CAN DO, never which
  tool it is. Frontmatter is not special; a file says in its own text what each host's copy should
  declare. Files only one host needs live under `src/content/targets/<name>/`. `tests/content/`
  covers the built plugin content itself (commands, agents, skills, protocols, docs, manifests).
- `src/targets/<name>.json` — ONE RECIPE per ecosystem (the filename is the registry key): `name`,
  `variables` (what its sources render with), `runtime_variables` (the `${NAME}` placeholders the
  HOST resolves, which we deliberately leave alone), and `targets` — a map from every shipped path
  under `dist/<name>/` to the ordered `sources` it is made of, plus optional per-entry `variables`
  and `permissions`. `null` declines a path explicitly. Nothing is globbed or inferred: a file not
  named here is not shipped, and a file named here ships exactly as its entry says. Kept as its own
  top-level directory rather than nested under `src/content/`: a recipe is the thing that names
  sources, so it must not be one.
- `src/scripts/hooks/` — the shared enforcement code, authored once and byte-copied to every ecosystem:
  the canonical frozen-test guard + the ONE generic write-gate adapter (`hercules_gate.py`). This is
  the one domain that stays Python permanently — it ships to and runs on the end user's machine, so
  it can't carry a Node runtime dependency. `tests/scripts/hooks/` is its own island (see § Testing below).
- `src/scripts/tools/` — the shared programs a COMMAND invokes deliberately, as opposed to `src/scripts/hooks/`,
  which the HOST fires on an event. Same stdlib-only Python, byte-copied the same way; the difference
  is the failure posture — a hook fails open, a tool that deletes fails closed. Each tool declares its
  capabilities in `tests/scripts/tools/test_tool_hygiene.py`, and a file with no entry fails the suite.
  `tests/scripts/tools/` is its own island too, packaged per feature.
- `internal/builder/` — the engine that EXECUTES a recipe. `recipe-loader` loads and validates one
  (duplicate keys are scanned in the text before parsing, because `JSON.parse` keeps the last of two
  and says nothing); `recipe-lints` checks every recipe against every source it names, all at once;
  `variable-scope`, `template-engine`, `render-entry`, `write-entry` are the pipeline itself, driven by `build`;
  `dist-diff` compares a fresh render with the committed tree by bytes and by permission bits.
  `bin/recipe` ties them together and is short enough to read in one sitting — deliberately, because
  there is no separate map of the build to keep in step with it.
- `tests/budgets/` — the budgets a shipped instruction file has to meet (token counts, instruction
  counts, loading-chain ceilings). Read only by tests, and deliberately outside the compiled build:
  nothing runs it from `.local/ts-out/`, because measuring a budget IS a test.
- `internal/release/` — ships the builder's output: versioning, changelog, npm packaging, CI smoke/validate
  checks, and the mutation kill-rate report (both its TypeScript and Python halves — the one
  requirement, shipped Python at >=85%, is inline in `internal/release/ci/mutation_report.sh`, and
  only the scheduled report job enforces it).
  `internal/release/ci/` holds the bash glue the GitHub workflows call through
  `make`. `tests/release/` covers all of it.
- `dist/` — generated output, committed and tracked (never git-ignored).
- `tests/` — the top-level tree above, plus two cross-cutting trees that belong to no single domain:
  repo-wide meta-guards (`tests/repo/`) plus the TypeScript test helpers shared across every domain's
  own tests (`tests/support/`).

## Adding a new target

The authoritative contract is [`CODE_OF_CONDUCT.md` § Adding an ecosystem](CODE_OF_CONDUCT.md); this
is the practical checklist. **A new ecosystem is one new JSON file** — the engine has zero
per-ecosystem branches, and in fact zero decisions at all: it executes the recipe. The CI-hard-failing
step that is easy to forget — the write-gate declaration (step 4) — is called out so you do not pass
local `make test` and then hit a late CI failure.

1. **Add `src/targets/<name>.json`** — copy the closest existing recipe and adjust. Start the file
   with `"$schema": "./recipe.schema.json"` and your editor will underline a mistake as you type it;
   the same schema checks the file at build time, naming the place and the expected shape. Four keys:
   - `name` — the directory under `dist/`. It must equal the filename stem.
   - `variables` — what every source rendered for this tool sees. Text, or a real boolean. A value
     may itself contain a `${…}`: that placeholder is not ours to resolve and survives verbatim into
     the shipped file. Use a real `false`, never the string `"false"` — the template engine treats a
     non-empty string as true, so `"false"` would switch a block ON.
   - `runtime_variables` — every `${NAME}` your shipped files are allowed to still contain, because
     the host resolves them at run time.
   - `targets` — one entry per shipped file. `sources` is an ordered list, joined by one blank line.
     Per-entry `variables` override the distribution's key by key; `null` REMOVES a key, so a source
     that then mentions it fails loudly instead of rendering nothing. `permissions` is an octal
     string; absent means 644. A `null` entry says "this tool deliberately ships no such file".
2. **Declare what the tool can do.** Capabilities ARE variables — there is no separate concept.
   Shipped guidance branches on their values (`{% if plan_mode == "tool" %}`), never on a tool's
   name, so declaring them is the whole of it: no edit to any content file. A variable used in a
   CONDITION must be declared by every configuration that renders that source — with `false` when
   the branch is not wanted, never by omission. A lint enforces this and names the file that is
   missing it. Prose describing what THIS tool supports and lacks is a file of its own,
   `src/content/targets/<name>/CAPABILITIES.md`, named by an entry like any other source.
3. **Rebuild and commit**: `make build` regenerates `dist/<name>/`; commit it alongside the source.
   `make build-check` compares a fresh render with the committed tree by bytes AND permission bits.
4. **Declare the write-gate** (CI-hard-failing): add an entry for the target to `GATE_EXPECTATIONS`
   in `tests/scripts/hooks/test_enforcement_gates.py`. `test_every_registered_target_declares_a_gate`
   fails for any registered ecosystem with no declared write-gate (or an explicit, reasoned waiver) —
   a deliberate security forcing-function, so a new target cannot ship ungated by accident. If the
   tool has a pre-write hook, its `hooks/write_gate.json` source is checked against
   `src/targets/recipe.schema.json#/$defs/writeGate` at build time — the same published vocabulary,
   because it is the shape of one declared file rather than a second specification.
5. **Add a smoke entry** to `internal/release/smoke-targets.json` — the CLI, how it is installed, and
   the spec that proves the built plugin loads in it. A distribution with no entry fails the release
   rather than silently skipping its leg.
6. **Add a smoke-checklist section** to `RELEASE.md` for the live behaviours a human confirms before
   release, and any ecosystem-specific expectations to `tests/dist/universalConformance.spec.ts`.

The keystone invariant: `make test` runs `--check` (renders to a temp dir, diffs against the
committed `dist/`, fails on drift) plus the full suite — so a target that does not render
deterministically, or whose output diverges from the committed `dist/`, fails CI immediately.

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

To test the Codex package from a checkout, add that checkout as a local marketplace and install the
Codex-native bundle:

```bash
codex plugin marketplace add /path/to/your/checkout
codex plugin add hercules@mbienkowski
```

The repository's `.agents/plugins/marketplace.json` points Codex at `dist/codex`. Remove an existing
`mbienkowski` marketplace first if Codex resolves the public and local sources ambiguously. For the
released package, use `codex plugin marketplace add mbienkowski/hercules` instead of a local path.

## Naming and contracts

- **Every name is self-explanatory**, following conventions junior and senior recognize: variable names, test names, file names, rule ids, class names. Cryptic ids make review and maintenance harder.
- **Derived contracts, not duplicated lists** (see CODE_OF_CONDUCT.md § Working principles). When two artifacts must agree, a test derives one side from the other's source — so a rename fails loudly, not silently.

## Conventions

- **No comments in code** unless explaining a non-obvious decision.
- All `.md` filenames must be **lowercase** — macOS is case-insensitive but Linux (CI) is not.
- Tests live under the top-level `tests/` tree, mirroring the domain they cover, organised by feature. Exceptions: `tests/scripts/hooks/` and `tests/scripts/tools/` are their own islands (shipped code, stdlib-only Python).
- One version, single-sourced — `package.json` is canonical; `pyproject.toml` is the only other literal and is cross-checked against it.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`). Commit messages are promises (see CODE_OF_CONDUCT.md): if your message claims a gate exists, it must be red-tested to exist.
