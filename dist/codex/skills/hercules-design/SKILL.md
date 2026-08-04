---
name: hercules-design
description: Design phase — turn a business requirement into numbered technical specs
---

Turn a business requirement into numbered technical specs ready for Build. Plugin-file citations (`hercules-reference §…`, `protocols/…`) live in this plugin's directory.

**Plan mode — required.** Enter plan mode at the start. Every draft is a full inline proposal; iterate freely; always regenerate the complete draft — never patch sections. At the **Plan approval** gate, on the user's approval, leave plan mode, then write.

Technical design and delivery sequencing wizard. Locate the business requirements, break them into self-contained specs, iterate, validate (implementability, then coverage with evidence), then take Plan approval and write. Never write without approval or with uncovered requirements.

## Step 1 — Session discovery

Read the **artifact root** (`docs_root`, default `docs/`) from the project's registry entry in
`~/.hercules/config.json` (see `hercules-reference § Artifact root resolution`). Find
`*-business-requirements.md` files inside its subdirectories.
List sessions that have a `*-business-requirements.md` but no specs yet:

```
Found sessions ready for design:
  1. docs/2026-06-14-user-auth/   (requirements written, no specs yet)
  2. docs/2026-06-10-payments/    (requirements written, no specs yet)

Which feature do you want to design? (number, path, or press Enter for the most recent)
```

If the path doesn't match, ask to confirm or correct. If no sessions are found, tell the user to run `$hercules-discover` first.

## Step 2 — Read requirements

Read the confirmed `*-business-requirements.md`. Extract every distinct requirement item. Summarise in 1–2 sentences before proceeding.

## Step 3 — Codebase constraint scan & read tier

Read the project's code-of-conduct (resolve it per `hercules-reference § Code-of-conduct resolution`) and any ADRs or API contracts the requirements reference, and scan the codebase for the surface this feature will touch (existing classes, modules, contracts). This scan feeds each spec's `## Affected code` section (do not scan again later) and bounds the Step 4 questions.

Read the session's `tier` from the project's state file (`~/.hercules/state/{slug}.json`). Complexity was scored once in Discover — **do not re-score it**; if the scan shows it was mis-scored, surface that and let the user override.

## Step 4 — Design questions (one group per turn)

Ask only what is needed — only what the Step 3 scan and `*-business-requirements.md` left open. Wait after each group.

**Group A — Architecture:** ask first whether API contracts or ADRs apply; read them before proceeding. Then: target stack, system context, external integrations. Does this feature span multiple services or repositories? If yes, name them — I'll structure the Architecture and Behaviour sections per service.  
**Group B — Data & behaviour:** data produced/consumed; critical business rules; UI/UX scope — wireframes, flows, visual design references?  
**Group C — Non-functional:** performance, security, scalability, accessibility beyond basics

## Step 5 — Advisor debate

Advisor count and debate depth both come from the tier read forward from Discover, scored against § complexity of the debate protocol cited below; its numbers are never restated here. Follow the **Sub-agent consent** flow and pick the advisors the task needs (default: **lead-architect, security-expert, senior-qa-engineer**). On the user's go-ahead, run the debate per `${PLUGIN_ROOT}/protocols/debate-consensus-protocol.md`, scaled to the tier — each spawn carries the delegation packet (`${PLUGIN_ROOT}/protocols/workflow-protocol.md#packet`); fold the synthesis into the draft and flag contested points.

## Step 6 — Draft & feedback loop

Present the complete draft inline. Then ask:
> This is the draft. Review it and tell me what to change, add, or remove.

Iterate: apply every change, show the updated draft, ask again, until the user is satisfied. Then run the Step 8 validation gates — the user gives formal **Plan approval** only in Step 9, after the draft is validated.

(medium+) Share this draft with stakeholders before locking. Say **"stakeholders approved"** or **"skip stakeholder review"** to continue.

## Step 7 — Falsify the assumptions this plan rests on

Before the plan is shown as approvable, check the few assumptions whose falsity would sink it. This
is **falsification, not proof**: it cannot show the plan will work — that would mean knowing the
result of executing it without executing it — but it does kill a plan that *cannot* work, for the
price of a few minutes, before anyone reads it.

