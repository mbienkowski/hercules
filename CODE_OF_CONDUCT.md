# Hercules — Code of Conduct

Hercules enforces spec-driven discipline on its users; it holds itself to the same bar. This document
is for **contributors** — the rules for extending Hercules itself. How a user *runs* Hercules (the
workflow, phases, and artifact conventions) lives in the built plugin's `CLAUDE.md` and the
auto-loaded `hercules-reference` skill, authored in [`src/content/`](src/content/).

---

## Development

### Repository layout

Hercules is authored once in a neutral **`src/`** tree and compiled to per-ecosystem plugins under
**`dist/`** (`make build`). **Edit `src/`, never `dist/`** — `dist/` is generated, and CI's drift gate
fails when it is hand-edited or left stale.

- **`src/content/`** — ecosystem-neutral content: `agents/`, `commands/`, `skills/{name}/SKILL.md`,
  `protocols/`, and `persona.md` (the project instructions, rendered to each host's convention —
  Claude Code's `CLAUDE.md`, OpenCode's `instructions.md`).
- **`src/ecosystems/<ecosystem>.json`** — ONE descriptor per ecosystem, the whole target as **data**
  (see **Adding an ecosystem**): token `vars`, `models`, `smoke`, role shapes, routes, inline JSON
  artifacts, guard/gate wiring, named generators. Shipped prose/SVG siblings follow the definitive
  filename schema **`<ecosystem>.dist.<dest>`** (ships byte-identically at plugin-root `<dest>`;
  the directory layout is schema-validated on discovery — a stray file fails the build). No
  per-ecosystem directories, no per-ecosystem code anywhere.
- **`src/hooks/`** — the SHARED enforcement code (stdlib Python, authored once, byte-copied to every
  ecosystem): the canonical frozen-test guard and the one generic write-gate adapter. `src/` holds no
  code the compiler executes — the compiler only copies these for the host to run.
- **`dist/<ecosystem>/`** — the built plugins (generated; the shipped output), one tree per target.

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
- Adds a token-budget row to `tests/testdata/thresholds.json`. Step numbers are integers — no `4a`/`1b`.

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
  in `src/ecosystems/claude-code.json` (CI-verified); each other ecosystem's equivalent gate is
  pinned by its own wiring test under `tests/hooks/` (see § Hooks).
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
- Update the roster in **three places** — the agent list in `src/content/persona.md`, the `advisors[]` array
  in the claude-code descriptor's `settings.json` artifact (`src/ecosystems/claude-code.json`), and
  `_ADVISOR_AGENTS` in `tests/agents/test_agents.py`; a sync test fails on drift.
- **Instruction load is a budget.** Say whose context new content lands in — a delegate's total stays
  under ~150 directives (own file + packet + A2A core + the project CoC). Always-loaded content spends
  everyone's headroom.

### Hooks

Hooks are the plugin's **hard** enforcement — deterministic code the host runs, which a model cannot
rationalise past. All hook code is authored ONCE in `src/hooks/` and byte-copied to every ecosystem;
what differs per host is **descriptor data** (the `guard`/`gate` sections of
`src/ecosystems/<eco>.json`, emitted as `hooks/gate.json` beside the shared adapter). The surfaces:

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
- Every hook ships with executable tests under `tests/hooks/` (scanned for hygiene across all ecosystems)
  plus a wiring test that each target's `hooks.json`/`plugin.js` resolves its command to a real script.

### Adding a skill

Skills are `src/content/skills/{name}/SKILL.md` — each declares a phase-anchored trigger, a
precondition-then-stop guard, and atomic/idempotent writes, and falls back gracefully when a target
project has no `code-of-conduct.md`.

### Adding an ecosystem (target)

One neutral `src/content/` compiles to every ecosystem through ONE generic engine: `cli.build_target`
loops the content once and dispatches through registries populated from the ecosystem descriptors —
it holds **zero** per-ecosystem branches, classes, or modules. **A target is one data file**:

- **Descriptor — `src/ecosystems/<eco>.json`:** the whole target, schema-validated
  (`scripts/build/descriptor.py`): token `vars`; `models` tiers; the `smoke` matrix entry
  (schema-required — a target cannot exist untestable); per-role output shapes (`roles` — named
  serialization modes and field generators); destination `routes` (named kinds); inline JSON
  `artifacts` (native manifests — a `version` field carries the `${version}` token, injected from
  `pyproject.toml` at build, **never** a hand-maintained literal); shared-`guard` modules and
  write-`gate` parameters; rendered `templates`. The vocabulary is **closed**: a descriptor selects
  named, mutation-covered Python behaviors and supplies operands only — an unknown key or enum value
  fails the build loudly at load, naming the allowed set.
