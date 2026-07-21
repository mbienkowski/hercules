---
description: Build phase — plan the delivery, then execute approved specs with TDD
disable-model-invocation: true
---

# /hercules:build

Plan the delivery, then execute the approved specs with TDD and full traceability. Plugin-file citations (`hercules-reference §…`, `protocols/…`) live in this plugin's directory.

**Plan mode — required.** Build opens in plan mode: call `EnterPlanMode`, present the **delivery plan**, and exit through the **Plan approval** gate below. Execution then runs automatically, spec by spec (a *ship each* "ship now" opens Ship's own plan).

---

## Plan mode

### Step 0 — Session context (resume)

Resolve the **artifact root** (`docs_root`, default `docs/`; `hercules-reference § Artifact root resolution`), then read the registry entry and state file (`~/.hercules/config.json`, `~/.hercules/state/{slug}.json`; `hercules-reference § Machine-local state`). Surface any `handed_off_by` / `handoff_note` whenever present. If a session's `current_phase` is `"build"` and `current_spec` is set, show the latest `build_progress` checkpoint, then offer:
> "You were building `{active_session}` on **{current_spec}**. Resume? Say **'resume'** or **'start fresh'**."

On 'start fresh': clear `current_spec`, `current_spec_round`, `frozen_test_files`, `frozen_override`, `pending_specs`, `build_progress`, and `delivered_specs` (under `keep_specs: true` keep `delivered_specs` and their `build_progress` checkpoints — the cross-check needs their record), then proceed. On 'resume': Steps 1–4 stay brief (prior answers stand); present the resume plan — current spec, round, stored `cadence` — and take **Plan approval** as usual; execution then starts at the spec matching `current_spec`.

On resume, reconcile against the filesystem: a spec in `delivered_specs` whose file still exists was interrupted before its delete — finish it now (`git rm` if tracked, else plain delete; skip under `keep_specs: true`); a spec with a `build_progress` checkpoint still in `pending_specs` finished building but missed retire — apply step 10's state updates, don't re-execute; `pending_specs` drives remaining work; drop `frozen_test_files` entries with no file on disk. If the registry entry is missing but a state file exists, rebuild it. No entry or no `"build"` session → proceed silently.

### Step 1 — Session discovery

Find sessions with specs not yet delivered: the state lists a non-empty `pending_specs` (never count `delivered_specs` — kept specs stay on disk); with no state file, `*-business-requirements.md` plus spec files on disk counts.

Present a numbered list. Ask which to deliver (number, path, or Enter for most recent). If no sessions are found, tell the user to run `/hercules:design` first.

### Step 2 — Service paths

Each spec names its service in `## Scope`; none named → work in the current directory. Otherwise, for each named service not yet in the registry entry's `repositories` map (`~/.hercules/config.json`), ask for its local path, validate it exists, echo `"Found {service} at {path}"`, and write it to `repositories` (atomically; never into the repo).

Check for the code-of-conduct file (any capitalization) at each service path (and the home repo for single-service). If absent, agents infer conventions from existing tests; the user can say **'generate conduct for {service}'**. A CoC directive to keep specs is cached as `keep_specs: true` in the registry entry (re-check each run; remove the key when the directive is gone).

### Step 3 — Read the specs & tier

Read `*-business-requirements.md` and the confirmed session's spec files. List all `*-spec-NN-*.md` files in delivery order (ascending `NN`). Summarise each spec's scope and its "done".

Read the session's `tier` from the state file. Complexity was scored once in Discover — **do not re-classify, re-derive, escalate, or de-escalate it.** Only a manual user override changes it.

Use `pending_specs` order from a prior run, else a shell-sort of spec filenames minus `delivered_specs`.

### Step 4 — Present the delivery plan

Show the delivery plan: each spec, the requirement(s) it satisfies (its `satisfies:` links), the delivery order, the grouping. State the count: `"{N} specs in delivery order."` The user can shape it before any code: **re-batch**, **reorder**, or set the **cadence** — deliver all in one pass, or ship each spec as it lands.

### Plan approval

The single **Plan approval** gate — *you approve the phase after reviewing the plan*, the same gate every phase ends on. The gate accepts the canonical Plan-approval trigger words defined in `persona.md § Delivery workflow` — any other utterance is feedback; regenerate the plan, never silently proceed. On the user's approval, call `ExitPlanMode` (`auto`) first, then set `current_phase: "build"`, `current_spec` to the first pending spec (on resume, the interrupted one), and the approved `cadence` (`"deliver-all"` / `"ship-each"`) in the session's state file (atomic temp + rename) and this session's `Status` to `build` in `docs/INDEX.md`; execution runs automatically per the approved batching and cadence.

---

## Execution (after Plan approval — automatic)

For each spec in delivery order, run this cycle, announcing `"Spec N of M"`. Spawns in this phase carry the delegation packet (`${CLAUDE_PLUGIN_ROOT}/protocols/workflow-protocol.md#packet`).

1. **Read the spec.** Acceptance criteria, implementation guide, `satisfies:` links. Confirm what "done" means before writing code. Classify the change: `annotation-only` (scaffold gate satisfied by existing code → skip to Step 3), `net-new`, `refactor`, or `mixed`.
2. **Scaffold.** Create empty classes, method signatures, and interfaces — no logic. Gate: the scaffold must compile before any tests are written.
3. **Write failing tests.** **Mandatory:** invoke `write-test-scenarios` for the spec's scope and its `## Test suite` section (skip only on its own precondition stop). Gate: every new test compiles **and fails for the right reason** — a real assertion of the requirement against the real interface, red only because the implementation is missing, never a syntax/runner error or forced failure. Frontend scope: suggest Gherkin e2e scenarios (Cypress/Playwright), kept in source control. Record the test files to `frozen_test_files`, their SHA-256 baselines to `frozen_baseline` (`{path: sha256}`, re-verified at retire, Step 10), and set `current_spec_round: 1` in the same atomic write (overrides bind to the round). **The tests are now frozen** — the agent does not edit them.    Announce the freeze and its exits as bullets: "change test X" (your permission is recorded — and the edit proceeds this turn); the round-limit stop's five options (step 5); `frozen_hook: "off"` for prompt-only. Backstop: before advance, `git diff` frozen files; any change outside the sanctioned path (step 5) or current-round `frozen_override` blocks; clear a consumed `frozen_override` here.
4. **Implement.** Write the minimum code to turn failing tests green; refactor inline while tests stay green. No test edits. No scope expansion. Respect `code-of-conduct.md`. Before freezing, confirm each new guard/assertion can actually fail against realistic input — upstream normalization may make it unreachable; surface as a warning. On constructor/signature changes with existing tests, run test-compile before the full check.
5. **Quality gates.** All tests pass; every CoC-defined gate passes — branch coverage, mutation kill rate, lint/format, type-checks, arch-unit checks — at the CoC's thresholds (Hercules carries no numbers of its own). Coverage thresholds apply **per touched file** (`## Affected code`), not just aggregate — verify per file. Run the real tools, never a self-report. **Round limit:** at most 3 implementation rounds against the frozen tests; persist in `current_spec_round` so resume can't reset it. Still failing after round 3 → stop, root-cause, persist checkpoint, and ask:
   > "Three rounds in, {spec} still fails {N} tests — my read: {root cause}. Your call: **correct the test** (tell me the fix — I record your grant and edit), **rework the design** (`/hercules:design`), **adjust scope**, **more rounds**, or **accept with a reason**."

   On a correct-the-test grant, record `frozen_override` — files, spec, round, quoted words — and edit; gate: the corrected test compiles and asserts the corrected requirement (green against existing code is the expected pass); then clear the override. The agent never edits a frozen test unprompted and never auto-advances.
6. **Mutation gate.** When the CoC requires one, meet its kill-rate threshold. Fix surviving mutants, or annotate an accepted-equivalent. Runs before retire, so weak tests are strengthened while the spec is live.
7. **Traceability.** An **independent review** (`hercules-reference § Independent review`), never a self-check: spawn `hercules:cynical-reviewer` with the packet (`${CLAUDE_PLUGIN_ROOT}/protocols/workflow-protocol.md#packet`); reading the spec's `satisfies:` + `*-business-requirements.md` + the test files **directly**, it maps each `satisfies:` requirement §section to ≥1 **named passing test** — and each acceptance criterion to a test. Synthesise: an uncovered requirement → stop, re-enter `/hercules:design`.
8. **Advance.** Honour the cadence approved in plan mode. *Ship each* → pause: `"Spec N of M complete — tests green, traced. Ship now, continue (next spec), or continue all (finish the rest without pausing)?"`; "ship now" cross-checks this spec, blocks on regression, runs `/hercules:ship` **spec-scoped** (ship.md § Spec-scoped ship); on failure control returns here and the spec is not retired. *Deliver all* → continue without pausing.
9. **Write the checkpoint.** Append a `build_progress` entry: acceptance criteria + `satisfies:` links, key decisions, interfaces, named tests added, coverage %, mutation %, constraints for later specs.
10. **Retire the spec.** **Acceptance backstop first:** recompute each `frozen_baseline` entry's SHA-256; any changed-or-deleted file not under a current-round `frozen_override` = a tampered acceptance test → **HALT and tell the user**, don't retire (it catches tampering the tool-time hooks miss). Only then, as the **last** action, `git rm docs/{session}/{spec-filename}` (plain delete if never committed) — code is now the source of truth — or, with `keep_specs: true`, keep and refresh to match what shipped. Update state atomically (temp + rename): set `current_spec` to next pending (or unset), append to `delivered_specs`, drop from `pending_specs`, remove `current_spec_round`, clear `frozen_test_files` and `frozen_override`. Multi-service: prefix spec refs with `"{service}/"`.
For a spec scoped to a service (named in its `## Scope`): announce `"Now working in {service} at {local-path}."`, resolve that service's CoC (§ CoC resolution; overrides the home CoC), and build absolute paths as `{service-path}/{path-from-repo-root}` for every Read/Write/Edit and Bash run — never a bare relative path.

## Cross-check validation (after all specs)

Spawn `hercules:cynical-reviewer` to cross-check the whole delivery — *does what we built match what we set out to build?* Specs are retired, so it reads each spec's `build_progress` checkpoint + the permanent `*-business-requirements.md`. Intentional improvement documented; scope reduction marked deferred; bug or regression is a **blocker**. Requirement traceability & drift with evidence: every requirement maps to a delivered spec and a named passing test (`✓ [requirement] → evidence` / `✗ [requirement] → NOT COVERED`); reverse drift (shipped behaviour with no originating requirement) is surfaced. Drift on a high-risk surface (auth, secrets, money, migration, deletion, prod-config, concurrency) **blocks** until requirement-backed. Depth scales to tier: trivial/low light; medium+ full; high/critical add the domain-expert.

For a single-spec delivery, the cross-check may merge with Step 7's traceability review — spawn `hercules:cynical-reviewer` once with both mandates.

Any undelivered spec or uncovered requirement → do not close out; the user resolves or defers with a reason.

## Capture learnings (all tiers)

Invoke the `learnings` skill to record what this delivery taught — every tier, not just high/critical.

## Close-out

After a passing cross-check there is no artifact to write — code, tests, and git history are the record.

Set this session's `Status` to `delivered` in `docs/INDEX.md`.

Ask: "Anyone taking over? Say 'handoff to {name}: {note}', or skip." Then write to `~/.hercules/state/{slug}.json` atomically — **all** end-of-Build mutations (`handed_off_by`/`handoff_note`, `current_spec: null`, `pending_specs: []`, `build_complete: true`, `last_updated`) in **one** temp + rename (`persona.md` § 9).

Show a one-line summary. Review the diff; run `/hercules:ship` when ready.
