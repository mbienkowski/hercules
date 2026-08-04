# Hercules — Code of Conduct

Hercules enforces spec-driven discipline on its users; it holds itself to the same bar. This document
is for **contributors** — the rules and invariants for extending Hercules itself. The practical side
(repository layout, build commands, checklists, live-plugin testing) lives in
[`CONTRIBUTING.md`](CONTRIBUTING.md); the release process in [`RELEASE.md`](RELEASE.md). How a user
*runs* Hercules (the workflow, phases, and artifact conventions) lives in the built plugin's
`CLAUDE.md` and the auto-loaded `hercules-reference` skill, authored in [`src/content/`](src/content/).

Rules here follow one shape — **the rule in bold**, a one-line WHY, and a DON'T/DO pair where one
fits. Scan the bold lines first; the rest is there when you need to argue with one.

---

## Development

### Source and output

Hercules is authored once — in `src/content/` (the product), `src/targets/` (one recipe per
ecosystem), and `src/scripts/hooks/` + `src/scripts/tools/` (shared stdlib Python shipped to users) —
and compiled to per-ecosystem plugins under `dist/` by `internal/builder/` (`make build`). **Edit the
source domains, never `dist/`** — `dist/` is generated, and CI's drift gate fails when it is
hand-edited or left stale. Paths below name the source you edit; the compiler places the built copy
under `dist/`. The full directory map is [`CONTRIBUTING.md` § Where things live](CONTRIBUTING.md).

### Working principles

**A name has to work without its directory.** Open a file cold and its name plus its function names
must tell you what happens. Three tests, in order:

1. **Does it say what it does, or only that it exists?** `scope` names a category, not a job;
   `buildRecipe` reads as "construct a recipe" but builds a distribution FROM one. Both send the
   reader off to check.
2. **Would the name survive swapping the implementation?** Name the ROLE, not the vendor —
   `template-engine` over `liquid-engine`; vendor facts belong in that file's header. This is
   dependency inversion applied to names.
3. **Does the abbreviation actually shorten anything?** `getRecPath()` beats `getRecipePath()` in no
   way that matters. **Keep** the platform's own words — `fs`, `env`, `src`, `dest`, `dir` — where
   expanding adds syllables without information.

Prefer a precise verb to a generic one: `list…` says plural, `read…` says disk, `find…` says maybe
empty, `describe…` says for a human. `get…` says none of that; use it only where the name should
read as a value (`getRecipePath`).
**WHY:** a name that lies costs more review time than one that is merely terse.
**DON'T:** `scope.mts`, `buildRecipe()`, `analyzeSource()`, `relFiles()`.
**DO:** `variable-scope.mts`, `buildDistribution()`, `parseTemplateStructure()`, `listFilesUnder()`.

**A rule is a hypothesis until it has met the whole corpus.** Run a new lint, law, or invariant over
the real tree before believing it — and when it first fires, ask whether the RULE is too broad before
assuming the content is wrong. **WHY:** the first legitimate-looking refusal is often the rule's
defect, and the narrowed rule is STRONGER — it catches the real defect and refuses nothing
legitimate. **DON'T:** ship the rule and amend content to fit it. **DO:** treat the first refusal as
evidence about the rule.

**A claim in a header is enforced, or it is struck.** A comment asserting a property — "this import
performs zero filesystem syscalls" — is a promise a reader will rely on and nothing will keep.
**WHY:** an unpinned guarantee outlives its truth silently; only a probe or a test notices.
**DON'T:** document a property you did not pin. **DO:** write the property as a test and let the
header cite it.

**Read before judging.** Never propose deleting or rewriting a file by its name or size alone; cite
its header before proposing removal. **WHY:** a file that looks redundant often defends a case its
header names and nothing else covers — e.g. a check that looks like a second drift gate exists
because drift comparison is blind to a source that never enters the pipeline. **DON'T:** "This test
looks redundant, remove it." **DO:** "This test defends X; I checked the survivors and they cover it."

**Cross-artifact contracts are derived, not listed.** When two artifacts must agree (markdown vs
Python guard; docs vs schema; a manifest vs the roster it names), a test derives one side from the
other's source, so a rename fails by name. **WHY:** the failure this kills is both documents agreeing
with each other and with nothing else — `tests/content/docsAndPlugin/theProcedureStillWorks.spec.ts`
refuses any configuration key this document names that no schema defines.