Name at most **three** load-bearing assumptions: the things where, if wrong, the design is not
merely harder but different. Then for each, state what you expect to observe, show the user the
command before it runs, and run it:

```
python3 ${PLUGIN_ROOT}/tools/probe_run.py run --label {assumption} --tier {tier} \
  --expect "{what you expect to see}" --faked "{unwritten internals stood in for}" \
  --into docs/{session}/probes/probe-{label}.json -- {the command}
```

The tier sets how many probes and how long they may take (`probe_run.py budget` prints both; never
restate those numbers here). Probe classes in rank order: the dependency exists · the API has the
shape assumed · the external endpoint answers · the runtime supports the mechanism · the data
supports the requirement · the **seam** — walk the main and negative scenario end to end with real
external dependencies and hand-written stand-ins for internals that do not exist yet. The seam probe
is what makes this work on a greenfield codebase, where there is nothing else to run.

Two rules decide whether a verdict means anything, and both are enforced:

- **The expectation is stated before the run.** A command that asserts nothing can always be made to
  exit zero, so a probe with no pre-stated expectation is `UNPROVEN` however cleanly it exits.
- **A probe never fakes what it exists to check.** Standing in for an unwritten internal is the
  point; standing in for the dependency, the API or the data makes it green exactly where production
  fails, and is recorded as a failure.

`FAIL` means the plan is contradicted — return to Step 6 with the contradiction quoted, do not carry
it to approval. `UNPROVEN` means it could not be checked here: carry it to Step 9 verbatim as a named
risk, with an owner and the build step that will settle it. Run
`probe_run.py verify --tier {tier} --into docs/{session}/probes/` to confirm the tier's probes ran
and that `UNPROVEN` has not become the answer to everything.

## Step 8 — Validation gates (implementability, then coverage)

Implementability check — every file named in a spec's `## Affected code` must already exist or be explicitly marked new; every `satisfies:` header must resolve to a real `*-business-requirements.md` section. Block on any mismatch — do not paper over it.

Requirements coverage is an **independent review** (`hercules-reference § Independent review`), never a self-check: invoke the `$hercules-advisor-cynical-reviewer` skill with the delegation packet (`${PLUGIN_ROOT}/protocols/workflow-protocol.md#packet`). It reads `*-business-requirements.md` and the spec drafts **directly** (never a slice you pre-select) and, for every requirement item, cites the specific spec sentence that addresses it — no coverage by assumption or paraphrase. It returns the coverage matrix:
```
Requirements coverage:
  ✓ [requirement text]
    → "exact quote from the spec that addresses this"
  ✗ [requirement text]
    → NOT COVERED — no matching content found
  ~ [requirement text]
    → partially covered: "quote" — but missing [specific gap]
```

Sub-spec ownership — every requirement must map to at least one spec via that spec's `satisfies:` header; a requirement owned by no spec is a ✗ — it would never get built.

Note on n-1 — `*-business-requirements.md` is both the validation source and the only prior artifact (n-1); one read suffices.

Synthesise the reviewer's findings (that synthesis is the terminal judgment): if any requirement is uncovered or partially covered, do not write the specs — surface the matrix to the user at Step 9 as input and ask whether to extend the specs to cover them, or mark them explicitly out of scope (with a reason); a fix is re-checked by a fresh reviewer. Only proceed to Plan approval once every requirement is covered (with a quote) and owned by a spec, or explicitly out of scope.

## Step 9 — Plan approval

This is the single **Plan approval** gate — *you approve the phase after reviewing the plan*, the same gate every phase ends on. The implementability and coverage gates have already run, so what you approve is an already-validated plan. Present the validated specs + delivery order. The gate accepts the canonical Plan-approval trigger words defined in `persona.md § Delivery workflow` — any other utterance is feedback, not approval. **Do not write the specs until the user approves.** On approval, leave plan mode, then write (Step 10).

## Step 10 — Output

After Plan approval, create one file per spec under the artifact root
(default `docs/`), numbered in delivery order — there is no separate design file:
```
docs/YYYY-MM-DD-{short-desc}/YYYY-MM-DD-{short-desc}-spec-NN-{slug}.md
```

