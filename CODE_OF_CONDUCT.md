# Hercules — Code of Conduct

Hercules enforces spec-driven discipline for its users. It holds itself to the same standard.
This document is for **contributors** — the rules for extending or contributing to Hercules
itself. How a user *runs* Hercules (the workflow, phases, and artifact conventions) lives in
[`plugin/CLAUDE.md`](plugin/CLAUDE.md).

---

## Development

### Adding a command

- File: `plugin/commands/{name}.md` — **lowercase only** (macOS is case-insensitive, Linux is not)
- Must contain the `/hercules:{name}` trigger phrase in the body
- Every delivery phase opens in plan mode and ends at one **Plan approval** gate, exiting with
  `ExitPlanMode` (`auto`). Discover and Design present a document draft and write on approval; Build
  presents a delivery plan and on approval auto-executes the per-spec TDD loop; Ship presents a commit
  plan and on approval executes. Skills that operate without user approval (read-only queries, utility
  transforms) may omit plan mode.
- Must use `YYYY-MM-DD` date format in all artifact paths
- Must point forward to the next phase at close-out
- Must update the delivery workflow table in `plugin/CLAUDE.md`
- Add a token budget entry to `tests/testdata/thresholds.json`
- Step numbering uses integers only — no letter suffixes (no `4a` / `1b`)

### Changing the workflow

The workflow's source of truth is the command files (`plugin/commands/*.md`) and `plugin/CLAUDE.md`;
its step order and hard guardrails are normatively listed in `plugin/protocols/workflow-protocol.md`
(phase lists + guardrail registry + delegation packet); its canonical picture is
`docs/workflow/workflow-diagram-detailed.html`, which ships with Hercules. Keep them in lock-step:

- **Any change to a phase or a sub-phase step — its definition, wording, or order — must be reflected
  in the protocol's phase list / guardrail registry and in `docs/workflow/workflow-diagram-detailed.html`
  in the same change.** Neither ever lags the commands; a workflow edit is not done until all three match.
  A `hook`-class registry row must match a live `plugin/hooks/hooks.json` matcher (CI-verified).
- If the change is visible at the four-phase level (a phase's purpose or its headline output), also
  update `docs/workflow/workflow-diagram-simplified.svg` and the README.
- The detailed diagram is HTML on purpose — it changes whenever the workflow does, and HTML is far
  easier to keep in sync than a hand-built SVG. Keep it self-contained (no external assets) and
  present-state (see § Documentation style).

### The execution walk

Commands are executed, not read. Before merging a command change, walk it step-by-step as the
runtime agent:

- Does the data each step reads exist yet? Is the tool allowed in this mode (plan mode blocks
  writes)? Can the shell command succeed on a fresh repo (`git rm` fails on uncommitted files)?
- Walk interruptions: a crash at any step boundary must leave a state the resume path recovers.
- A gate must be satisfiable by what it gates — a "must fail" gate can't judge a corrected test
  that is rightly green.

### Changing what something means

A behaviour change is done when the old meaning is extinct, not when the new one is written:

- First list every surface stating the old meaning: commands, `plugin/CLAUDE.md`, emitted
  templates, agents, hook messages, README, diagrams.
- Grep the **concept**, not the string — old meanings hide in paraphrase.

### Adding an agent

- File: `plugin/agents/{name}.md` — lowercase
- Carries **no hardcoded stack or personal preferences** — project variance lives in each project's `code-of-conduct.md`
- Carries **no Hercules-internal literals** — no `/hercules:{command}` references, Hercules state-schema
  field names (`current_spec`, `build_progress`, `tier`), or artifact filename patterns (`*-spec-NN-*.md`).
  That knowledge belongs in the orchestrating command file, injected into the agent via the delegation
  prompt at call time (the same pattern `plugin/protocols/a2a-communication-protocol.md` § How to inject
  uses for the A2A format). Exception: `hercules.md`, the default orchestrator persona, not a delegate.
  Generic software-delivery vocabulary ("spec," "acceptance criteria," "coverage") is not a violation —
  only the literal forms above are.
- **Never describes updating, syncing, or revising a Hercules spec.** A spec is read-only / write-once /
  delete-once — `git rm`'d on delivery (a keep-specs code-of-conduct instead has the orchestrator refresh
  it once, at retire — still never a delegate). An agent file that assumes a Hercules spec stays editable
  is describing behaviour that cannot exist. A generic caller-conditional branch (as `cynical-reviewer`
  keeps for non-Hercules callers) is fine.