**The engine explains itself, or it is too big.** `internal/builder/bin/recipe.mts` states the whole
pipeline in one page of code, and each module's header says why it exists; when that stops being
true, the answer is a smaller engine, not a diagram. **WHY:** a separate map of the build drifts from
the build it claims to explain, and then needs a guard test of its own to reconcile the two.

**Deletion discipline.** Before deleting a test, hook, or block, inventory what behaviours it
defends and map each to a survivor: prove redundancy by opening the covering test in CI, or (only
when the owner authorizes) record the dropped class in a ledger and commit message. **WHY:** a
"covering" suite's roster can exclude the very case in question — a claim of coverage is only as good
as the named defender. **DON'T:** delete silently. **DO:** run the spec that claims to cover it, open
its file, name the defender.

**Commit messages are commitments.** Audits read them as promises — if your message says a gate
exists, it must be red-tested to exist. **WHY:** CI runs on commit messages to decide what to check.
**DON'T:** "add CI gate" without wiring. **DO:** write the test red first, wire the gate, then commit
with the promise auditable.

**Honest accounting.** Report misses as misses; numbers measured by command, both ways when a metric
can be framed. Never move goalposts after the shot. **WHY:** hidden gaps silently widen into control
gaps. **DON'T:** "coverage is 82%" when it measures 79% on your machine. **DO:** state the
measurement and the tool.

**Executable over wishful.** An instruction an LLM must follow ("write atomically, preserving other
sessions") is a hardening candidate: make it a stdlib tool with exit codes (pattern:
`src/scripts/tools/project_reset.py`), not prose. **WHY:** text shrinks, certainty rises, and its
tests become code tests. **DON'T:** "the gate must prevent…" in markdown. **DO:** code exit codes
and test them.

**Abstraction vs duplication.** An abstraction that costs more than duplication is rejected — 2
sites × <10 lines is usually fine — and reasoned rejections are recorded so they are not
re-litigated. **WHY:** premature abstraction invites changes that don't amortize; `canon()` is
duplicated deliberately because shipping isolation and opposite fail postures justify keeping the
code apart.

**Look 2–3 steps ahead.** Judge a change by what it forecloses; a narrow fix that blocks a likely
future need loses to the more general approach.

**Propose a change in five parts, in order:** quote the original, show the after, link the file(s),
state the need, state the approach.

### Adding a command

Commands are `src/content/commands/{name}.md` (lowercase — macOS is case-insensitive, Linux is not). Each:

- Carries its `/hercules:{name}` trigger phrase and uses `YYYY-MM-DD` dates in every artifact path.
- Opens in plan mode and ends at one **Plan approval** gate, exiting with `ExitPlanMode` (`auto`);
  read-only or utility skills may omit plan mode.
- Points forward to the next phase at close-out and updates the workflow table in `src/content/persona.md`.
- Adds a token-budget entry to `tests/content/promptBudgets.spec.ts`. Step numbers are integers — no `4a`/`1b`.

A **maintenance command** — invoked deliberately, standing outside the four phases, never a side effect
of one — carries none of the phase-only obligations above: no forward pointer and no workflow-table row,
because there is no next phase and it is not a step. It still opens in plan mode, still ends at one Plan
approval gate, and still carries its trigger phrase and its budget row like any other command.

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
  registry row must match a live matcher in the **reference** gate — the `hooks/hooks.json` entry
  in `src/targets/claude-code.json` (CI-verified); each other ecosystem's equivalent gate is
  pinned by its own wiring test under `tests/scripts/hooks/` (see § Hooks).
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
  `advisors[]` array in Claude Code's own settings source
  (`src/content/targets/claude-code/settings.json`) — `tests/dist/rosterSync.spec.ts` reads the compiled
  `settings.json` roster directly and fails on drift, so there is no third place to keep in sync.
- **Instruction load is a budget.** Say whose context new content lands in — a delegate's total stays
  under ~150 directives (own file + packet + A2A core + the project code of conduct). Always-loaded
  content spends everyone's headroom.

### Hooks

> **LOCKED.** `src/scripts/hooks/` stays Python, stdlib-only, forever — the one deliberate, permanent
> exception to the all-TypeScript rule for executable domains. Porting it would force a Node runtime
> dependency onto every consumer across all seven ecosystems, for code whose entire job is running
> unmodified on whatever the host ships. Do not "finish the migration" here.

