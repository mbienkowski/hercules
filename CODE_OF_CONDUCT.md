# Hercules — Code of Conduct

Hercules enforces spec-driven discipline on its users; it holds itself to the same bar. This document
is for **contributors** — the rules for extending Hercules itself. How a user *runs* Hercules (the
workflow, phases, and artifact conventions) lives in [`plugin/CLAUDE.md`](plugin/CLAUDE.md).

---

## Development

### Working principles

- **Look 2–3 steps ahead.** Judge a change by what it forecloses; a narrow fix that blocks a likely
  future need loses to the more general approach.
- **Propose a change in five parts, in order:** quote the original, show the after, link the file(s),
  state the need, state the approach.
- **New files** state their purpose and structure up front and use self-descriptive, case-safe names.
- **Single source of truth.** Each fact has one owning file; every other place references or injects
  it, never restates it as its own source.

### Adding a command

Commands are `plugin/commands/{name}.md` (lowercase — macOS is case-insensitive, Linux is not). Each:

- Carries its `/hercules:{name}` trigger phrase and uses `YYYY-MM-DD` dates in every artifact path.
- Opens in plan mode and ends at one **Plan approval** gate, exiting with `ExitPlanMode` (`auto`);
  read-only or utility skills may omit plan mode.
- Points forward to the next phase at close-out and updates the workflow table in `plugin/CLAUDE.md`.
- Adds a token-budget row to `tests/testdata/thresholds.json`. Step numbers are integers — no `4a`/`1b`.

### Changing the workflow

The workflow lives in four files, each owning one thing:

- **protocol** (`plugin/protocols/workflow-protocol.md`) — the source of truth for step order, hard
  guardrails, and the delegation packet (`#packet`);
- **commands** (`plugin/commands/*.md`) — operational prose and state mechanics, composing that packet per spawn;
- **`plugin/CLAUDE.md`** — the state schema and the user-facing overview;
- **diagram** (`docs/workflow/workflow-diagram-detailed.html`) — the picture.

Keep them in lock-step:

- Any change to a phase or step — its definition, wording, or order — lands in the protocol's phase
  list / guardrail registry first, with the command and the detailed diagram never lagging it **in the
  same change** (CLAUDE.md follows only when the state schema or overview changes). A `hook`-class
  registry row must match a live `plugin/hooks/hooks.json` matcher (CI-verified).
- If the change is visible at the four-phase level, also update the simplified diagram and the README.

### The execution walk

Commands are executed, not read. Before merging a command change, walk it step-by-step as the runtime
agent:

- Does the data each step reads exist yet? Is the tool allowed in this mode (plan mode blocks writes)?
  Can the shell command succeed on a fresh repo (`git rm` fails on uncommitted files)?
- A crash at any step boundary must leave a state the resume path recovers.
- A gate must be satisfiable by what it gates — a "must fail" gate can't judge a rightly-green corrected test.

### Changing what something means

A behaviour change is done when the old meaning is **extinct**, not when the new one is written:

- List every surface stating the old meaning — commands, `plugin/CLAUDE.md`, templates, agents, hook
  messages, README, diagrams, tests, and protocols — and update each.
- Grep the **concept**, not the string; old meanings hide in paraphrase.

### Adding an agent

Agents are `plugin/agents/{name}.md` (lowercase). They carry **no hardcoded stack** (project variance
lives in each project's `code-of-conduct.md`) and **no Hercules-internal literals** (`/hercules:*`,
state fields like `current_spec`/`tier`, `*-spec-NN-*.md`) — that knowledge is injected at call time.
Exception: `hercules.md`, the orchestrator persona.

- A spec is read-only / write-once / **delete-once** (`git rm` at delivery); under a keep-specs
  code-of-conduct the orchestrator refreshes it once at retire instead. An agent never updates a spec.
