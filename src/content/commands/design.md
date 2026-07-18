---
description: Design phase — turn a business requirement into numbered technical specs
disable-model-invocation: true
---

# ${ns}design

Turn a business requirement into numbered technical specs ready for Build. Plugin-file citations (`hercules-reference §…`, `protocols/…`) live in this plugin's directory.

${target:claude}
**Plan mode — required.** Call `${plan_enter}` at the start. Every draft is a full inline proposal; iterate freely; always regenerate the complete draft — never patch sections. At the **Plan approval** gate, on the user's approval, call `${plan_exit}` (`auto`), then write.
${target:opencode}
**Plan mode — required.** Enter plan mode at the start. Every draft is a full inline proposal; iterate freely; always regenerate the complete draft — never patch sections. At the **Plan approval** gate, on the user's approval, leave plan mode, then write.
${target:end}

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

If the path doesn't match, ask to confirm or correct. If no sessions are found, tell the user to run `${ns}discover` first.

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

Follow the **Sub-agent consent** flow and pick the advisors the task needs (default: **lead-architect, security-expert, senior-qa-engineer**; see `hercules-reference § Agent scaling`). On the user's go-ahead, run the debate per `${plugin_root}protocols/debate-consensus-protocol.md`, scaled to the tier — each spawn carries the delegation packet (`${plugin_root}protocols/workflow-protocol.md#packet`); fold the synthesis into the draft and flag contested points.

## Step 6 — Draft & feedback loop

Present the complete draft inline. Then ask:
> This is the draft. Review it and tell me what to change, add, or remove.

Iterate: apply every change, show the updated draft, ask again, until the user is satisfied. Then run the Step 7 validation gates — the user gives formal **Plan approval** only in Step 8, after the draft is validated.

(medium+) Share this draft with stakeholders before locking. Say **"stakeholders approved"** or **"skip stakeholder review"** to continue.

## Step 7 — Validation gates (implementability, then coverage)

Implementability check — every file named in a spec's `## Affected code` must already exist or be explicitly marked new; every `satisfies:` header must resolve to a real `*-business-requirements.md` section. Block on any mismatch — do not paper over it.

Requirements coverage is an **independent review** (`hercules-reference § Independent review`), never a self-check: spawn `${agent_ns}cynical-reviewer` with the delegation packet (`${plugin_root}protocols/workflow-protocol.md#packet`). It reads `*-business-requirements.md` and the spec drafts **directly** (never a slice you pre-select) and, for every requirement item, cites the specific spec sentence that addresses it — no coverage by assumption or paraphrase. It returns the coverage matrix:
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

Synthesise the reviewer's findings (that synthesis is the terminal judgment): if any requirement is uncovered or partially covered, do not write the specs — surface the matrix to the user at Step 8 as input and ask whether to extend the specs to cover them, or mark them explicitly out of scope (with a reason); a fix is re-checked by a fresh reviewer. Only proceed to Plan approval once every requirement is covered (with a quote) and owned by a spec, or explicitly out of scope.

## Step 8 — Plan approval

${target:claude}
This is the single **Plan approval** gate — *you approve the phase after reviewing the plan*, the same gate every phase ends on. The implementability and coverage gates have already run, so what you approve is an already-validated plan. Present the validated specs + delivery order. **Do not write the specs until the user approves.** On approval, call `${plan_exit}` (`auto`), then write (Step 9).
${target:opencode}
This is the single **Plan approval** gate — *you approve the phase after reviewing the plan*, the same gate every phase ends on. The implementability and coverage gates have already run, so what you approve is an already-validated plan. Present the validated specs + delivery order. **Do not write the specs until the user approves.** On approval, leave plan mode, then write (Step 9).
${target:end}

## Step 9 — Output

After Plan approval, create one file per spec under the artifact root
(default `docs/`), numbered in delivery order — there is no separate design file:
```
docs/YYYY-MM-DD-{short-desc}/YYYY-MM-DD-{short-desc}-spec-NN-{slug}.md
```

Delivery order is the ascending `NN`: each spec is a self-contained delivery track, ordered so it
builds on the ones before it. For multiple services, scope each spec to a single service and name
that service in its `## Scope`.

Each sub-spec file structure:
```markdown
# Spec {NN}: {slug}
satisfies: [YYYY-MM-DD-{short-desc}-business-requirements.md §Section]
complexity: {tier}

## Scope
What this spec delivers (code paths, services, components).

## Affected code
Existing classes, methods, and modules this spec touches (from a codebase scan).

## Implementation
Key technical decisions, patterns to follow, constraints from code-of-conduct.md.

## Test suite
- **Unit:** [list what to unit-test] — mocking: [what must be mocked, what must never be, and why]
- **Integration:** [list integration scenarios]
- **API:** [list API contract tests, if applicable]
- **E2E:** [list end-to-end scenarios, if applicable]

## Acceptance criteria
Given / When / Then for each deliverable.

## Deletion note
Delete this file via `git rm` once its feature is delivered in code (a keep-specs code-of-conduct refreshes it instead). Code is the source of truth after delivery.
```

The spec's depth is filled in by whichever specialist advisors ran in Step 5 — each contributing
into the relevant sections per its role. The template stays generic; the advisors make it specific.

If the feature is single-track (no meaningful split), emit one spec file (`spec-01`) covering the full scope.

Update `docs/INDEX.md`: set this session's `Status` to `design` if creating the row,
or update it in place if the row exists. Write atomically (temp + rename).

Update the active session in the project's state file (`~/.hercules/state/{slug}.json`): set
`current_phase` to `"design"` and write `pending_specs` (the spec filenames in ascending delivery
order). Write atomically (temp + rename), preserving other sessions.

Show the saved spec paths in delivery order. Then say: "The specs and delivery sequence are locked. Ready to **Build**? Run `${ns}build` — I'll present a delivery plan first, then deliver the specs."