Hooks are the plugin's **hard** enforcement — deterministic code the host runs, which a model cannot
rationalise past. All hook code is authored ONCE in `src/scripts/hooks/` and byte-copied to every
ecosystem; what differs per host is **its own data file** — `hooks/write_gate.json`, authored at
`src/content/targets/<eco>/hooks/write_gate.json` and checked against
`recipe.schema.json#/$defs/writeGate`. The surfaces:

- **Claude Code** — a `PreToolUse` hook (the canonical guard itself, wired by the recipe's
  `hooks/hooks.json` entry) denies a write before it lands. The reference gate.
- **OpenCode** — a generated `tool.execute.before` hook (in `plugin.js`) throws to abort a frozen edit
  before disk — a real pre-write veto. It shells to the byte-identical canonical guard, not a re-port.
- **Gemini CLI / Copilot CLI** — the host's `BeforeTool`/`preToolUse` event, mapped through the
  configuration's tool map onto the canonical guard: a true pre-write veto. The hosts' decision
  shapes (deny/allow JSON) are configuration data.
- **Cursor** — `beforeShellExecution`/`beforeMCPExecution` **deny** a frozen write/commit; the edit
  path is **runtime-aware**, because `afterFileEdit` is notification-only: **advisory** in the
  interactive IDE (a loud notice, **no** working-tree mutation — the human owns their tree), an
  automatic `git checkout` restore only in **headless** runs (`HERCULES_RUNTIME_MODE=headless`).
  The backstop is the **acceptance gate**: frozen tests re-hashed before a spec retires — a strong
  catch, not an unbypassable lock. Full disclosure: `src/content/targets/cursor/CAPABILITIES.md`.

Shared rules for every hook, on every ecosystem:

- **Stdlib-only Python, no shebang** — invoked as `python3 <script>` (exec-form `args`, or a `command`
  string on hosts that require it); no jq/bash dependency, cross-platform. The `${…_PLUGIN_ROOT}` env
  var is the host's, e.g. `${CLAUDE_PLUGIN_ROOT}` / `${CURSOR_PLUGIN_ROOT}`.
- **Read-only over `~/.hercules`, fail-open** — a hook never writes state (it would race the model's
  atomic writes) and allows the action whenever no active build resolves or no `python3` is found; it
  must never crash a user's edit. The **one** sanctioned working-tree mutation among hooks is
  Cursor's disclosed headless restore: through git, bounded to the frozen path, reporting success
  **only when git actually restored it**. A tool in `src/scripts/tools/` is the other sanctioned
  mutation and a different kind: command-invoked, write-capable by declaration, and fail-closed —
  a hook's safe default is allowing an edit; a deleting tool's is doing nothing.
- **Honest scope.** A hook reads model-authored state, so it is **runtime-mediated, not tamper-proof**
  — say so, never "unbypassable"; disclose each host's limits in its own
  `src/content/targets/<eco>/CAPABILITIES.md` (fail-open without `python3`; a revert-only path where
  the host can only report after a write). User-granted overrides (`frozen_override`,
  `frozen_hook: "off"`) are recorded state, not holes.
- **Single source of truth.** The frozen-guard state reader (`hercules_state.py`) is authored once and
  shipped byte-identical to every ecosystem (a build-time copy, pinned by a byte-identity test).
- Every hook ships with executable tests under `tests/scripts/hooks/` (scanned for hygiene across all
  ecosystems) plus a wiring test that each target's `hooks.json`/`plugin.js` resolves its command to a
  real script.

### Adding a skill

Skills are `src/content/skills/{name}/SKILL.md` — each declares a phase-anchored trigger, a
precondition-then-stop guard, and atomic/idempotent writes, and falls back gracefully when a target
project has no `code-of-conduct.md`.

### Adding an ecosystem (target)

**A target is one data file, and the build executes it.** `src/targets/<eco>.json` is a RECIPE — a
map from every shipped path under `dist/<eco>/` to the ordered sources it is made of, checked against
the published `src/targets/recipe.schema.json`. The engine holds **zero** per-ecosystem branches and
zero decisions of any kind; nothing is globbed, routed, or inferred — a file not named is not
shipped, and a `null` entry declines a path explicitly. The practical step-by-step (recipe keys,
capability declaration, gate registration, smoke entries) is
[`CONTRIBUTING.md` § Adding a new target](CONTRIBUTING.md). The contract:

