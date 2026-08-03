# Hercules — Code of Conduct

Hercules enforces spec-driven discipline on its users; it holds itself to the same bar. This document
is for **contributors** — the rules for extending Hercules itself. How a user *runs* Hercules (the
workflow, phases, and artifact conventions) lives in the built plugin's `CLAUDE.md` and the
auto-loaded `hercules-reference` skill, authored in [`src/content/`](src/content/).

---

## Development

### Repository layout

Five top-level directories, each answering one question: `src/` — what we ship (content, per-ecosystem
target data, and the shared hooks/tools scripts); `internal/` — what we build with (the compiler and
release tooling, never shipped); `tests/` — what we defend; `dist/` — what a user gets (generated);
`.local/` — what can be deleted (transient tool output, regenerable by one `make` target, never
committed). Every second-level directory under `src/` and `internal/` is a **domain**, not a language
or a category — nothing is named `ts`, `py`, or similar. Tests live OUTSIDE both entirely, in a
top-level **`tests/`** tree that mirrors each domain by name (`tests/builder/` tests
`internal/builder/`, `tests/scripts/hooks/` tests `src/scripts/hooks/`, and so on) — a domain owns its
tests by name, never by nesting.

Hercules is authored once (in `src/content/`, `src/targets/`, `src/scripts/hooks/`, and `src/scripts/tools/`) and compiled to per-ecosystem
plugins under **`dist/`** (`make build`). **Edit the source domains, never `dist/`** — `dist/` is
generated, and CI's drift gate fails when it is hand-edited or left stale.

