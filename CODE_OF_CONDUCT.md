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
- **`src/targets/<ecosystem>/`** — an ecosystem's **data**: a `config.json` (token `vars`), a
  `smoke.json`, an optional versioned manifest, an optional `hooks/` dir on any host that supports
  enforcement (`claude-code`, `cursor`), and an optional `CAPABILITIES.md` (disclosed gaps, prose). The
  small per-ecosystem build **code** — its `Serializer` and `Target` — lives under `scripts/build/`
  (see **Adding an ecosystem**), not here; `src/` holds no code the compiler executes.
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
  registry row must match a live matcher in the **reference** gate,
  `src/targets/claude-code/hooks/hooks.json` (CI-verified); each other ecosystem's equivalent gate is
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
  in `src/targets/claude-code/settings.json`, and `_ADVISOR_AGENTS` in `tests/agents/test_agents.py`; a sync test fails
  on drift.
- **Instruction load is a budget.** Say whose context new content lands in — a delegate's total stays
  under ~150 directives (own file + packet + A2A core + the project CoC). Always-loaded content spends
  everyone's headroom.

### Hooks

Hooks are the plugin's **hard** enforcement — deterministic code the host runs, which a model cannot
rationalise past. They ship **per ecosystem, wherever the host offers an enforcement surface**, all keyed
off the same frozen-guard state so no logic is reimplemented per target:

- **Claude Code** — a `PreToolUse` hook (`src/targets/claude-code/hooks/`, auto-loaded via `hooks.json`)
  denies a write before it lands. The reference gate.
- **OpenCode** — a generated `tool.execute.before` hook (in `plugin.js`) throws to abort a frozen edit
  before disk — a real pre-write veto. It shells to the byte-identical Claude guard, not a re-port.
- **Cursor** — a `hooks.json` adapter (`src/targets/cursor/hooks/`) that `beforeShellExecution`/
  `beforeReadFile` **denies** a frozen write/read, and — since `afterFileEdit` is notification-only —
  reverts a frozen edit after the fact as a disclosed backstop.

Shared rules for every hook, on every ecosystem:

- **Stdlib-only Python, no shebang** — invoked as `python3 <script>` (exec-form `args`, or a `command`
  string on hosts that require it); no jq/bash dependency, cross-platform. The `${…_PLUGIN_ROOT}` env var
  is the host's, e.g. `${CLAUDE_PLUGIN_ROOT}` / `${CURSOR_PLUGIN_ROOT}`.
- **Read-only over `~/.hercules`, fail-open** — a hook never writes state (it would race the model's
  atomic writes) and allows the action whenever no active build resolves — or no `python3` is found. It
  must never crash a user's edit. The **one** sanctioned working-tree mutation is Cursor's disclosed
  after-edit `git checkout` revert (a host with no pre-write veto); it goes through git, never a direct
  write, and is bounded to restoring the frozen path.
- **Honest scope.** A hook reads model-authored state, so it is **runtime-mediated, not tamper-proof** —
  say so, never "unbypassable"; disclose the per-ecosystem limits in `CAPABILITIES.md` (fail-open without
  `python3`; Cursor's revert-only Composer path). User-granted overrides (`frozen_override`,
  `frozen_hook: "off"`) are recorded state, not holes.
- **Single source of truth.** The frozen-guard state reader (`hercules_state.py`) is authored once and
  shipped byte-identical to every ecosystem (a build-time copy, pinned by a byte-identity test).
- Every hook ships with executable tests under `tests/hooks/` (scanned for hygiene across all ecosystems)
  plus a wiring test that each target's `hooks.json`/`plugin.js` resolves its command to a real script.

### Adding a skill

Skills are `src/content/skills/{name}/SKILL.md` — each declares a phase-anchored trigger, a
precondition-then-stop guard, and atomic/idempotent writes, and falls back gracefully when a target
project has no `code-of-conduct.md`.

### Adding an ecosystem (target)

One neutral `src/content/` compiles to every ecosystem through a generic engine: `cli.build_target`
loops the content once and dispatches through two registries — it holds **zero** per-ecosystem
branches, so onboarding a target is additive, never an edit to the orchestrator. A target is **data +
one or two small code registrations**, in this fixed shape:

- **Data — `src/targets/<eco>/`:** `config.json` (token `vars`); `smoke.json` (its CLI + install method
  + smoke-test path — CI-hard-failing if absent); optional `plugin.json` (a native manifest, added to
  `scripts/build/version_targets.py::VERSION_TARGETS`); optional `hooks/` (the write-gate adapter);
  optional `CAPABILITIES.md` (disclosed gaps — plain prose, **never** a Python string literal).
- **Content transform — `scripts/build/serialize.py`:** one `Serializer` subclass, `register()`-ed.
  This is genuine per-ecosystem *behaviour* (which frontmatter keys survive, how the body renders) and
  stays code — it carries the mutation gate. It is the one irreducible code touch every target needs.
- **Non-content extras — `scripts/build/targets/<eco>.py`:** one `register(Target(...))` — its
  `renames`/`dest_fn` (destination routing) and `emit_extras_fn`. Copies/shared-hook/CAPABILITIES
  plumbing goes through the shared helpers (`emit.copy_map`, `targets.base.emit_shared`); write bespoke
  code here **only** for genuinely generated output (e.g. OpenCode's `plugin.js`). A target with no
  extras beyond copies needs just the one `register()` call.
- **Enforcement + release:** a `GATE_EXPECTATIONS` entry (or explicit waiver) in
  `tests/hooks/test_enforcement_gates.py` — hand-authored on purpose, the forcing function that a new
  target cannot ship ungated; output-pinning tests under `tests/build/`; a `RELEASE.md` smoke section.

The rule is the same for a trivial ecosystem and a complex one — the complex one just fills in more of
the optional parts (a `hooks/` dir, a bespoke `emit_extras`). Do **not** invent a JSON config DSL for
the serializer, or auto-discovered executable code under `src/`: control-flow stays typed,
mutation-covered Python; `src/` stays data the compiler only reads.

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
- **The plugin version is single-sourced** — `pyproject.toml`, `package.json`, and every ecosystem's
  versioned manifest (`src/targets/<ecosystem>/plugin.json`, e.g. `claude-code`, `cursor`) carry the same
  version; the canonical list is `scripts/build/version_targets.py`. The build propagates it into `dist/`
  and CI fails on drift. Version targets are build *sources*, never `dist/` outputs (a `dist/` file would
  be regenerated from `src/` on the next build).
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