- **Configurations hold data, never expressions.** The conditional vocabulary in content is equality
  and nothing else — `{% if var %}`, `{% if var == "literal" %}`, `{% elsif %}`, `{% else %}`,
  `{% endif %}`, `{{ var }}`, `{% raw %}`; everything beyond it is refused by a lint naming the file
  and line, and zero template filters are registered, so content needing escaping fails loudly. A
  target needing more vocabulary gets a named, tested change in `internal/builder/`, or an
  ecosystem-specific FILE — never a cleverer configuration.
- **Guidance adapts by declared capability, never by tool name.** Content branches on what a tool CAN
  DO (`{% if plan_mode == "tool" %}`); capabilities ARE variables, no separate concept. A variable
  used in a condition must be declared by EVERY configuration rendering that source — `false` when
  the branch is unwanted, never omission (lint-enforced): a condition on an undeclared variable is
  exactly the silent empty block this design exists to eliminate.
- **Ecosystem-specific FILES are sanctioned; per-ecosystem code paths are not.** A host's manifest,
  hook wiring, capability prose, logo, or entry point is a real file at `src/content/targets/<eco>/`,
  named by a recipe entry like any other source; a versioned manifest writes `{{ version }}`.
- **What is NOT in the recipe.** Live-CLI smoke declarations live in
  `internal/release/smoke-targets.json` — "what does this distribution contain" and "how does CI
  prove it loads" are different questions, pinned to each other: a distribution with no smoke entry,
  or an entry naming no distribution, stops the release. The write gate keeps its own schema
  (`recipe.schema.json#/$defs/writeGate`) because it is a security surface: a mistyped key there
  ships a hook that is asked for permission and structurally cannot refuse.
- **Enforcement + release:** a `GATE_EXPECTATIONS` entry (or explicit waiver) in
  `tests/scripts/hooks/test_enforcement_gates.py` — hand-authored on purpose, the forcing function
  that a new target cannot ship ungated — and a `RELEASE.md` smoke section.

The rule is the same for a trivial ecosystem and a complex one; the complex one just names more
files. `make build-check` proves a recipe reproduces the committed `dist/` — by BYTES and by
PERMISSION BITS, because that tree is what every marketplace installs from.

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

Enforced by the test suite (the top-level `tests/` tree mirroring every domain, plus the Python
islands `tests/scripts/hooks/` and `tests/scripts/tools/`) — a change that breaks one fails CI:

- **Every shipped artifact has an owning test.** A new manifest, agent, command, or skill ships only with
  a test that fails when it is missing or malformed.
- **The plugin version is single-sourced** — `package.json` is the canonical version of record;
  `pyproject.toml` is the only other literal, cross-checked every CI `validate` run; the two are the
  whole canonical list (`internal/release/version-files.mts::VERSION_TARGETS`), and both are build
  *inputs*, never `dist/` outputs. Every versioned manifest writes `{{ version }}`, never a literal.
  Tests assert every shipped manifest equals the canonical version, that no `{{ … }}` survives a
  render, and that every surviving `${NAME}` is declared in the recipe's `runtime_variables` — those
  belong to the host, and we never resolve them.
- **Red first, red possible forever.** A new test is born failing — write it before the feature, watch it
  fail for the right reason, then make it pass. Anchor it so it stays able to fail; `"auto" in lower`
  stays green on "automatically" — that's decoration, not a test.
- **Pin both ends of a cross-file contract** — writer and reader, or one sync test. A reader-only pin
  stays green while the deleted writer bricks the product.
- **CI is Makefile-driven — no inline code in workflows.** Every GitHub Actions `run:` step is a single
  `make <target>`; the logic lives in the `Makefile` and `internal/release/ci/`, so it is one source of truth,
  testable, and runnable locally. A new CI step adds a `make` target + a `internal/release/ci/` helper, never an
  inline YAML heredoc or multi-line shell. Enforced by `tests/release/pipeline/releasePipeline.spec.ts`.

---

## Documentation & comment style

Written by a maintainer for a maintainer: reading a fifth of what is here should answer most of what
anyone asks of a file. Volume is the enemy of that, and the caps below are not stylistic.