- Replies follow the A2A `§ Agent-Injected Core` format (see `plugin/protocols/a2a-communication-protocol.md`)
- Update the roster in **three places**: the agent list in `plugin/CLAUDE.md`, the `advisors[]`
  array in `plugin/settings.json`, and `_ADVISOR_AGENTS` in `tests/agents/test_agents.py` — a sync
  test fails if any of the three drifts
- Run the suite to confirm no drift
- **Instruction load is a budget.** Say whose context new content lands in. A delegate's total
  stays under ~150 directives: own file + packet + A2A core (~100) + the project CoC (30–40; a
  big-repo CoC at 50–70 spends this same headroom — the generator says so when it happens).
  Always-loaded content spends everyone's headroom.

### Hooks (hard gateways)

Hooks are the plugin's only **hard** enforcement — deterministic code Claude Code runs, which a model
cannot rationalise past (unlike prose guardrails). They live in `plugin/hooks/`, auto-load via
`plugin/hooks/hooks.json` (convention path — no `plugin.json` key needed), and ship with the plugin via
`${CLAUDE_PLUGIN_ROOT}`.

- **Stdlib-only Python, no shebang** — invoked as `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<name>.py"` so
  interpreter resolution and portability (incl. Windows) are Claude Code's job; no `jq`/bash dependency.
- **Read-only over `~/.hercules`** — a hook must never write state (it would race the model's atomic
  temp+rename writes). The shared `hercules_state.resolve_session(cwd)` resolves the active session.
- **Fail-open** — when no active build session resolves (no state, unrelated repo, parse error), a hook
  allows the action. It blocks only inside a confirmed active build. A guard must never crash a user's edit.
- **Honest scope (not over-claimed).** The frozen-tests hook (`frozen_tests.py`) hardens against
  *accidental, lazy, and pressure-tested* deviation by a cooperative model. Its predicate reads
  model-authored state, so it is **runtime-mediated, not tamper-proof** — a model that rewrites its own
  `~/.hercules` state to self-exempt is a distinct adversarial threat, not closed here. Say "runtime-mediated,"
  never "unbypassable."
- **User-granted overrides are state, not holes.** `frozen_override` (and the `frozen_hook: "off"`
  opt-out) are model-authored state like `frozen_test_files` itself — no new attack class. A legitimate
  crossing is a recorded, user-quoted, round-bound grant the pre-advance git diff reconciles against;
  the honest path is also the cheapest path. Runtime-mediated, never "unbypassable."
- Every hook ships with executable tests under `tests/hooks/` (feed a `PreToolUse` payload → assert the
  exit code), plus a wiring test that its `hooks.json` command resolves to a real script.

### Adding a skill

- Directory: `plugin/skills/{name}/SKILL.md`
- Must declare: phase-anchored trigger, precondition-then-stop guard, atomic/idempotent writes
- Falls back gracefully when `code-of-conduct.md` is absent in the target project

### Documentation style

Prefer bullet points over prose blobs for anything a contributor needs to scan — checklists, term
definitions, rule lists. Long inline lists → one bullet per item, with the term in bold:

- **Term:** definition — not `*Term* = definition` run together in a sentence.

Apply this to glossaries, README callout boxes, and CoC rule lists. The goal: a developer scanning
in 30 seconds should find any rule or definition without reading a full paragraph.

- **Prose is pinned.** Most sentences in `plugin/` are pinned by tests (heading-anchored slices and
  literal gate sentences). Before rewording anything, `grep tests/` for the sentence — the pin names
  the behaviour the wording carries, and CI fails on silent drift.

- **Line length:** hard cap of **160 characters** per line in every file (code, docs, tests) for
  all new and edited content. Structurally single-line content — markdown table rows, long URLs,
  the HTML diagram's markup, YAML frontmatter values — is the only exemption.

### Failure moments

Users judge the product at its stops, not its happy path:

- Every stop, refusal, or block gets a scripted message with the next action — no bare problem
  statements, no internal field names as the remedy.
- Name only exits that exist; a recipe must satisfy its own validator (code checks four fields →
  the message names four).
- A mechanism described on several surfaces has ONE canonical list; every echo matches verbatim,
  pinned in lock-step.

### Branching

