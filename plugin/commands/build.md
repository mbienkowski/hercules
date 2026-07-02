# /hercules:build

Plan the delivery, then execute the approved specs with TDD and full requirement traceability.

**Plan mode — required.** Build opens in plan mode like every other phase: call `EnterPlanMode`, present the **delivery plan**, and at the **Plan approval** gate — *you approve the phase after reviewing the plan* — call `ExitPlanMode` (`auto`). Execution then runs automatically, one spec at a time, with no further plan-mode prompts (a *ship each* "ship now" opens Ship's own plan).

---

## Plan mode

### Step 0 — Session context (resume)

Resolve the **artifact root** (`docs_root`, default `docs/`; `CLAUDE.md § Artifact root resolution`), then read the project's registry entry in `~/.hercules/config.json` and its state file `~/.hercules/state/{slug}.json` (`CLAUDE.md § Machine-local state`). If a session's `current_phase` is `"build"` and `current_spec` is set, show any `handed_off_by` / `handoff_note` and the latest `build_progress` checkpoint first, then offer:
> "You were building `{active_session}` on **{current_spec}**. Resume? Say **'resume'** or **'start fresh'**."

On 'start fresh': clear `current_spec`, `current_spec_round`, `frozen_test_files`, `delivered_specs`, and `pending_specs`, then proceed. On 'resume': after Step 1, skip to the spec matching `current_spec`.

On resume, reconcile against the filesystem: a spec in `delivered_specs` whose file still exists was interrupted before its delete — `git rm` it now; `pending_specs` drives remaining work. If the registry entry is missing but a state file exists, rebuild it. No entry or no `"build"` session → proceed silently.

### Step 1 — Session discovery

Find sessions ready for delivery — a session has `*-business-requirements.md` and at least one `*-spec-NN-*.md` still pending (not yet delivered).

Present a numbered list. Ask which to deliver (number, path, or Enter for most recent). If no sessions are found, tell the user to run `/hercules:design` first.

### Step 2 — Service paths

Each spec names its service in `## Scope`. If none are named, work in the current directory. Otherwise, for each named service not yet in the registry entry's `repositories` map (`~/.hercules/config.json`), ask for its local path, validate it exists, echo `"Found {service} at {path}"`, and write it to `repositories` (atomically; never into the repo).

Check for `code-of-conduct.md` at each service path (and the home repo for single-service). If absent, agents infer conventions from existing tests; the user can say **'generate conduct for {service}'** at any point.

### Step 3 — Read the specs & tier

Read `*-business-requirements.md` and the spec files from the confirmed session. List all `*-spec-NN-*.md` files in delivery order (ascending `NN`). Summarise each spec's scope and its "done".

Read the session's `tier` from the state file. Complexity was scored once in Discover — **do not re-classify, re-derive, escalate, or de-escalate it.** Only a manual user override changes it.

Use `pending_specs` order from a prior run, else a shell-sort of spec filenames.

### Step 4 — Present the delivery plan

Show the delivery plan for review: each spec, the requirement(s) it satisfies (its `satisfies:` links), the delivery order, and how the specs are grouped. State the count: `"{N} specs in delivery order."` The user can shape it before any code: **re-batch** ("do spec 1 & 2 together"), **reorder**, or set the **cadence** — deliver all in one pass, or ship each spec as it lands.

### Plan approval

The single **Plan approval** gate — *you approve the phase after reviewing the plan*, the same gate every phase ends on. On the user's approval, set `current_phase: "build"` and `current_spec` to the first spec in delivery order in the session's state file (atomic temp + rename), then call `ExitPlanMode` (`auto`); execution runs automatically per the approved batching and cadence.

---

## Execution (after Plan approval — automatic)

For each spec in delivery order, run this cycle, announcing `"Spec N of M"`. Spawns in this phase carry the delegation packet (`protocols/workflow-protocol.md#packet`).

1. **Read the spec.** Acceptance criteria, implementation guide, `satisfies:` links. Confirm what "done" means before writing a line of code.
2. **Scaffold.** Create empty classes, method signatures, and interfaces — no logic. Gate: the scaffold must compile before any tests are written.
3. **Write failing tests.** Invoke `write-test-scenarios` for the spec's scope and linked design section. Gate: every new test compiles **and fails for the right reason** — a real assertion of the requirement against the real interface, red only because the implementation is missing, never a syntax/runner error or forced failure. Frontend scope: suggest Gherkin e2e scenarios (Cypress/Playwright); keep scenario files in source control. Record the test files to `frozen_test_files`. **The tests are now frozen** — the agent does not edit them. Announce the freeze and its exits, as bullets: "change test X" (your words become a round-bound `frozen_override`; the edit proceeds this turn); "correct the test" at the round-limit stop; re-enter `/hercules:design`; `frozen_hook: "off"` for this project. Enforced, not promised: before the advance step, `git diff` the frozen files; any change outside the sanctioned user-decision path (step 5) or the current-round `frozen_override` blocks.
4. **Implement.** Write the minimum code to turn the failing tests green; refactor inline while the tests stay green. No test edits. No scope expansion. Respect `code-of-conduct.md`.
5. **Quality gates.** All tests pass, no regressions; and every quality gate the project's `code-of-conduct.md` defines passes — branch coverage, mutation kill rate, lint/format, type-checks, arch-unit checks — at the thresholds the CoC sets (Hercules carries no numbers of its own). Run the real tools, never a self-report. **Round limit:** at most 3 implementation rounds against the frozen tests; persist the count in `current_spec_round` so a resume can't reset it. Still failing after round 3 → stop, run a root-cause analysis (test defect, design gap, or genuine difficulty?), persist the checkpoint, mark the spec blocked, and hand the **user** the decision: correct the test (on their explicit grant record `frozen_override` — files, spec, round, quoted words — edit, re-pass the step-3 gate, clear it), re-enter `/hercules:design`, adjust scope, more rounds, or accept with a reason. The agent never edits a frozen test unprompted and never auto-advances.
6. **Mutation gate.** When the CoC requires one, meet its kill-rate threshold. Fix surviving mutants, or annotate an accepted-equivalent with a one-line reason. Runs before the spec is retired, so a weak test is strengthened while the spec is live.
7. **Traceability.** Each `satisfies:` requirement §section maps to ≥1 **named passing test** — the spec's own acceptance criteria passing is not sufficient; the business requirement needs a test asserting it. Each acceptance criterion maps to a test. Uncovered requirement → stop, re-enter `/hercules:design`.
8. **Advance.** Honour the cadence approved in plan mode. *Ship each* → pause: `"Spec N of M complete — tests green, traced. Ship now / continue / continue all"`; "ship now" cross-checks this spec, blocks on a regression, then runs `/hercules:ship` **spec-scoped** (ship.md § Spec-scoped ship); on failure control returns here and the spec is not retired. *Deliver all* → continue to the next spec without pausing.
9. **Write the checkpoint.** Append a `build_progress` entry to the session in state: the spec's acceptance criteria + `satisfies:` links, key decisions, interfaces, the named tests added, coverage %, mutation %, any accepted-equivalent reason, and constraints later specs must respect.
10. **Retire the spec.** As the **last** action for this spec, `git rm docs/{session}/{spec-filename}` — code is now the only source of truth. Update the session in state atomically (temp + rename): set `current_spec` to the next pending spec (or unset if none remain), append the filename to `delivered_specs`, drop it from `pending_specs`, reset `current_spec_round`. Multi-service: prefix spec references with `"{service}/"`.

For a spec scoped to a service (`## {service}` in the design): announce `"Now working in {service} at {local-path}."`, read `{service-path}/code-of-conduct.md` if present (it overrides the home CoC), and build absolute paths as `{service-path}/{path-from-repo-root}` for every Read/Write/Edit and Bash run — never a bare relative path.

## Cross-check validation (after all specs)

Spawn `hercules:cynical-reviewer` (Spec Sync) to cross-check the whole delivery — *does what we built match what we set out to build?* The specs are retired, so it reads each spec's record from the `build_progress` checkpoint + the permanent `*-business-requirements.md`, not the deleted files. Per spec: an intentional improvement is documented; a scope reduction is marked deferred; a bug or regression is a **blocker**. Then requirement traceability & drift, with cited evidence: every requirement maps to a delivered spec and a named passing test (`✓ [requirement] → evidence` / `✗ [requirement] → NOT COVERED`); and the reverse — shipped behaviour with no originating requirement is scope drift, surfaced for a disposition (amend `*-business-requirements.md`, or annotate deliberate/trivial). Drift on a high-risk surface (auth, secrets, money, migration, deletion, prod-config, concurrency) **blocks** until requirement-backed. Depth scales to tier: trivial/low a light pass; medium+ the full review; high/critical also spawn the relevant domain-expert.

Any undelivered spec or uncovered requirement → do not close out; the user resolves or defers with a reason.

## Capture learnings (all tiers)

Invoke the `learnings` skill to record what this delivery taught — every tier, not just high/critical.

## Close-out

After a passing cross-check there is no artifact to write — code, tests, and git history are the record.

Set this session's `Status` to `delivered` in `docs/INDEX.md` (atomic temp + rename).

Ask: "Is anyone taking over from here? Say 'handoff to {name}: {note}' to record it, or skip." Then write to the session in the state file (`~/.hercules/state/{slug}.json`) atomically: any `handed_off_by` / `handoff_note`, `current_spec: null`, `pending_specs: []`, `build_complete: true`, `last_updated`.

Show a one-line summary of what was delivered. Then run `/hercules:ship` to commit the delivered work.