**Every written word in this repo describes the present state — what exists now.** This is not a
docs-only rule: it binds docs, READMEs, diagrams, code comments, docstrings, YAML and JSON comments,
test headers, and error messages alike. No before/after, changelog narrative, migration story, or
"previously / used to / no longer / ported from / unlike the old / new vs old" framing, and no
reference to a deleted file, language, or tool as context — history lives in `git diff` and the
generated `CHANGELOG.md`. Explain what the code does and *why it is this way*, never what it was.

- **Hard caps, per kind.** A **file** header is 1–2 lines; 5–6 only when the file carries a real
  subtlety. A **function** header is 1–2 lines; 4–5 in genuinely rare cases. A **JSON field**
  description is ONE line — if it needs more, the field is doing several jobs and wants splitting
  into several fields. Over the cap is not a writing problem, it is a design signal: the function is
  too big, the name is wrong, or the field means too much.
- **Never explain a rule from this document in code.** No "per CODE_OF_CONDUCT §…", no restating why
  a threshold exists, no arguing for a decision already made here. A reader verifies compliance by
  holding the code up to this file — not by finding the file quoted inside it.
- **Comments read top to bottom as the business flow.** File header, then function header, then one
  line above each block. Someone reading ONLY those lines, in order, should be able to say what the
  function does for the business and what to expect from it — without reading a statement.
- **Blocks are separated by one blank line**, and a block gets at most one line above it. Nobody
  reads a mid-function comment cold; they read the headers first and then scan for the block they
  need.
- **Expand every abbreviation at first use**, in every file — write "FS (filesystem)", "A2A
  (agent-to-agent)", "CC (cognitive complexity)". A reader must never have to guess or grep.
- Prefer **bullets over prose** for anything a contributor scans — one bullet per rule, the term in bold.
- **One reading only** — every sentence admits exactly one interpretation; if it reads two ways, split or reword it.
- **160-character** hard line cap on new and edited content (table rows, long URLs, the HTML diagram's
  markup, and YAML values are the only exemptions).
- **Prose is pinned.** Most sentences in `src/content/` are pinned by tests — `grep content/tests/` for a
  sentence before rewording it; CI fails on silent drift.

---

## Testing

Two runtimes, two runners, one bar. **Python** is only for code SHIPPED TO USERS and run unmodified
on their machine (stdlib-only, no runtime dependency): `src/scripts/hooks/` and `src/scripts/tools/`,
each its own test island (`tests/scripts/hooks/`, `tests/scripts/tools/`). **TypeScript** is
everything else executable, each domain's tests mirrored under the top-level `tests/` tree. Commands:
[`CONTRIBUTING.md` § Quick start](CONTRIBUTING.md). CI's one `test` job runs `make test` verbatim, so
a red check reproduces locally with that target — then narrows with `make test-py` / `make test-ts`.

**A change to test or CI infrastructure is verified by running the pipeline, not the suite.** When
you touch `vitest.config.mts`, a `make` target, or anything under `internal/release/ci/`, run the
workflows' own entry points — `make ci-build validate test test-smoke smoke-matrix` — and simulate a
release (`make release-version && make build && npx vitest run`). **WHY:** a defect in the harness is
invisible to the suite it drives — a config-level `exclude` beats an explicit file path on the
command line, so a green local run proves nothing about the excluded path CI invokes. **DON'T:** call
a green `npx vitest run` proof of a config change. **DO:** run the same entry points CI runs.

**No percentage gates.** A numeric floor rewards letter-tests written to hit a number. What holds
the bar instead, mechanically:

- **Coverage ratchet** — the MEASURED coverage of the behavioural suite becomes the floor; it rises
  only by re-measuring after tests are added, never by editing the number, and never as an
  aspiration.
- **Size is direction, never a target.** No work is judged by lines removed or added; quality of
  delivery outranks minimisation.

**Mutation testing is a tool, not a gate** — the whole policy, stated once, here:

- `make test-mutation` is LOCAL and manual: it runs mutmut and Stryker directly; each prints its own
  kill rate and survivor list. No job that can block a merge or a release runs it — mutation reaches
  CI only as the scheduled report (`.github/workflows/mutation-report.yml`, `cron: '0 2 * * 6'`,
  `make mutation-report`), whose red is a calendar flag. The one numeric requirement — shipped Python
  at >=85% — lives inline in `internal/release/ci/mutation_report.sh`, run only by that job.
  **WHY:** a gate a pull request never runs is not a gate — it is a trap that springs after merge, on
  `main`, where it blocks shipping rather than the change that caused it. **Nothing in `ci.yml` is
  main-only.**