- **Branch names must not contain slashes.** A `/` makes git create nested directories under
  `.git/refs/heads/` (e.g. `claude/feature-x` becomes `refs/heads/claude/feature-x`), which clutters
  the ref namespace and blocks a later branch from reusing that name as a leaf.
- Use **hyphens** instead: `claude-feature-x`, not `claude/feature-x`.

### Invariants

These rules are enforced by `tests/` — a change that breaks one fails CI:

- **Every shipped artifact has an owning test.** A new manifest, agent, command, or skill
  ships only with a test that fails when it is missing or malformed.
- **The plugin version is single-sourced.** `pyproject.toml` and `plugin/.claude-plugin/plugin.json`
  must carry the same version; CI fails on drift.
- **Red first, red possible forever.** A new test is born failing: write it before the feature or
  fix, watch it fail for the right reason, then make it pass — a test first seen green has proven
  nothing. And it must stay able to fail: anchor to a heading, pin the sentence that IS the
  feature, try the breaking edit once. `"auto" in lower` stays green on "automatically" — that's
  decoration, not a test.
- **Pin both ends of a cross-file contract.** Writer and reader, or one sync test — a reader-only
  pin stays green while the deleted writer bricks the product.

---

## Documentation style

Every doc, README, and diagram describes **the present state — what exists now**. Never write a
before/after comparison, a changelog narrative, or "previously / today / used to / changed from /
new vs old" framing in shipped docs. A reader who wants history runs `git diff` or reads the
changelog. This keeps docs readable and prevents them from rotting into a pile of "we used to…" notes.

Bad → good:

- ✗ "Mutation moved into the loop. Today's per-tier table is inverted; now it is flat."
  → ✓ "The mutation gate runs per spec, before retire, at the threshold the code-of-conduct sets."
- ✗ "⚑ New mechanism versus today" / "This reverses the earlier decision."
  → ✓ Describe the mechanism as it is.
- ✗ "Complexity is no longer re-scored in every phase."
  → ✓ "Complexity is scored once in Discover and read forward."

(The `CHANGELOG.md` is the one place history belongs; it is generated from Conventional Commits.)

---

## Testing

One language, one runner: **Python**. Everything is a pytest test under `python -m pytest tests/` —
the plugin-content lint and the A2A protocol/metric budgets.

```bash
# Set up once
pip install -e ".[dev]"

# Run everything — CI gates on >= 90% branch coverage (make test)
make test

# Branch coverage, same gate as CI
python -m pytest tests/ --cov=tests.metrics --cov-branch --cov-report=term-missing --cov-fail-under=90
```

Hercules holds itself to the bar it enforces on its users: **>= 90% branch coverage** (gated by
`make test`) and a **>= 90% mutation kill rate** (gated by `make test-mutation`). Both run in CI on
every PR — practice what we preach.

- **A surviving mutant is a verdict:** a missing test (write it) or better behaviour than the code
  (adopt it). Never a pragma to make it go away.

### Mutation pragmas are for static strings only

`# pragma: no mutate` is a hole in the mutation gate — every use must be defensible. Allowed only
on lines whose mutants are all behaviourally equivalent: static user-facing message strings, type
aliases, and codec arguments where every mutation still fails open. Never on a branch, comparison,
or return value — those get a killing test instead. Enforced by
`tests/hooks/test_hook_hygiene.py::test_pragma_no_mutate_only_on_static_strings`.

### Tests assert the present state, not the past

A test that only asserts a string is **absent** encodes a historical fix, not a present-state property —
CI can't tell a genuinely-guarded invariant from a stale memorial to one past bug. Pair every absence
check with either (a) a positive companion assertion (the correct replacement is present, or a related
cross-file invariant still holds) or (b) a named, specific, ongoing risk it guards against. Neither →
it's cosmetic; find the positive form.

### End-to-end smoke (manual)

The static suite (`tests/workflow/test_workflow_modes.py`) asserts the workflow commands carry the
right phase/mode directives, but Claude Code's permission-mode state can't be inspected from the
plugin. To verify the *effect* — that Discover → Design → Build → Ship actually produces its artifacts — run
the workflow by hand against a throwaway repo (install the plugin from a local-path marketplace, then
drive `/hercules:workflow`) and confirm a `*-business-requirements.md`, then `*-spec-NN-*.md`, then
code + tests appear in order, followed by a committed git record. This is a release-time manual check, not a CI gate — it needs a Claude
binary and credentials.

### What's covered