Every spec carries `covers:` — the scenario identifiers from the requirements' `## Flows` that it
delivers. Each must name a scenario that exists, and every scenario in the requirements must be
covered by exactly one spec. That is what turns the traceability gate at Build into a search for an
identifier rather than a judgement about whether two sentences mean the same thing.

Delivery order is the ascending `NN`: each spec is a self-contained delivery track, ordered so it
builds on the ones before it. For multiple services, scope each spec to a single service and name
that service in its `## Scope`.

Each sub-spec file structure:
```markdown
# Spec {NN}: {slug}
satisfies: [YYYY-MM-DD-{short-desc}-business-requirements.md §Section]
covers: [M1, N1, N2]
complexity: {tier}
profile: code

## Challenge
The one prose slot: the requirement restated in your own words, plus the single hardest thing
about it. Under 150 words, no technology named — a technology here is a decision, not a challenge.

## Scope
What this spec delivers (code paths, services, components).

## Affected code
Existing classes, methods, and modules this spec touches (from a codebase scan).

## Decision record
| Decision | Chosen | Rejected (why) | Risk of choice | Mitigation | Revisit when |
|---|---|---|---|---|---|

## Structure & patterns
(medium+) Each pattern named, why it applies, and one real use case. A deviation carries its WHY.

## Naming contract
(high+) Domain vocabulary, the names rejected, and why — the swap test and the cold-reader test.

## Implementation
Key technical decisions, patterns to follow, constraints from code-of-conduct.md.

## Rules — DO / DON'T
(high+) Two columns, imperative, each row checkable against a diff.

## Risks & mitigations
(medium+) Risk, the signal it is happening, the mitigation, and who owns it at build.

## Test suite
- **Unit:** [list what to unit-test] — mocking: [what must be mocked, what must never be, and why]
- **Integration:** [list integration scenarios]
- **API:** [list API contract tests, if applicable]
- **E2E:** [list end-to-end scenarios, if applicable]

## Acceptance criteria
Given / When / Then for each deliverable, each ending in the scenario it proves — `[M1]`, `[N2]`.

## Known violations
Architecture/dependency rules expected to fail at scaffold time, and which spec resolves them. Leave empty when none.

## Deletion note
Delete this file via `git rm` once its feature is delivered in code (a keep-specs code-of-conduct refreshes it instead). Code is the source of truth after delivery.
```

Section depth follows the tier — `python3 ${PLUGIN_ROOT}/tools/doc_lint.py template --kind spec
--tier {tier}` prints exactly the skeleton this tier expects, and the `document-contract` skill
carries the ambiguity replacements, the naming questions and worked fragments for each table.

The spec's depth is filled in by whichever specialist advisors ran in Step 5 — each contributing
into the relevant sections per its role. The template stays generic; the advisors make it specific.

If the feature is single-track (no meaningful split), emit one spec file (`spec-01`) covering the full scope.

Update `docs/INDEX.md`: set this session's `Status` to `design` if creating the row,
or update it in place if the row exists.

Update the active session in the project's state file by running `python3 ${PLUGIN_ROOT}/tools/state_patch.py apply --project-slug {slug} --session-id {id} --set current_phase=design --set pending_specs={spec-filenames-in-order} --confirm` to write atomically; Non-zero exit: relay the output and stop.

Show the saved spec paths in delivery order.

## Step 11 — Review

Each spec is reviewed by someone who did not write it — an **independent review**
(`hercules-reference § Independent review`), never a self-check.
Invoke the `$hercules-advisor-cynical-reviewer` skill with the delegation packet
(`${PLUGIN_ROOT}/protocols/workflow-protocol.md#packet`).
It reads each spec **directly** and answers every category in the spec rubric
(`python3 ${PLUGIN_ROOT}/tools/doc_report.py rubric`), writing its answers beside the spec as
`{same-name}-report.json`.

The rubric asks what no check can: does this answer the requirement in full, is any sentence
readable two ways, would a swapped library force a rename, could this be built as described. A
category left unanswered is not a pass.

Surface `blocker` and `major` findings to the user as input, never as an auto-veto.

Build will not open until every spec's review says proceed — that gate runs on its own, so there is
nothing here to remember. Then say: "The specs and delivery sequence are locked. Ready to **Build**? Run `$hercules-build` — I'll present a delivery plan first, then deliver the specs."