- **Mutate the engine, never the output.** The mutation globs cover `src/scripts/` and `internal/`
  only — the code that DECIDES things — never `dist/` (generated; the drift gate already proves it
  byte-for-byte) and never `tests/budgets/` (you don't mutate your own ruler). A hardened engine
  still only proves the *transform* — a wrong fact in `src/content/` or `src/targets/*.json` ships
  byte-perfect through it, which is why `tests/content/` and recipe schema validation are separate
  gates. Widening the globs is a change to reject in review, with a pointer to this paragraph.
- **A surviving mutant is a verdict a human rules on** — a missing test (write it) or a better
  behaviour than the code (adopt it) — never one CI enforces, and never silenced:
  `# pragma: no mutate` is allowed only on static strings whose mutants are all behaviourally
  equivalent, never on a branch, comparison, or return value.

**Test names state a business fact, timelessly** — a stakeholder could sign them:

```
DO:  it('a new ecosystem builds a complete dist from its JSON alone, with no code change')
DO:  it('a malformed target config fails the build naming the config, the path and the allowed values')
DO:  it('a frozen test cannot be edited while its spec is under implementation')
DON'T: expect(md).toContain('cadence')                      // a letter, not a behaviour
DON'T: expect(err.message).toBe('targets["agents/hercules.md"].sources[0]: …') // pins wording, not meaning
DON'T: expect(lower.lastIndexOf('git rm')).toBeGreaterThan(lower.indexOf('traceab'))
```

The bans on prose-pinning and the business-language bar are REVIEW-enforced conventions — stated
here as the standard reviewers hold changes to, with no tool pretending otherwise.

- **One synthetic contract, seven real conformance suites.**
  `tests/dist/synthetic-ecosystem.spec.ts` hand-composes a recipe exercising every choice the schema
  allows at least once, proving the ENGINE handles the full vocabulary independent of any one
  ecosystem; `tests/dist/universalConformance.spec.ts` then proves each REAL configuration's declared
  choices render correctly. A per-target spec (`tests/dist/<eco>/build.spec.ts`) exists only for a
  fact neither can know — a host-specific rendering contract — never a restatement of something the
  generic suite already proves for every target.
- **One target per test.** Each test asserts one behaviour; split any test longer than 20 lines, and
  any test file longer than 500 lines.
- **Pin the product, not this guide.** Tests pin commands, agents, protocols, and hooks — the enforced
  surfaces; this document stays editable and is not itself pinned sentence-by-sentence.
- **Budgets are fixed.** The token/instruction budgets in `tests/content/promptBudgets.spec.ts` are quality
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

### Test value hierarchy

**Three tiers of test value,** in descending order. Protect them accordingly, and trim what falls below:

**(a) Tests of shipped code (hooks/tools) — highest value.** They detect behaviour changes in code
users run unmodified. Keep 80–90% coverage here — a gap means the user could hit a defect.

**(b) Machinery tests — main flows + one representative error path.** Coverage is a ZONE (floor 80,
aim 82–88), never a maximum to chase. A 91% coverage spike on bad tests is worse than 82% on good ones.

**(c) Content tests — lowest value.** Assert main decisions, user gates, critical prohibitions, and
step order **only** — never wording. A content test asserts that a promise **survives** — the
smallest evidence needed — not the sentence making it. **WHY:** a sentence rewording is not a defect,
breaking the promise is — and a test that breaks on rewording teaches people to stop improving
sentences. **DON'T:** `it('the exact string "without asking" appears')`. **DO:** name the promise —
`it('never writes over an existing code of conduct without asking')`.

### Guard the guard

Any parameterised/derived suite must fail when it finds nothing — empty roster = red — and its
roster is reconciled against reality. **WHY:** an entry removed from a roster silently removes every
test derived from it, all green. Example: `editions.spec.ts` scans the live filesystem, so an
edition gone from disk but not from the suite goes red instead of vanishing.

Guard-the-guard belongs on the ORCHESTRATOR — the thing that discovers what to inspect — not on every
leaf function it calls. A pure function over one file's text correctly returns nothing for empty
input; the discovery that fed it nothing is what must go red.

### One universal test beats seven per-host ones

A test written for one ecosystem must be one you genuinely **cannot** write generically: it launches
that host's real binary, parses that host's output, or asserts a format only that host uses.
Everything else is derived once, from the recipes, so an eighth ecosystem is covered with zero new
lines. **WHY:** hand-written per-host restatements of what a recipe already declares are files to
maintain for one fact, each incapable of failing before the universal check fails first with a better
message. **DON'T:** a hardcoded list of shipped paths in `tests/dist/<eco>/`. **DO:** derive the list
from the recipe, and leave the per-host file holding only the live-CLI leg.

A universal test that enumerates the seven names in its own body is the same failure moved, not fixed.

### Test the source, not the seven copies

Every hook and tool under `src/scripts/` is authored once and byte-copied into all seven
distributions. Tests of its LOGIC drive `src/`, against fixtures that can express shapes no
distribution happens to ship. Tests that read `dist/` are supply-chain checks — that the SHIPPED copy
runs, and is wired — and each one says so in its header, with the reason. **WHY:** driving logic
through a shipped copy tests the copy operation seven times, grows the suite with the ecosystem count
for no added protection, and cannot reach shapes (a missing deny, a deeply nested reason, an
unimplemented protocol) that no host ships today but a fixture can.

### A quarantined test needs a measurement, not a belief

Excluding a spec from the default run is a real cost: it stops defending the thing it was written
for. The exclusion has to name a **measured** reason — a runtime, a spawned process — not a belief
about one. **WHY:** a spec parked as "slow" on belief alone can measure fast, and while it sits in
the slow gate the defect class it guards ships green.

### A ratchet declares its path upward

A budget measured exactly against today's tree has zero headroom, so the first legitimate addition
breaks it — and the pressure goes into gaming the measurement rather than into the decision the
budget exists to force. Raising one is allowed and is a decision: the accounting goes in the file
itself, naming what the rise bought, so the next reader can judge it and the owner can reverse it.
Then re-measure DOWN as soon as the work that justified it settles. A budget stated as a requirement
is not raised without the owner's word.

### Tokens

Token counts use `js-tiktoken` (cl100k_base), imported as `js-tiktoken/lite` +
`js-tiktoken/ranks/cl100k_base` so the encoding's ranks are bundled at install time — no runtime
fetch, no cache directory, and the suite runs offline by construction. Exact-pinned in
`package.json` (never a caret range): a tokenizer bump can silently move the counts
`tests/content/promptBudgets.spec.ts` gates on, so it arrives as a reviewable, Dependabot-proposed
PR, never an invisible transitive update.

### Shipped-content review

**The committed `dist/` IS the reviewed snapshot.** `make build-check` byte-compares a fresh render
against it on every commit, across all seven editions, so no shipped byte changes without appearing
in a diff — that comparison, plus human review of the diff, is what governs a content change. No
gate here accepts a self-attested sentence in place of the diff: a written claim about a change
cannot distinguish a true one from a false one, only its own presence.

Give every regex or absence-based guard a companion test that proves it fires on a real violation —
a detector that quietly matches nothing reports success.

All methodology checks are gates, not warnings — a failing gate means the change broke a contract;
fix the contract, not the test.

### Complexity

There is no complexity gate and no cyclomatic/cognitive ceiling: a numeric gate invites writing to
the number. What holds the bar: `tsc` (strict types, both TS projects) and review against this
document. If a function grows past what a reader follows in one sitting, simplify it — because a
human said so, not because a linter's counter did.

### Dependencies

```bash
make vulnerability-scan   # fail on any HIGH or CRITICAL dependency CVE
```

npm carries the **entire** dependency surface: the shipped plugin declares zero runtime dependencies
and the Python hooks are stdlib-only (`dependencies = []` in `pyproject.toml`), so the whole exposure
is the dev toolchain in `package-lock.json`. CI runs the scan on every commit; high/critical fails,
moderate/low stay visible without blocking. A flagged advisory is fixed by bumping to the patched
version (Dependabot proposes these as reviewable, exact-pinned PRs) — never by lowering
`--audit-level`.

**The template engine is a supply-chain dependency, not a dev tool.** `liquidjs` writes every byte of
every shipped distribution, so it is pinned **exactly** (no caret), and an audit is not sufficient
for it — the risk is a behaviour change nobody ever classified as a vulnerability. A version bump
requires, in this order: read the upstream release diff, run `make build-check` (the byte gate over
all seven distributions on the REAL content), and record in the commit message what was read. No
other dependency gets this treatment, because no other one gets to author shipped text.