| Area | Where | Kind |
|------|-------|------|
| Marketplace + plugin manifests, default-agent persona, no-AGENT_TEAMS guard | `tests/plugin/test_plugin_integrity.py`, `tests/agents/test_agents.py` | unit + policy |
| Docs match the marketplace reality; version single-sourced | `tests/docs/test_docs.py` | policy |
| A2A protocol grammar and status vocabulary | `tests/metrics/test_a2a_grammar.py`, `tests/protocols/test_protocol_files.py` | unit + policy |
| Instruction and token budget checks | `tests/metrics/test_threshold_runner.py`, `tests/plugin/test_plugin_integrity.py` | unit + data-driven |
| Agent and skill file hygiene | `tests/agents/test_agents.py`, `tests/skills/test_skills.py` | policy |
| Command file structure | `tests/commands/test_commands.py` | policy |
| Frozen-test hook: behaviour, wiring, hygiene | `tests/hooks/test_frozen_tests_hook.py`, `tests/hooks/test_hooks_wiring.py`, `tests/hooks/test_hook_hygiene.py` | unit + policy |
| Workflow protocol: anchors, packet, registry↔commands, hook wiring | `tests/protocols/test_workflow_protocol.py` | policy |

### Adding a check

**A threshold/budget check → add a row to `tests/testdata/thresholds.json`** (no Python change):

```json
{
  "name": "my-file-token-budget",
  "target": "plugin/commands/discover.md",
  "metric": "token_count",
  "op": "<=", "limit": 400, "warn_at": 320,
  "severity": "warn"
}
```

- `target` — a path, or a comma-separated list of paths/globs. For a glob/list the metric is
  **summed** across all matched files.
- `metric` — one of: `instruction_count`, `token_count`, `core_entry_count`, `core_token_count`.
  Add new ones in `tests/metrics/threshold_runner.py` (`METRIC_REGISTRY`).
- `op` — `==`, `<=`, `>=`, `<`, `>`.
- `severity` — `gate` (fails the build) or `warn` (prints a warning, non-failing).
- `warn_at` (optional) — emit a warning when the value crosses this soft line while still under
  the hard `limit`.
- `per_file` (optional) — when `true`, apply the limit to **each** matched file individually
  (e.g. "every agent ≤ 800 tokens"), instead of summing the metric across the glob. The agent and
  skill token budgets use this, so a new agent or skill is gated automatically — no new row needed.

**A new metric → add a function to `tests/metrics/` and register it** in `METRIC_REGISTRY`.

### Budgets are fixed — stop and ask before you bump or cut

Token and instruction budgets in `tests/testdata/thresholds.json` are quality gates, not
obstacles: every token a command/agent/skill carries is consumed at startup and on every run,
eating context the model needs for good output. More tokens → less room to think → lower quality.

When a change would breach a budget, the assistant is the **guardian of the gate**. It must
**not** silently raise the threshold, and must **not** silently cut content to make room. Instead:

1. **Stop and surface it.** State plainly which budget would be exceeded and by how much, e.g.
   *"The token budget for the Discover phase (`discover.md`) would be exceeded — ~1390 / limit 1350."*
2. **Propose at least three options** and recommend one, for example:
   - **Tighten verbose prose** elsewhere in the file to absorb the addition (usually the best fit).
   - **Move content out** — extract detail into a separate file/reference the phase links to.
   - **Drop a lower-value instruction** to make room for the higher-value one.
   - **Raise the threshold** — only if the maintainer explicitly chooses this.
3. **Let the maintainer decide.** Apply only the chosen option.

Raise a threshold **only** when the maintainer explicitly instructs it in their own words. Absent
that explicit instruction, treat every threshold as immovable.

### Tokens

Token counts are computed with `tiktoken` (cl100k_base). The encoding file is fetched once and
cached; set `TIKTOKEN_CACHE_DIR` to a persistent directory to run the suite fully offline (CI
caches it under the same variable).

### Golden files

The injected A2A Core is pinned byte-for-byte in `tests/testdata/core.golden`. After an
intentional edit to the Core block, re-bless it:

```bash
cp plugin/protocols/a2a-communication-protocol.md /tmp/a2a.md  # then extract and overwrite core.golden
```

Or let the failing test tell you the expected value and paste it in.

All methodology checks are gates, not warnings. A failing gate means the change violates a
contract — fix the contract or the gate, not the test.