- Replies follow the A2A `§ Agent-Injected Core` (`plugin/protocols/a2a-communication-protocol.md`).
- Update the roster in **three places** — the agent list in `plugin/CLAUDE.md`, the `advisors[]` array
  in `plugin/settings.json`, and `_ADVISOR_AGENTS` in `tests/agents/test_agents.py`; a sync test fails
  on drift.
- **Instruction load is a budget.** Say whose context new content lands in — a delegate's total stays
  under ~150 directives (own file + packet + A2A core + the project CoC). Always-loaded content spends
  everyone's headroom.

### Hooks

Hooks are the plugin's only **hard** enforcement — deterministic code Claude Code runs, which a model
cannot rationalise past. They live in `plugin/hooks/` and auto-load via `plugin/hooks/hooks.json`.

- **Stdlib-only Python, no shebang** — invoked as `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<name>.py"`; no
  jq/bash dependency, portable to Windows.
- **Read-only over `~/.hercules`, fail-open** — a hook never writes state (it would race the model's
  atomic writes) and allows the action whenever no active build resolves. It must never crash a user's edit.
- **Honest scope.** It reads model-authored state, so it is **runtime-mediated, not tamper-proof** — say
  so, never "unbypassable." User-granted overrides (`frozen_override`, `frozen_hook: "off"`) are recorded
  state, not holes.
- Every hook ships with executable tests under `tests/hooks/` plus a wiring test that its `hooks.json`
  command resolves to a real script.

### Adding a skill

Skills are `plugin/skills/{name}/SKILL.md` — each declares a phase-anchored trigger, a
precondition-then-stop guard, and atomic/idempotent writes, and falls back gracefully when a target
project has no `code-of-conduct.md`.

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
- **The plugin version is single-sourced** — `pyproject.toml` and `plugin/.claude-plugin/plugin.json`
  carry the same version; CI fails on drift.
- **Red first, red possible forever.** A new test is born failing — write it before the feature, watch it
  fail for the right reason, then make it pass. Anchor it so it stays able to fail; `"auto" in lower`
  stays green on "automatically" — that's decoration, not a test.
- **Pin both ends of a cross-file contract** — writer and reader, or one sync test. A reader-only pin
  stays green while the deleted writer bricks the product.

---

## Documentation style

Every doc, README, and diagram describes the **present state — what exists now**. No before/after,
changelog narrative, or "previously / today / used to / new vs old" framing — history lives in `git diff`
and the generated `CHANGELOG.md`.

- Prefer **bullets over prose** for anything a contributor scans — one bullet per rule, the term in bold.
- **One reading only** — every sentence admits exactly one interpretation; if it reads two ways, split or reword it.
- **160-character** hard line cap on new and edited content (table rows, long URLs, the HTML diagram's
  markup, and YAML values are the only exemptions).
- **Prose is pinned.** Most sentences in `plugin/` are pinned by tests — `grep tests/` for a sentence
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
  gates — never silently raise a threshold or cut content to fit. Surface the breach, propose at least
  three options, and let the maintainer choose; raise a limit only on their explicit word.
- **Assert the present state, not the past** — pair every absence check with a positive companion
  assertion or a named, ongoing risk it guards, or it is cosmetic.
- **Prove it works, don't assert it "should."** A green suite is necessary, not sufficient — verify a
  change end-to-end with a real run before calling it done. The suite can't inspect Claude Code's
  permission mode, so at release time drive `/hercules:workflow` by hand against a throwaway repo and
  confirm the four phases produce their artifacts in order. That manual smoke is a release check, not
  a CI gate.

### Tokens

Token counts use `tiktoken` (cl100k_base); the encoding is fetched once and cached. Set
`TIKTOKEN_CACHE_DIR` to a persistent directory to run the suite offline (CI caches it there).

### Golden files

The injected A2A Core is pinned byte-for-byte in `tests/testdata/core.golden`. After an intentional edit,
re-bless it from the failing test's expected value. All methodology checks are gates, not warnings — a
failing gate means the change broke a contract; fix the contract, not the test.
