# Hercules — Code of Conduct

Hercules enforces spec-driven discipline on its users; it holds itself to the same bar. This document
is for **contributors** — the rules for extending Hercules itself. How a user *runs* Hercules (the
workflow, phases, and artifact conventions) lives in the built plugin's `CLAUDE.md` and the
auto-loaded `hercules-reference` skill, authored in [`src/content/`](src/content/).

---

## Development

### Repository layout

Every top-level directory is a **domain**, not a language or a category — nothing is named `ts`,
`py`, `scripts`, or similar. A domain that has tests owns them directly, in its own `tests/`.

Hercules is authored once (in `src/content/`, `src/targets/`, and `src/hooks/`) and compiled to per-ecosystem
plugins under **`dist/`** (`make build`). **Edit the source domains, never `dist/`** — `dist/` is
generated, and CI's drift gate fails when it is hand-edited or left stale.

- **[`src/content/`](src/content/)** — the product: ecosystem-neutral content (`agents/`, `commands/`,
  `skills/{name}/SKILL.md`, `protocols/`, and `persona.md` — the project instructions, rendered to
  each host's convention: Claude Code's `CLAUDE.md`, OpenCode's `instructions.md`). `src/content/tests/`
  covers the built plugin content itself.
- **[`src/targets/`](src/targets/)`/<ecosystem>.json`** — ONE descriptor per ecosystem, the whole target
  as **data** (see **Adding an ecosystem**): token `vars`, `models`, `smoke`, role shapes, routes,
  inline JSON artifacts, guard/gate wiring, named generators. Shipped prose/SVG siblings follow the
  definitive filename schema **`<ecosystem>.dist.<dest>`** (ships byte-identically at plugin-root
  `<dest>`; the directory layout is schema-validated on discovery — a stray file fails the build). No
  per-ecosystem directories, no per-ecosystem code anywhere. Kept as its own top-level domain rather
  than nested under `src/content/`: the builder's content walk is recursive, so a descriptor sitting
  inside `src/content/` would be swept up as if it were content to render.
- **[`src/hooks/`](src/hooks/)** — the SHARED enforcement code (stdlib Python, authored once, byte-copied to
  every ecosystem): the canonical frozen-test guard and the one generic write-gate adapter. This
  domain holds no code the compiler executes — the compiler only copies these for the host to run.
  `src/hooks/tests/` is its own island (see § Testing).
- **[`src/builder/`](src/builder/)** — the generic compiler that turns `src/content/` + `src/targets/` into
  `dist/`. `src/builder/tests/` covers it.
- **[`src/release/`](src/release/)** — ships the builder's output: versioning, changelog, npm packaging, CI
  smoke/validate checks, the mutation-kill-rate gate, and the bash glue the GitHub workflows call
  through `make` (`src/release/ci/`). `src/release/tests/` covers it.
- **[`src/metrics/`](src/metrics/)** — instruction/token budgets, A2A grammar checks, loading-chain gates.
  `src/metrics/tests/` covers it.
- **`dist/<ecosystem>/`** — the built plugins (generated; the shipped output), one tree per target.
- **[`src/commons/`](src/commons/)** — cross-cutting test infrastructure that belongs to no single
  domain: repo-wide meta-guards (`src/commons/repo/`) plus the TypeScript test helpers shared across
  every domain's own `tests/` (`src/commons/support/`).

Paths below name the **source** you edit; the compiler places the built copy under `dist/`.

### Working principles

- **Look 2–3 steps ahead.** Judge a change by what it forecloses; a narrow fix that blocks a likely
  future need loses to the more general approach.
- **Propose a change in five parts, in order:** quote the original, show the after, link the file(s),
  state the need, state the approach.
- **New files** state their purpose and structure up front and use self-descriptive, case-safe names.
- **Single source of truth.** Each fact has one owning file; every other place references or injects
  it, never restates it as its own source.

### Adding a command

Commands are `src/content/commands/{name}.md` (lowercase — macOS is case-insensitive, Linux is not). Each:

- Carries its `/hercules:{name}` trigger phrase and uses `YYYY-MM-DD` dates in every artifact path.
- Opens in plan mode and ends at one **Plan approval** gate, exiting with `ExitPlanMode` (`auto`);
  read-only or utility skills may omit plan mode.
- Points forward to the next phase at close-out and updates the workflow table in `src/content/persona.md`.
- Adds a token-budget row to `src/metrics/tests/testdata/thresholds.json`. Step numbers are integers — no `4a`/`1b`.

### Changing the workflow

The workflow lives in four files, each owning one thing:

- **protocol** (`src/content/protocols/workflow-protocol.md`) — the source of truth for step order, hard
  guardrails, and the delegation packet (`#packet`);
- **commands** (`src/content/commands/*.md`) — operational prose and state mechanics, composing that packet per spawn;
- **`src/content/persona.md`** (user-facing overview) and **`src/content/skills/hercules-reference/SKILL.md`** (the state schema);
- **diagram** (`docs/workflow/workflow-diagram-detailed.html`) — the picture.

Keep them in lock-step:

- Any change to a phase or step — its definition, wording, or order — lands in the protocol's phase
  list / guardrail registry first, with the command and the detailed diagram never lagging it **in the
  same change** (persona.md follows only when the state schema or overview changes). A `hook`-class
  registry row must match a live matcher in the **reference** gate — the `hooks/hooks.json` artifact
  in `src/targets/claude-code.json` (CI-verified); each other ecosystem's equivalent gate is
  pinned by its own wiring test under `src/hooks/tests/` (see § Hooks).
- If the change is visible at the four-phase level, also update the simplified diagram, the README
  (end-user overview), and `CONTRIBUTING.md` (if the contributor workflow is affected).

### The execution walk

Commands are executed, not read. Before merging a command change, walk it step-by-step as the runtime
agent:

- Does the data each step reads exist yet? Is the tool allowed in this mode (plan mode blocks writes)?
  Can the shell command succeed on a fresh repo (`git rm` fails on uncommitted files)?
- A crash at any step boundary must leave a state the resume path recovers.
- A gate must be satisfiable by what it gates — a "must fail" gate can't judge a rightly-green corrected test.

### Changing what something means

A behaviour change is done when the old meaning is **extinct**, not when the new one is written:

- List every surface stating the old meaning — commands, `src/content/persona.md`, templates, agents, hook
  messages, README, diagrams, tests, and protocols — and update each.
- Grep the **concept**, not the string; old meanings hide in paraphrase.

### Adding an agent

Agents are `src/content/agents/{name}.md` (lowercase). They carry **no hardcoded stack** (project variance
lives in each project's `code-of-conduct.md`) and **no Hercules-internal literals** (`/hercules:*`,
state fields like `current_spec`/`tier`, `*-spec-NN-*.md`) — that knowledge is injected at call time.
Exception: `hercules.md`, the orchestrator persona.

- A spec is read-only / write-once / **delete-once** (`git rm` at delivery); under a keep-specs
  code-of-conduct the orchestrator refreshes it once at retire instead. An agent never updates a spec.
- Replies follow the A2A `§ Agent-Injected Core` (`src/content/protocols/a2a-communication-protocol.md`).
- Update the roster in **two places** — the agent list in `src/content/persona.md` and the
  `advisors[]` array in the claude-code descriptor's `settings.json` artifact
  (`src/targets/claude-code.json`) — `src/builder/tests/guards/rosterSync.spec.ts` reads the compiled
  `settings.json` roster directly and fails on drift, so there is no third place to keep in sync.
- **Instruction load is a budget.** Say whose context new content lands in — a delegate's total stays
  under ~150 directives (own file + packet + A2A core + the project CoC). Always-loaded content spends
  everyone's headroom.

### Hooks

> **LOCKED.** `src/hooks/` stays Python, stdlib-only, forever — this is not a migration-in-progress
> state. Every other executable domain in this repo (`src/builder/`, `src/release/`, `src/metrics/`, and their
> tests) is TypeScript; hooks are the one deliberate, permanent exception. Porting them would force a
> Node runtime dependency onto every consumer across all six ecosystems, for code whose entire job is
> running unmodified, byte-identical, on whatever the host ships. Do not "finish the migration" here.

Hooks are the plugin's **hard** enforcement — deterministic code the host runs, which a model cannot
rationalise past. All hook code is authored ONCE in `src/hooks/` and byte-copied to every ecosystem;
what differs per host is **descriptor data** (the `guard`/`gate` sections of
`src/targets/<eco>.json`, emitted as `hooks/gate.json` beside the shared adapter). The surfaces:

- **Claude Code** — a `PreToolUse` hook (the canonical guard itself, wired by the descriptor's
  `hooks.json` artifact) denies a write before it lands. The reference gate.
- **OpenCode** — a generated `tool.execute.before` hook (in `plugin.js`) throws to abort a frozen edit
  before disk — a real pre-write veto. It shells to the byte-identical canonical guard, not a re-port.
- **Gemini CLI / Copilot CLI** — the generic adapter's `pre_tool` protocol: the host's `BeforeTool`/
  `preToolUse` event is mapped through the descriptor's tool map onto the canonical guard, a true
  pre-write veto; the host's decision shapes (deny/allow JSON) are descriptor data.
- **Cursor** — the generic adapter's `event_guards` protocol: `beforeShellExecution`/
  `beforeMCPExecution` **deny** a frozen write/commit (a coarse guardrail — reads are not blocked; the
  agent must read the test it makes pass). Since `afterFileEdit` is notification-only, the edit path is
  **runtime-aware**: **advisory** in the interactive IDE (a loud notice, **no** working-tree mutation —
  the human owns their tree and decides), and an automatic `git checkout` restore only in **headless**
  `cursor-agent` runs (`HERCULES_RUNTIME_MODE=headless`, no human present). Behind the advisory IDE path
  is the **acceptance gate** (§ Build): frozen tests are re-hashed against a baseline before a spec
  retires, catching a tamper at acceptance. Its check is deterministic, but its invocation is
  prompt-enforced like the other Build gates — a strong catch, not an unbypassable lock (honest scope).

Shared rules for every hook, on every ecosystem:

- **Stdlib-only Python, no shebang** — invoked as `python3 <script>` (exec-form `args`, or a `command`
  string on hosts that require it); no jq/bash dependency, cross-platform. The `${…_PLUGIN_ROOT}` env var
  is the host's, e.g. `${CLAUDE_PLUGIN_ROOT}` / `${CURSOR_PLUGIN_ROOT}`.
- **Read-only over `~/.hercules`, fail-open** — a hook never writes state (it would race the model's
  atomic writes) and allows the action whenever no active build resolves — or no `python3` is found. It
  must never crash a user's edit. The **one** sanctioned working-tree mutation is Cursor's disclosed
  after-edit `git checkout` restore in **headless** runs (`afterFileEdit` is notification-only, so it
  cannot block the landed edit — Cursor's generic `preToolUse` deny hook is unverified for the Composer
  path and not relied on; no human is present headless to act on a notice); it goes through git, never a
  direct write, is bounded to restoring the frozen path,
  and reports success **only when git actually restored it** — never a false "reverted" claim on an
  untracked file or non-git tree. In the interactive IDE the after-edit path is **advisory only** (no
  mutation).
- **Honest scope.** A hook reads model-authored state, so it is **runtime-mediated, not tamper-proof** —
  say so, never "unbypassable"; disclose the per-ecosystem limits in the compiled `CAPABILITIES.md`
  (authored in `src/content/capabilities.md`: fail-open without `python3`; Cursor's revert-only
  Composer path). User-granted overrides (`frozen_override`, `frozen_hook: "off"`) are recorded
  state, not holes.
- **Single source of truth.** The frozen-guard state reader (`hercules_state.py`) is authored once and
  shipped byte-identical to every ecosystem (a build-time copy, pinned by a byte-identity test).
- Every hook ships with executable tests under `src/hooks/tests/` (scanned for hygiene across all ecosystems)
  plus a wiring test that each target's `hooks.json`/`plugin.js` resolves its command to a real script.

### Adding a skill

Skills are `src/content/skills/{name}/SKILL.md` — each declares a phase-anchored trigger, a
precondition-then-stop guard, and atomic/idempotent writes, and falls back gracefully when a target
project has no `code-of-conduct.md`.

### Adding an ecosystem (target)

One neutral `src/content/` compiles to every ecosystem through ONE generic engine: `buildTarget`
loops the content once and dispatches through registries populated from the ecosystem descriptors —
it holds **zero** per-ecosystem branches, classes, or modules. **A target is one data file**:

- **Descriptor — `src/targets/<eco>.json`:** the whole target, schema-validated
  (`src/builder/descriptor.mts`): token `vars`; `models` tiers; the `smoke` matrix entry
  (schema-required — a target cannot exist untestable); per-role output shapes (`roles` — named
  serialization modes and field generators); destination `routes` (named kinds); inline JSON
  `artifacts` (native manifests — a `version` field carries the `${version}` token, injected from
  `package.json` at build, **never** a hand-maintained literal); shared-`guard` modules and
  write-`gate` parameters; rendered `templates`. The vocabulary is **closed**: a descriptor selects
  named, mutation-covered behaviors and supplies operands only — an unknown key or enum value fails
  the build loudly at load, naming the allowed set.
- **No executable content in descriptors.** No expressions, interpolation, conditionals, or code
  references beyond the named vocabulary. A target needing behavior the vocabulary lacks gets a
  **new named behavior in `src/builder/` or `src/hooks/`** — mutation-gated, exact-output
  tested — then referenced by name. Genuinely generated text (e.g. OpenCode's `plugin.js`) is a
  `<eco>.template.<dest>` sibling rendered from closed, named computed-value kinds (`js_string`,
  `role_entries_js`, …; the computations are mutation-covered functions in `genExtras.mts`), never
  inline JSON logic, never auto-discovered code under `src/content/`. Growing descriptor expressiveness
  instead of adding a named behavior is the failure mode to reject in review.
- **Capability disclosures are compiled content.** `CAPABILITIES.md` is authored ONCE in
  `src/content/capabilities.md` — shared claims live in shared lines, host-specific nuance in
  `${target:…}` branches — and compiled per ecosystem like every other content file, so a shared
  claim can never drift between ecosystems. An ecosystem routes it in with an `exact` route (or out
  with `omit` — claude-code, the reference, ships none); conformance and gate-wiring sync tests pin
  the rendered prose against the descriptor data it describes.
- **Siblings — `src/targets/<eco>.dist.<dest>` and `<eco>.template.<dest>`:** binary/marketplace
  files byte-copied to plugin-root `<dest>` (cursor's logo/readme), and text templates rendered to
  `<dest>` (OpenCode's `plugin.js`). The filename IS the routing — the `.dist.`/`.template.` marker
  and dest are validated on discovery, pinned deterministic by tests, no separate mapping to drift.
  No per-ecosystem directories.
- **Enforcement + release:** a `GATE_EXPECTATIONS` entry (or explicit waiver) in
  `src/hooks/tests/test_enforcement_gates.py` — hand-authored on purpose, the forcing function that a new
  target cannot ship ungated; output-pinning tests under `src/builder/tests/`; a `RELEASE.md` smoke section.

The rule is the same for a trivial ecosystem and a complex one — the complex one just fills in more
of the optional sections. The old "no JSON config DSL" rule stands in spirit: the descriptor is a
config **file**, not a DSL — control flow stays typed, mutation-covered code; `src/content/` and
`src/targets/` stay data the compiler only reads (and `src/hooks/` code it only copies). The
committed-dist drift gate (`--check`) is what proves a descriptor reproduces the intended bytes.

### Failure moments

Users judge the product at its stops, not its happy path:

- Every stop, refusal, or block gets a **scripted** message naming the next action — never a bare problem
  statement or an internal field name as the remedy.
- Name only exits that exist; a recipe must satisfy **its own validator** (code checks four fields → the
  message names four).
- A mechanism described on several surfaces has ONE **canonical** list; every echo matches verbatim.

### Branching

- **Branch names must not contain slashes** — a `/` makes git nest refs under `.git/refs/heads/` and
  blocks a later branch from reusing that name. Use **hyphens**: `claude-feature-x`, not `claude/feature-x`.

### Invariants

Enforced by the test suite (every domain's own `tests/`, plus `src/hooks/tests/`) — a change that breaks
one fails CI:

- **Every shipped artifact has an owning test.** A new manifest, agent, command, or skill ships only with
  a test that fails when it is missing or malformed.
- **The plugin version is single-sourced** — `package.json` is the canonical version of record
  (`readCanonicalVersion`); `pyproject.toml` is the only other literal (setuptools reads it as-is) and
  is cross-checked against package.json every CI `validate` run. The two are the whole canonical list
  (`src/builder/versionTargets.mts::VERSION_TARGETS`). Every ecosystem's versioned manifest (a
  `"versioned": true` artifact in `src/targets/<ecosystem>.json`) carries a `${version}` **token**,
  not a literal — a human never sees a version to hand-bump under `src/content/`; the build injects the canonical
  version into each `dist/…/plugin.json` (fail-loud if the token is absent or duplicated). Tests assert
  every shipped manifest equals the canonical version and that no `${…}` token survives. Literal version sources are build *inputs* (`pyproject.toml`, `package.json`), never `dist/`
  outputs (a `dist/` file would be regenerated from source on the next build).
- **Red first, red possible forever.** A new test is born failing — write it before the feature, watch it
  fail for the right reason, then make it pass. Anchor it so it stays able to fail; `"auto" in lower`
  stays green on "automatically" — that's decoration, not a test.
- **Pin both ends of a cross-file contract** — writer and reader, or one sync test. A reader-only pin
  stays green while the deleted writer bricks the product.
- **CI is Makefile-driven — no inline code in workflows.** Every GitHub Actions `run:` step is a single
  `make <target>`; the logic lives in the `Makefile` and `src/release/ci/`, so it is one source of truth,
  testable, and runnable locally. A new CI step adds a `make` target + a `src/release/ci/` helper, never an
  inline YAML heredoc or multi-line shell. Enforced by `src/release/tests/pipeline/releasePipeline.spec.ts`.

---

## Documentation style

Every doc, README, and diagram describes the **present state — what exists now**. No before/after,
changelog narrative, or "previously / today / used to / new vs old" framing — history lives in `git diff`
and the generated `CHANGELOG.md`.

- Prefer **bullets over prose** for anything a contributor scans — one bullet per rule, the term in bold.
- **One reading only** — every sentence admits exactly one interpretation; if it reads two ways, split or reword it.
- **160-character** hard line cap on new and edited content (table rows, long URLs, the HTML diagram's
  markup, and YAML values are the only exemptions).
- **Prose is pinned.** Most sentences in `src/content/` are pinned by tests — `grep content/tests/` for a
  sentence before rewording it; CI fails on silent drift.

---

## Testing

Two runtimes, two runners, one bar. **Python** is the island: `src/hooks/` — the enforcement code
shipped to users, stdlib-only, no runtime dependency to impose on a consumer (see § Hooks) — and
nothing else. **TypeScript** is everything else executable: the compiler (`src/builder/`), the
CI/release scripts (`src/release/`), the plugin-content lint (`src/content/tests/`), and the A2A/metric
budgets (`src/metrics/`) — each domain carrying its own `tests/`.

```bash
make install         # once: pip install -e ".[dev]" + npm ci
make test             # CI gate: >= 90% branch coverage, BOTH runtimes independently
make test-mutation    # CI gate: >= 90% mutation kill rate, BOTH runtimes independently
```

`test`/`test-mutation` are each a thin wrapper over `test-py` + `test-ts` / `mutation-py` +
`mutation-ts` — the split is real, not cosmetic: CI runs each pair as **separate, parallel jobs**
(`mutation-py` and `mutation-ts` in particular used to be one ~40min sequential job; splitting them
by runtime, each provisioning only the toolchain it needs, is what makes them run concurrently). The
`-py`/`-ts` suffix is the same string in the make target, the CI job id, and the CI display name —
a red check can be reproduced by copying its name straight into a terminal.

Hercules holds itself to the bar it enforces on its users: **>= 90% branch coverage** and a **>= 90%
mutation kill rate**, gated in CI on every PR, for **each** runtime independently — a strong
TypeScript suite does not excuse a weak Python one, or vice versa.

- **A surviving mutant is a verdict** — a missing test (write it) or a better behaviour than the code
  (adopt it). Never a `# pragma: no mutate` to silence it; that pragma is allowed only on static strings
  whose mutants are all behaviourally equivalent, never on a branch, comparison, or return value.
- **One target per test.** Each test asserts one behaviour; split any test longer than 20 lines, and
  any test file longer than 500 lines.
- **Pin the product, not this guide.** Tests pin commands, agents, protocols, and hooks — the enforced
  surfaces; this document stays editable and is not itself pinned sentence-by-sentence.
- **Budgets are fixed.** The token/instruction budgets in `src/metrics/tests/testdata/thresholds.json` are quality
  gates, not obstacles — every token a command, agent, or skill carries is consumed on every run,
  eating the context an AI agent needs to edit code well, so more tokens mean lower output quality.
  Never silently raise a threshold or cut content to fit: surface the breach, propose at least three
  options, and let the maintainer choose. Edit a budget **only on a direct user request to bump it** —
  that is the single sanctioned path, reserved for a genuinely planned increase. An agent never bumps a
  budget by default, on its own initiative, or as a side effect of another approved change; absent an
  explicit "raise this budget" instruction, treat every threshold as immovable and fit the change to it.
- **Assert the present state, not the past** — pair every absence check with a positive companion
  assertion or a named, ongoing risk it guards, or it is cosmetic.
- **Prove it works, don't assert it "should."** A green suite is necessary, not sufficient — verify a
  change end-to-end with a real run before calling it done. The suite can't inspect Claude Code's
  permission mode, so at release time drive `/hercules:workflow` by hand against a throwaway repo and
  confirm the four phases produce their artifacts in order. That manual smoke is a release check, not
  a CI gate — the full per-ecosystem checklist lives in [`RELEASE.md`](RELEASE.md).

### Tokens

Token counts use `js-tiktoken` (cl100k_base), imported as `js-tiktoken/lite` +
`js-tiktoken/ranks/cl100k_base` so the encoding's ranks are bundled at install time — no runtime
fetch, no cache directory, and the suite runs offline by construction. Exact-pinned in
`package.json` (never a caret range): a tokenizer dependency bump is exactly the kind of change that
can silently move the counts `src/metrics/tests/testdata/thresholds.json` gates on, so a bump is a reviewable,
Dependabot-proposed PR, never an invisible transitive update.

### Golden files

The injected A2A Core is pinned byte-for-byte in `src/content/tests/core.golden`. After an intentional edit,
re-bless it from the failing test's expected value. All methodology checks are gates, not warnings — a
failing gate means the change broke a contract; fix the contract, not the test.

### Complexity

```bash
make complexity-scan   # local SonarQube-style scan, BOTH runtimes
```

No first-party function may exceed **15** on either **cyclomatic** (independent paths) or **cognitive**
(SonarSource's nesting-aware) complexity. Cognitive is the metric that matters most — it charges extra
for each level of nesting, so it is what catches "a junior can't follow these nested loops"; 15 is
SonarQube's own default. Cyclomatic is a cheap second opinion in the same run. The **same 15** governs
both runtimes, so neither can hide a hotspot the other would reject:

- **TypeScript** (`src/builder/`, `src/release/`, `src/metrics/`) — ESLint, config and ceiling in
  [`eslint.config.mjs`](eslint.config.mjs): the core `complexity` rule plus `sonarjs/cognitive-complexity`.
- **Python** (`src/hooks/`) — flake8 restricted to its two complexity checks (`C901` mccabe cyclomatic,
  `CCR001` cognitive); no style rules run.

Tests are excluded on both sides: a table-driven, assertion-dense spec is legitimately branchy and is not
shipped — the gate guards the product code a maintainer reads under pressure. The complexity linters are
**exact-pinned** (`package.json`, `pyproject.toml`) for the same reason the tokenizer is: a linter can
move its scores between releases, and a gate whose verdict shifts on a silent bump is not a gate.

**Fix a breach by extracting named helpers, never by raising the ceiling** — a function over 15 is telling
you its steps want names a junior can read. Same doctrine as the budgets: the number is immovable; the
code moves to fit it.

CI runs `make complexity-scan` as its own `complexity-scan` job on **every commit**, in the same fast
tier as `test`/`validate`/`smoke` — it `needs: [build]` only (it lints source, not the compiled
output), so it runs **in parallel** with the correctness jobs, never gated behind them. Mutation is the
only job that waits (it `needs:` all five fast checks) and the only one that is main-only. So a
complexity regression is caught on the commit that introduces it, right alongside the tests.

### Dependencies

```bash
make vulnerability-scan   # fail on any HIGH or CRITICAL dependency CVE
```

npm carries the **entire** dependency surface: the shipped plugin declares zero runtime dependencies and
the Python hooks are stdlib-only (`dependencies = []` in `pyproject.toml`), so there is no pip
runtime-CVE surface — the whole exposure is the dev toolchain in `package-lock.json`. `npm audit
--audit-level=high` exits non-zero on high/critical only; moderate and low stay visible but do not block.
CI runs it as the `vulnerability-scan` job on every commit, in the same fast tier as `complexity-scan`
and `test`/`validate`/`smoke` (it `needs: [build]` only, running in parallel with them). A flagged
advisory is fixed by bumping to the patched version (Dependabot proposes these as reviewable,
exact-pinned PRs) — never by lowering `--audit-level`.