- **[`src/content/`](src/content/)** — the product: ecosystem-neutral content (`agents/`, `commands/`,
  `skills/{name}/SKILL.md`, `protocols/`, and `persona.md` — the project instructions, rendered to
  each host's convention: Claude Code's `CLAUDE.md`, OpenCode's `instructions.md`). `tests/content/`
  covers the built plugin content itself.
- **[`src/targets/`](src/targets/)`/<ecosystem>.json`** — ONE RECIPE per ecosystem (see **Adding an
  ecosystem**): every shipped path under `dist/<eco>/` named explicitly, with the ordered sources it
  is made of, the variables it renders with, and its mode. Provenance runs the other way for free —
  "why does this file look like that?" is answered by reading its entry, never by reading builder
  code. Files a single host needs live under `src/content/targets/<eco>/`. Kept as its own top-level
  domain rather than nested under `src/content/`: a recipe is the thing that names sources, so it
  must not be one.
- **[`src/scripts/hooks/`](src/scripts/hooks/)** — the SHARED enforcement code (stdlib Python, authored once, byte-copied to
  every ecosystem): the canonical frozen-test guard and the one generic write-gate adapter. This
  domain holds no code the compiler executes — the compiler only copies these for the host to run.
  `tests/scripts/hooks/` is its own island (see § Testing).
- **[`src/scripts/tools/`](src/scripts/tools/)** — the SHARED programs a COMMAND invokes deliberately (stdlib Python,
  authored once, byte-copied to every ecosystem), as opposed to `src/scripts/hooks/`, which the HOST fires on
  an event. The distinction is the failure posture: a hook fails OPEN, because allowing an edit is its
  safe default; a tool that deletes fails CLOSED, because doing nothing is. Keeping them in separate
  domains is what lets `src/scripts/hooks/`'s blanket write-ban stay exactly as strict as it is. Each tool
  declares its own capabilities in `tests/scripts/tools/test_tool_hygiene.py`, and a file with no entry
  fails the suite. `tests/scripts/tools/` is its own island (see § Testing).
- **[`internal/builder/`](internal/builder/)** — the engine that executes a recipe: load and validate,
  lint, read the version, merge variables, render, write, compare with the committed `dist/`.
  `tests/builder/recipe/` covers it; the cross-ecosystem conformance and live-CLI smoke suites live
  in `tests/dist/` (see below).
- **[`internal/release/`](internal/release/)** — ships the builder's output: versioning, changelog, npm packaging, CI
  smoke/validate checks, the mutation kill-rate report, and the bash glue the GitHub workflows call
  through `make` (`internal/release/ci/`). `tests/release/` covers it.
- **[`tests/budgets/`](tests/budgets/)** — instruction/token budget, A2A (agent-to-agent) grammar, and loading-chain
  measurement code, read only by its own colocated tests (nothing runs it from the compiled output),
  so it lives in `tests/` rather than `internal/` even though it is production logic.
- **`dist/<ecosystem>/`** — the built plugins (generated; the shipped output), one tree per target.
- **[`tests/`](tests/)** — the top-level tree above, plus two cross-cutting trees that belong to no
  single domain: `tests/repo/` (repo-wide meta-guards, e.g. that every Python testpath is actually
  collected) and `tests/support/` (the TypeScript test helpers shared across every domain's own
  `tests/`). `tests/dist/` holds the cross-ecosystem conformance suites and the live-CLI smoke checks
  (one `smoke.spec.ts` per ecosystem directory) that read the BUILT `dist/` output rather than one
  domain's source alone.
- **[`.local/`](.local/)** — every transient tool output (`ts-out/`, `coverage/`, `pytest-cache/`,
  `.coverage`, `stryker-tmp/`, mutation reports): regenerable by one `make` target, machine-local,
  never committed (see `.gitignore`).

Paths below name the **source** you edit; the compiler places the built copy under `dist/`.

### Working principles

**A name has to work without its directory.** Open a file cold, knowing nothing about where it sits in the tree, and its name plus its function names must tell you what happens. Three tests, applied in this order:

1. **Does it say what it does, or only that it exists?** `scope` names a category, not a job — it builds the variable set one file renders with. `buildRecipe` reads as "construct a recipe" and in fact builds a distribution FROM one. Both are least-astonishment failures: the reader has to go and check.
2. **Would the name survive swapping the implementation?** A module named after its vendor makes a library swap touch every importer; a module named after its ROLE makes it touch one file's contents. `template-engine` over `liquid-engine` — the Liquid-specific facts belong in that file's header, which is exactly where a reader looks for them. This is dependency inversion applied to names.
3. **Does the abbreviation actually shorten anything?** `rel` appeared 52 times meaning "relative path" and cost a translation step every time; `getRecPath()` is not shorter than `getRecipePath()` in any way that matters. **Keep** the domain's own vocabulary — `fs`, `env`, `src`, `dest`, `dir` are the words the platform uses, and expanding them adds syllables without information.

Prefer a precise verb to a generic one. `list…` says the result is plural, `read…` says it touches disk, `find…` says it may come back empty, `describe…` says the result is for a human. `get…` says none of that; use it where the name would otherwise read as a value (`getRecipePath`).

**WHY:** cryptic and mis-aimed names make code harder to review and maintain, and a name that lies costs more than one that is merely terse. **DON'T:** `scope.mts`, `buildRecipe()`, `analyzeSource()`, `relFiles()`. **DO:** `variable-scope.mts`, `buildDistribution()`, `parseTemplateStructure()`, `listFilesUnder()`.

**A rule is a hypothesis until it has met the whole corpus.** A lint, law or invariant that reads as obviously right in a spec is a proposal, and the real tree is what tests it. Run it over everything before believing it — and when it fires for the first time, ask whether the RULE is too broad before assuming the content is wrong. **WHY:** twice in one migration the first real refusal was the rule: "no template tag inside a fenced code block" refused legitimate `{{ path }}` substitutions in command examples, and "every `${…}` in the output is a declared runtime variable" would have condemned a shared module's docstring documenting how another host invokes it. Both narrowed versions were STRONGER — they catch the real defect and refuse nothing legitimate. **DON'T:** ship the rule and start amending the content to fit it. **DO:** treat the first legitimate-looking refusal as evidence about the rule.

**A claim in a header is enforced, or it is struck.** A comment asserting a property — "this import performs zero filesystem syscalls", "every lint fails on empty input" — is a promise a reader will rely on and nothing will keep. Either a test enforces it or the sentence goes. **WHY:** both examples are real: the import-purity guarantee was deleted with its test while the module went on asserting it, and the guard-the-guard claim was simply false for two of seven lints — found by a reviewer probing the compiled module, not by reading. **DON'T:** document a property you did not pin. **DO:** write the property as a test and let the header cite it.

**Read before judging.** Never propose deleting or rewriting a file by its name or size alone; cite its header comments before proposing removal. **WHY:** five design assumptions failed against the code in one phase — `tests/dist/nothingIsSilentlyDropped.spec.ts` looks like a second copy of the drift check, but its header documents it exists because drift comparison is blind to a source that never enters the pipeline at all. **DON'T:** "This test looks redundant, remove it." **DO:** "This test defends X; I checked the survivors and they cover it."

**Cross-artifact contracts are derived, not listed.** When two artifacts must agree (markdown instructions vs Python guard; docs vs schema; a shipped manifest vs the roster it names), a test derives one side from the other's source, so a rename fails by name. **WHY:** the failure this kills is both documents agreeing with each other and with nothing else. Example: `theProcedureStillWorks.spec.ts` reads the published schemas and refuses any configuration key this document names that no schema defines — so a vocabulary change that left the docs behind fails here, by name, rather than misleading the next contributor.

**The engine explains itself, or it is too big.** There is no separate map of the build to keep in
step with it. `internal/builder/bin/recipe.mts` states the whole pipeline in one page of code, and
each module's header says why it exists; when that stops being true, the answer is a smaller engine,
not a diagram. **WHY:** a separate map is machinery describing machinery — it drifts from the build
it claims to explain, and then needs a guard test of its own to reconcile the two.

**Deletion discipline.** Before deleting a test, hook, or block, inventory what behaviours it defends. Map each to a survivor, prove redundancy by opening the covering test in CI, or (only when the owner authorizes) record the dropped class in a ledger and commit message. **WHY:** eight gate scenarios were wrongly deleted as duplicates and restored — the "covering" suite's roster excluded that host; a hooks pass found "proven covered" claims false because a regex short-circuited. **DON'T:** delete silently. **DO:** run the spec that claims to cover it, open its file, name the defender.

**Commit messages are commitments.** Audits read them as promises — if your message says a gate exists, it must be red-tested to exist. Three audits in a row caught gaps between message claims and code. **WHY:** CI runs on commit messages to decide what to check. **DON'T:** "add CI gate" without wiring. **DO:** write the test red first, wire the gate, then commit with the promise auditable.

**Honest accounting.** Report misses as misses; numbers measured by command, both ways when a metric can be framed. Never move goalposts after the shot. **WHY:** hidden gaps silently widen into control gaps. **DON'T:** "coverage is 82%" when it's 79% on your machine. **DO:** state the measurement and the tool.

**Executable over wishful.** An instruction an LLM must follow ("write atomically, preserving other sessions") is a hardening candidate: make it a stdlib tool with exit codes (pattern: `src/scripts/tools/project_reset.py`), not prose. **WHY:** text shrinks, certainty rises, its tests become code tests. **DON'T:** "the gate must prevent…" in markdown. **DO:** code exit codes and test them.

**Abstraction vs duplication.** An abstraction that costs more than duplication is rejected. 2 sites × <10 lines is usually fine. Reasoned rejections are recorded so they are not re-litigated. **WHY:** premature abstraction invites changes that don't amortize. Example: `canon()` duplicated deliberately — shipping isolation + opposite fail postures justify keeping the code apart.

- **Look 2–3 steps ahead.** Judge a change by what it forecloses; a narrow fix that blocks a likely
  future need loses to the more general approach.
- **Propose a change in five parts, in order:** quote the original, show the after, link the file(s),
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

> **LOCKED.** `src/scripts/hooks/` stays Python, stdlib-only, forever — this is not a migration-in-progress
> state. Every other executable domain in this repo (`internal/builder/`, `internal/release/`, `tests/budgets/`, and their
> tests) is TypeScript; hooks are the one deliberate, permanent exception. Porting them would force a
> Node runtime dependency onto every consumer across all seven ecosystems, for code whose entire job is
> running unmodified, byte-identical, on whatever the host ships. Do not "finish the migration" here.

Hooks are the plugin's **hard** enforcement — deterministic code the host runs, which a model cannot
rationalise past. All hook code is authored ONCE in `src/scripts/hooks/` and byte-copied to every ecosystem;
what differs per host is **its own data file** — `hooks/write_gate.json`, authored at
`src/content/targets/<eco>/hooks/write_gate.json`, checked against
`recipe.schema.json#/$defs/writeGate`, and shipped beside the shared adapter. The surfaces:

- **Claude Code** — a `PreToolUse` hook (the canonical guard itself, wired by the recipe's
  `hooks/hooks.json` entry) denies a write before it lands. The reference gate.
- **OpenCode** — a generated `tool.execute.before` hook (in `plugin.js`) throws to abort a frozen edit
  before disk — a real pre-write veto. It shells to the byte-identical canonical guard, not a re-port.
- **Gemini CLI / Copilot CLI** — a gate declaring `when: before_write`: the host's `BeforeTool`/
  `preToolUse` event is mapped through the configuration's tool map onto the canonical guard, a true
  pre-write veto; the host's decision shapes (deny/allow JSON) are configuration data.
- **Cursor** — a gate declaring `when: after_write`: `beforeShellExecution`/
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
  must never crash a user's edit. Among hooks, the **one** sanctioned working-tree mutation is Cursor's disclosed
  after-edit `git checkout` restore in **headless** runs (`afterFileEdit` is notification-only, so it
  cannot block the landed edit — Cursor's generic `preToolUse` deny hook is unverified for the Composer
  path and not relied on; no human is present headless to act on a notice); it goes through git, never a
  direct write, is bounded to restoring the frozen path,
  and reports success **only when git actually restored it** — never a false "reverted" claim on an
  untracked file or non-git tree. In the interactive IDE the after-edit path is **advisory only** (no
  mutation). A tool in `src/scripts/tools/` is the other sanctioned mutation, and a different kind: invoked by
a command rather than fired by the host, write-capable by declaration, and fail-closed.
- **Honest scope.** A hook reads model-authored state, so it is **runtime-mediated, not tamper-proof** —
  say so, never "unbypassable"; disclose each host's limits in its own
  `src/content/targets/<eco>/CAPABILITIES.md` (fail-open without `python3`; a revert-only path where
  the host can only report after a write). User-granted overrides (`frozen_override`, `frozen_hook: "off"`) are recorded
  state, not holes.
- **Single source of truth.** The frozen-guard state reader (`hercules_state.py`) is authored once and
  shipped byte-identical to every ecosystem (a build-time copy, pinned by a byte-identity test).
- Every hook ships with executable tests under `tests/scripts/hooks/` (scanned for hygiene across all ecosystems)
  plus a wiring test that each target's `hooks.json`/`plugin.js` resolves its command to a real script.

### Adding a skill

Skills are `src/content/skills/{name}/SKILL.md` — each declares a phase-anchored trigger, a
precondition-then-stop guard, and atomic/idempotent writes, and falls back gracefully when a target
project has no `code-of-conduct.md`.

### Adding an ecosystem (target)

**A target is one data file, and the build executes it.** `src/targets/<eco>.json` is a RECIPE: a map
from every shipped path under `dist/<eco>/` to the ordered sources it is made of. The engine holds
**zero** per-ecosystem branches — and, more than that, zero decisions of any kind. It reads the
version, and then for each entry it merges variables, renders the sources in order, joins, writes and
chmods. There is no dispatch, no role, no route and no layout rule, because a recipe leaves nothing
for one to decide.

- **The recipe — `src/targets/<eco>.json`**, checked against the published
  `src/targets/recipe.schema.json` (an editor reads it through the file's `$schema` line while the
  author types; the build reads the same file and refuses anything it does not describe). Four keys:
  `name`; `variables` (what every source rendered for this tool sees — text or a real boolean);
  `runtime_variables` (every `${NAME}` a shipped file may still contain, because the HOST resolves
  it and we never do); and `targets`. An entry names `sources` (ordered, joined by one blank line),
  optional `variables` overriding the distribution's key by key, and optional `permissions`
  (absent = 644). A `null` entry declines a path explicitly — "we know about this one and it is
  deliberately absent" reads differently from silence. Nothing is globbed, routed or inferred: a file
  not named is not shipped.
- **Configurations hold data, never expressions.** The conditional vocabulary in content is equality
  and nothing else: `{% if var %}` or `{% if var == "literal" %}`, plus `{% elsif %}`, `{% else %}`,
  `{% endif %}`, `{{ var }}` and `{% raw %}`. `unless`, `and`, `or`, `!=`, `case` and every filter are
  refused by a lint that names the file and the line. Zero template filters are registered, so the
  day real content needs escaping it fails loudly here rather than corrupting a shipped file
  quietly. A target needing behaviour this vocabulary lacks does not get a cleverer configuration —
  it gets a named, tested change in `internal/builder/`, or it gets an ecosystem-specific FILE.
- **Guidance adapts by declared capability, never by tool name.** Shipped content branches on what a
  tool CAN DO (`{% if plan_mode == "tool" %}`), so a new ecosystem receives correct guidance with no
  content edit. Capabilities ARE variables now — there is no separate concept. A variable used in a
  condition must be declared by EVERY configuration that renders that source, with `false` when the
  branch is not wanted, never by omission: a lint enforces it, because a condition on an undeclared
  variable is exactly the silent empty block this design exists to eliminate.
- **Ecosystem-specific files — `src/content/targets/<eco>/`.** The "no per-ecosystem directories"
  rule is REPEALED, deliberately. It was right when the alternative was per-host code; it is wrong
  now that the alternative is inline JSON inside a recipe. A host's manifest, its hook wiring,
  its capability prose, its logo, its plugin entry point — each is a real file a human can open,
  named by an entry like any other source. A manifest needing the release version writes
  `{{ version }}`.
- **What is NOT in the recipe.** Live-CLI smoke declarations live in
  `internal/release/smoke-targets.json`: a recipe answers "what does this distribution contain", and
  that is a different question from "how does CI prove it loads in the real tool". The two are pinned
  to each other — a distribution with no smoke entry, or an entry naming no distribution, stops the
  release rather than silently skipping a leg. The write gate keeps a schema of its own
  (`recipe.schema.json#/$defs/writeGate`) because it is a security surface: every other emitted file
  is opaque text to this build, but a mistyped key there ships a hook that is asked for permission
  and structurally cannot refuse.
- **Enforcement + release:** a `GATE_EXPECTATIONS` entry (or explicit waiver) in
  `tests/scripts/hooks/test_enforcement_gates.py` — hand-authored on purpose, the forcing function
  that a new target cannot ship ungated; a `RELEASE.md` smoke section.

The rule is the same for a trivial ecosystem and a complex one; the complex one just names more
files. The committed-`dist/` gate (`make build-check`) is what proves a recipe reproduces the
intended bytes — by BYTES and by PERMISSION BITS, because that tree is what every marketplace
installs from.

**Mutation scope: logic, never output.** Mutation testing runs over `src/scripts/` and `internal/`
only — the code that DECIDES things. It never runs over `dist/`, over generated output, or over the
measurement code under `tests/budgets/`. Mutating a distribution asks "would a test notice if the
shipped bytes changed", which `build-check` already answers absolutely and for free. Widening the
mutation globs beyond those two trees is a change to reject in review, with a pointer to this
paragraph.

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
- **The plugin version is single-sourced** — `package.json` is the canonical version of record
  (`readCanonicalVersion`); `pyproject.toml` is the only other literal (setuptools reads it as-is) and
  is cross-checked against package.json every CI `validate` run. The two are the whole canonical list
  (`internal/release/version-files.mts::VERSION_TARGETS`). Every ecosystem's versioned manifest has a
  source under `src/content/targets/<eco>/` that writes `{{ version }}` like any other source, never a
  literal — a human never sees a version to hand-bump under `src/content/`; the build resolves it from
  `package.json` into each `dist/…/plugin.json`. Tests assert every shipped manifest equals the
  canonical version, that no `{{ … }}` survives a render, and that every `${NAME}` that DOES survive is
  one that recipe declares in its `runtime_variables` — those belong to the host, and we never resolve
  them.
  Literal version sources are build *inputs* (`pyproject.toml`, `package.json`), never `dist/` outputs
  (a `dist/` file would be regenerated from source on the next build).
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
  a threshold exists, no arguing for a decision already made here. Write code that follows the rules
  and let this document be the place they are checked against. A reader verifies compliance by
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

Two runtimes, two runners, one bar. **Python** is for code SHIPPED TO USERS and run unmodified on
their machine, stdlib-only so a consumer carries no runtime dependency: `src/scripts/hooks/` (the host fires
these on an event, see § Hooks) and `src/scripts/tools/` (a command invokes these deliberately) — and nothing
else. Each is its own island, its tests at `tests/scripts/hooks/` and `tests/scripts/tools/`. **TypeScript** is
everything else executable: the compiler (`internal/builder/`), the CI/release scripts (`internal/release/`),
the plugin-content lint (`src/content/`), and the A2A/metric budgets (`tests/budgets/`) — each domain's
tests mirrored under the top-level `tests/` tree.

```bash
make install         # once: pip install -e ".[dev]" + npm ci
make test            # behavioural suites, BOTH runtimes; coverage is REPORTED, never gated
make test-mutation   # LOCAL and manual only; no CI job runs it, no threshold gates on it
```

**A change to test or CI infrastructure is verified by running the pipeline, not the suite.** When you
touch `vitest.config.mts`, a `make` target, or anything under `internal/release/ci/`, run the workflows' own
entry points — `make ci-build validate test test-smoke smoke-matrix tripwire normative-gate` — and simulate a
release (`make release-version && make build && npx vitest run`). Two of the worst defects in one
delivery were invisible to `npx vitest run`: excluding the flaky live-CLI specs from the default config
left `run_smoke.sh` invoking them under a config that no longer found them, taking all seven CI smoke
legs red; and the shipped-content manifest hashed the version-bearing plugin manifests, so the release
— which bumps a version, rebuilds and commits `dist/` with no human step — wedged every release after
the first behind a `[skip ci]` commit. A config-level `exclude` also beats an explicit file path on the
command line, so every caller of an excluded path needs the `--config` flag, CI scripts included.

`test`/`test-mutation` are each a thin wrapper over `test-py` + `test-ts` / `mutation-py` +
`mutation-ts` — the split is real, not cosmetic: each half drives its own runtime's toolchain. CI has
ONE `test` job, and its only `run:` is `make test`, so a red check is reproduced by running that same
target in a terminal — then narrowed to the failing half with `make test-py` or `make test-ts`.

**No percentage gates.** The phase-1 reset dropped the 90% coverage floor (mutation's had already
gone: as a main-only CI gate it outgrew its ceiling, reported `cancelled` rather than `failed`, and
silently blocked every release with no red check to explain it). A numeric floor rewards
letter-tests written to hit a number, and this repo's audit traced much of its test bloat to
exactly that. What replaces them, mechanically:

- **The tripwire** (`internal/release/ci/tripwire.sh`, per-commit CI job): a commit that changes
  production code must carry a test change in the same commit; a pure rename is marked
  `[rename-only]`. Deleting or shrinking a test file requires a `Test-removal:` line in the commit
  message naming which surviving coverage takes over. The tripwire checks a test change EXISTS —
  its quality is review-enforced against the examples below, not tool-enforced.
- **Coverage ratchet** (from phase close-out): the MEASURED coverage of the behavioural suite
  becomes the floor; it rises only by re-measuring after tests are added, never by editing the
  number, and never as an aspiration.
- **Mutation testing is manual.** `make test-mutation` runs mutmut and Stryker directly; each
  prints its own kill rate and survivor list. No job that can block a merge or a release runs it —
  mutation testing reaches CI only as the scheduled report (`.github/workflows/mutation-report.yml`,
  `cron: '0 2 * * 6'`, `make mutation-report`), whose red is a calendar flag. A survivor is a human
  call, made in review.
- **Size is direction, never a target.** No work is judged by lines removed or added; quality of
  delivery outranks minimisation.

Test names state a business fact, timelessly — a stakeholder could sign them:

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

**Mutation testing is a tool here, not a gate.** `make test-mutation` reports a kill rate and the
mutants that survived; the one requirement — shipped Python at >=85% — lives inline in
`internal/release/ci/mutation_report.sh`, which only the scheduled `mutation-report.yml` job runs, so
no score blocks a merge or a release. It used to run as two main-only jobs that gated the release,
and that shape did more harm than the score was worth: a campaign that outgrew its `timeout-minutes`
ceiling reported `cancelled`, and because `release.yml` fires only on CI's overall success, releases
silently stopped being cut with no red check anywhere (RELEASE.md § If a release didn't happen). A
gate a pull request never runs is not a gate — it is a trap that springs after merge, on `main`,
where it blocks shipping rather than the change that caused it. **Nothing in `ci.yml` is main-only.**

- **Mutate the engine, never the output.** Stryker's `mutate` globs cover `internal/builder/` and
  `internal/release/` only — never `dist/` (generated; proven by the drift + determinism gate, not
  mutation) and never `tests/budgets/` (a measuring tool, not shipped logic — you don't mutate your own
  ruler). A correct, mutation-hardened engine given fixed input still only proves the *transform*; a
  wrong fact in `src/content/` or `src/targets/*.json` ships byte-perfect through it regardless, which
  is why `tests/content/` and each recipe's own schema validation exist as separate gates.
  `src/scripts/hooks/` is copied, not computed, so the "prove the engine, trust the output" argument does not
  cover it at all — its own logic is mutated in place by `mutmut`, independent of the builder.
- **One synthetic contract, seven real conformance suites.** `tests/dist/
  synthetic-ecosystem.spec.ts` hand-composes a recipe exercising every choice the schema allows at
  least once: a conditional in all three branch forms, a boolean that is really `false`, a per-entry
  variable override, a `null` tombstone that REMOVES a variable, an explicit `permissions` mode, an
  explicitly declined (`null`) destination, several sources joined into one file, `{% raw %}`, the
  injected `version`, and a `${RUNTIME}` placeholder travelling from a variable's value into the
  shipped bytes untouched — so it proves the ENGINE handles the full vocabulary, independent of any
  one ecosystem. `tests/dist/universalConformance.spec.ts` then proves each REAL configuration's own
  declared choices render correctly. A per-target spec (`tests/dist/<eco>/build.spec.ts`)
  exists only for a fact neither of those can know — a host-specific rendering contract (Gemini's TOML
  escaping, OpenCode's `plugin.js` entrypoint shape) — never a restatement of something the generic
  suite already proves for every target.
- **A surviving mutant is a verdict** — a missing test (write it) or a better behaviour than the code
  (adopt it) — but a verdict a human reads and rules on, not one CI enforces. Never a
  `# pragma: no mutate` to silence it; that pragma is allowed only on static strings whose mutants are
  all behaviourally equivalent, never on a branch, comparison, or return value.
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

**(a) Tests of shipped code (hooks/tools) — highest value.** They detect behaviour changes in code users run unmodified. Keep 80–90% coverage here — a gap means the user could hit a defect.

**(b) Machinery tests — main flows + one representative error path.** Coverage is a ZONE (floor 80, aim 82–88), never a maximum to chase. A 91% coverage spike on bad tests is worse than 82% on good ones.

**(c) Content tests — lowest value.** Assert main decisions, user gates, critical prohibitions, and step order **only** — never wording. **WHY:** a test that breaks when a sentence is reworded teaches people to stop improving sentences. Example: the CoC-generator spec went from 41 phrase-pins to 9 named promises — the test now states "never writes over an existing code of conduct without asking", not "contains the exact string X".

**DON'T:** `expect(md).toContain('cadence')` (a letter, not a behaviour). **DO:** name the promise — `it('names the current phase at every step')`.

### Promise, not phrasing

A content test asserts that a promise **survives** — the smallest evidence needed — not the sentence making it. **WHY:** a sentence rewording is not a defect; breaking the promise is. Example test name: `it('never writes over an existing code of conduct without asking')`, not `it('the exact string "without asking" appears')`.

### Guard the guard

Any parameterised/derived suite must fail when it finds nothing — empty roster = red — and its roster is reconciled against reality. **WHY:** removing an edition from a list once left 16 fewer tests, all green. Example: `editions.spec.ts` scans the live filesystem; an entry-gone-but-test-not-updated hides silently.

Guard-the-guard belongs on the ORCHESTRATOR — the thing that discovers what to inspect — not on every leaf function it calls. A pure function over one file's text correctly returns nothing for empty input; the discovery that fed it nothing is what must go red.

### One universal test beats seven per-host ones

A test written for one ecosystem must be one you genuinely **cannot** write generically: it launches that host's real binary, parses that host's output, or asserts a format only that host uses. Everything else is derived once, from the recipes, so an eighth ecosystem is covered with zero new lines.

**WHY:** six of seven ecosystems once carried the same assertion under six different names — "the manifest validates", "the plugin is well formed", "ships the core components" — each a hand-written restatement of what its recipe already declares, and each incapable of failing before the universal check failed first with a better message. That is seven files to maintain for one fact. **DON'T:** a hardcoded list of shipped paths in `tests/dist/<eco>/`. **DO:** derive the list from the recipe, and leave the per-host file holding only the live-CLI leg.

A universal test that enumerates the seven names in its own body is the same failure moved, not fixed.

### Test the source, not the seven copies

Every hook and tool under `src/scripts/` is authored once and byte-copied into all seven distributions. Tests of its LOGIC drive `src/`, against fixtures that can express shapes no distribution happens to ship. Tests that read `dist/` are supply-chain checks — that the SHIPPED copy runs, and is wired — and each one says so in its header, with the reason.

**WHY:** driving logic through a shipped copy tests the copy operation seven times and makes the suite grow with the ecosystem count for no added protection. Moving three gate suites onto fixtures raised gate coverage from 93% to 96%, because a fixture reaches a gate with no `deny`, a reason nested two levels deep, and a protocol the adapter does not implement — none of which any host ships today.

### A quarantined test needs a measurement, not a belief

Excluding a spec from the default run is a real cost: it stops defending the thing it was written for. The exclusion has to name a measured reason. **WHY:** `everyComponentShips.spec.ts` sat in the slow gate under the note that it "launches the real host binaries" — measured, it runs 394 ms and spawns nothing. The consequence was not theoretical: a file deleted from the shipped tree left the entire default suite green.

### A ratchet declares its path upward

A budget measured exactly against today's tree has zero headroom, so the first legitimate addition breaks it — and the pressure goes into gaming the measurement rather than into the decision the budget exists to force. Raising one is allowed and is a decision: the accounting goes in the file itself, naming what the rise bought, so the next reader can judge it and the owner can reverse it. Then re-measure DOWN as soon as the work that justified it settles. A budget stated as a requirement is not raised without the owner's word.

### Tokens

Token counts use `js-tiktoken` (cl100k_base), imported as `js-tiktoken/lite` +
`js-tiktoken/ranks/cl100k_base` so the encoding's ranks are bundled at install time — no runtime
fetch, no cache directory, and the suite runs offline by construction. Exact-pinned in
`package.json` (never a caret range): a tokenizer dependency bump is exactly the kind of change that
can silently move the counts `tests/content/promptBudgets.spec.ts` gates on, so a bump is a reviewable,
Dependabot-proposed PR, never an invisible transitive update.

### Shipped-content review (the normative-change gate)

**The committed `dist/` IS the reviewed snapshot.** `make build-check` byte-compares a fresh render
against it on every commit, across all seven editions, so no shipped byte changes without appearing
in a diff. On top of that, the **normative-change declaration gate**
(`internal/release/ci/normative_gate.sh`, a per-commit CI job) forces the deliberate step the old bless
ritual used to force: every commit touching `src/content/` must carry
`Normative-change: <one sentence>` (or `Normative-change: none — wording only`) in its OWN message,
and CI prints that commit's content diff right beside the declaration so review sees the real
change, not just the claim. An early declared commit never excuses a later undeclared one — the
gate judges each commit separately.

**Honest scope.** The declaration is self-attested: the gate forces the statement and the visible
diff, not comprehension — the same ceiling the retired bless ritual had. History to respect: three
mutation campaigns showed contradictions get written on surfaces nobody pinned, so keep the
structural guards beside the gate (whole-sentence rule pins, the scaling-model parsers, and the
section-duplication rejection in `section()`/`sectionBody()` — a duplicated heading once passed the
whole suite while changing behaviour).

Give every regex or absence-based guard a companion test that proves it fires on a real violation.
A detector that quietly matches nothing reports success, and several here did.

All methodology checks are gates, not warnings — a failing gate means the change broke a contract;
fix the contract, not the test.

### Complexity

There is no complexity gate. The phase-1 reset removed the cyclomatic/cognitive ceiling and its
toolchain (ESLint + sonarjs, flake8 + cognitive-complexity): the ceiling guarded against the
accreted machinery that phase deletes at the source, and a numeric gate invites writing to the
number. What holds the bar now: `tsc` (strict types, both TS projects), review against this
document, and the tripwire. If a function grows past what a reader follows in one sitting,
simplify it — because a human said so, not because a linter's counter did.

### Dependencies

```bash
make vulnerability-scan   # fail on any HIGH or CRITICAL dependency CVE
```

npm carries the **entire** dependency surface: the shipped plugin declares zero runtime dependencies and
the Python hooks are stdlib-only (`dependencies = []` in `pyproject.toml`), so there is no pip
runtime-CVE surface — the whole exposure is the dev toolchain in `package-lock.json`. `npm audit
--audit-level=high` exits non-zero on high/critical only; moderate and low stay visible but do not block.
CI runs it as the `vulnerability-scan` job on every commit, in the same fast tier as the per-commit gates
and `test`/`validate`/`smoke` (it `needs: [build]` only, running in parallel with them). A flagged
advisory is fixed by bumping to the patched version (Dependabot proposes these as reviewable,
exact-pinned PRs) — never by lowering `--audit-level`.

**The template engine is a supply-chain dependency, not a dev tool.** `liquidjs` writes every byte of
every shipped distribution: a change in how it trims whitespace, or in what it treats as truthy, is a
change to what users install. It is therefore pinned **exactly** (no caret) in `package.json`, and
`--audit-level=high` is explicitly not sufficient for it — an audit catches disclosed CVEs, and the
risk here is a behaviour change nobody ever classified as a vulnerability. A version bump requires,
in this order: read the upstream release diff, run `make build-check` (the byte gate over all seven
distributions on the REAL content — the thing that would actually surface a rendering change), and
record in the commit message what was read. No other dependency here gets this treatment, because no
other one gets to author shipped text.