- **No executable content in descriptors.** No expressions, interpolation, conditionals, or code
  references beyond the named vocabulary. A target needing behavior the vocabulary lacks gets a
  **new named behavior in `scripts/build/` or `src/hooks/` Python** — mutation-gated, exact-output
  tested — then referenced by name. Genuinely generated text (e.g. OpenCode's `plugin.js`) is a
  `<eco>.template.<dest>` sibling rendered from closed, named computed-value kinds (`js_string`,
  `role_entries_js`, …; the computations are mutation-covered functions in `genextras.py`), never
  inline JSON logic, never auto-discovered code under `src/`. Growing descriptor expressiveness
  instead of adding a named Python behavior is the failure mode to reject in review.
- **Capability disclosures are compiled content.** `CAPABILITIES.md` is authored ONCE in
  `src/content/capabilities.md` — shared claims live in shared lines, host-specific nuance in
  `${target:…}` branches — and compiled per ecosystem like every other content file, so a shared
  claim can never drift between ecosystems. An ecosystem routes it in with an `exact` route (or out
  with `omit` — claude-code, the reference, ships none); conformance and gate-wiring sync tests pin
  the rendered prose against the descriptor data it describes.
- **Siblings — `src/ecosystems/<eco>.dist.<dest>` and `<eco>.template.<dest>`:** binary/marketplace
  files byte-copied to plugin-root `<dest>` (cursor's logo/readme), and text templates rendered to
  `<dest>` (OpenCode's `plugin.js`). The filename IS the routing — the `.dist.`/`.template.` marker
  and dest are validated on discovery, pinned deterministic by tests, no separate mapping to drift.
  No per-ecosystem directories.
- **Enforcement + release:** a `GATE_EXPECTATIONS` entry (or explicit waiver) in
  `tests/hooks/test_enforcement_gates.py` — hand-authored on purpose, the forcing function that a new
  target cannot ship ungated; output-pinning tests under `tests/build/`; a `RELEASE.md` smoke section.

The rule is the same for a trivial ecosystem and a complex one — the complex one just fills in more
of the optional sections. The old "no JSON config DSL" rule stands in spirit: the descriptor is a
config **file**, not a DSL — control flow stays typed, mutation-covered Python; `src/` stays data the
compiler only reads (and `src/hooks/` code it only copies). The committed-dist drift gate (`--check`)
is what proves a descriptor reproduces the intended bytes.

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

Enforced by `tests/` — a change that breaks one fails CI:

- **Every shipped artifact has an owning test.** A new manifest, agent, command, or skill ships only with
  a test that fails when it is missing or malformed.
- **The plugin version is single-sourced** — `pyproject.toml` is the canonical version of record
  (`read_canonical_version`); `package.json` is the only other literal (npm/OpenCode read it as-is) and
  is cross-checked against pyproject every CI `validate` run. The two are the whole canonical list
  (`scripts/build/version_targets.py::VERSION_TARGETS`). Every ecosystem's versioned manifest (a
  `"versioned": true` artifact in `src/ecosystems/<ecosystem>.json`) carries a `${version}` **token**,
  not a literal — a human never sees a version to hand-bump under `src/`; the build injects the canonical
  version into each `dist/…/plugin.json` (fail-loud if the token is absent or duplicated). Tests assert
  every shipped manifest equals the canonical version and that no `${…}` token survives. Literal version sources are build *inputs* (`pyproject.toml`, `package.json`), never `dist/`
  outputs (a `dist/` file would be regenerated from `src/` on the next build).
- **Red first, red possible forever.** A new test is born failing — write it before the feature, watch it
  fail for the right reason, then make it pass. Anchor it so it stays able to fail; `"auto" in lower`
  stays green on "automatically" — that's decoration, not a test.
- **Pin both ends of a cross-file contract** — writer and reader, or one sync test. A reader-only pin
  stays green while the deleted writer bricks the product.
- **CI is Makefile-driven — no inline code in workflows.** Every GitHub Actions `run:` step is a single
  `make <target>`; the logic lives in the `Makefile` and `scripts/ci/`, so it is one source of truth,
  testable, and runnable locally. A new CI step adds a `make` target + a `scripts/ci/` helper, never an
  inline YAML heredoc or multi-line shell. Enforced by `tests/build/test_workflows_use_make.py`.

---

## Documentation style

Every doc, README, and diagram describes the **present state — what exists now**. No before/after,
changelog narrative, or "previously / today / used to / new vs old" framing — history lives in `git diff`
and the generated `CHANGELOG.md`.

- Prefer **bullets over prose** for anything a contributor scans — one bullet per rule, the term in bold.
- **One reading only** — every sentence admits exactly one interpretation; if it reads two ways, split or reword it.
- **160-character** hard line cap on new and edited content (table rows, long URLs, the HTML diagram's
  markup, and YAML values are the only exemptions).
- **Prose is pinned.** Most sentences in `src/content/` are pinned by tests — `grep tests/` for a sentence
  before rewording it; CI fails on silent drift.

---

## Testing

One language, one runner: **Python**. Everything is a pytest test under `python -m pytest tests/` — the
code tests plus the plugin-content lint and the A2A/metric budgets.

```bash
pip install -e ".[dev]"   # once
make test                 # CI gate: >= 90% branch coverage
make test-mutation        # CI gate: >= 90% mutation kill rate
```

Hercules holds itself to the bar it enforces on its users: **>= 90% branch coverage** and a **>= 90%
mutation kill rate**, both gated in CI on every PR.

- **A surviving mutant is a verdict** — a missing test (write it) or a better behaviour than the code
  (adopt it). Never a `# pragma: no mutate` to silence it; that pragma is allowed only on static strings
  whose mutants are all behaviourally equivalent, never on a branch, comparison, or return value.
- **One target per test.** Each test asserts one behaviour; split any test longer than 20 lines, and
  any test file longer than 500 lines.
- **Pin the product, not this guide.** Tests pin commands, agents, protocols, and hooks — the enforced
  surfaces; this document stays editable and is not itself pinned sentence-by-sentence.
- **Budgets are fixed.** The token/instruction budgets in `tests/testdata/thresholds.json` are quality
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

Token counts use `tiktoken` (cl100k_base); the encoding is fetched once and cached. Set
`TIKTOKEN_CACHE_DIR` to a persistent directory to run the suite offline (CI caches it there).

### Golden files

The injected A2A Core is pinned byte-for-byte in `tests/testdata/core.golden`. After an intentional edit,
re-bless it from the failing test's expected value. All methodology checks are gates, not warnings — a
failing gate means the change broke a contract; fix the contract, not the test.
