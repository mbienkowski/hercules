# /hercules:design

**Plan mode — required.** Every draft is a full inline proposal. Iterate freely; write only on "approved". Always regenerate the complete draft — never patch sections.

Technical design and delivery sequencing wizard. Locate the business requirements, break them into one or more self-contained specs, iterate, validate coverage with evidence, write only after approval. Never write without approval and never write with uncovered requirements.

## Step 1 — Session discovery

Read the **artifact root** (`docs_root`, default `docs/`) from the project's entry in
`~/.hercules/hercules-config.json` (see `CLAUDE.md § Artifact root resolution`). Find
`*-business-requirements.md` files inside its subdirectories.
List sessions that have a `*-business-requirements.md` but no specs yet:

```
Found sessions ready for design:
  1. docs/2026-06-14-user-auth/   (*-business-requirements.md ✓, specs ✗)
  2. docs/2026-06-10-payments/    (*-business-requirements.md ✓, specs ✗)

Which feature do you want to design? (number, path, or press Enter for the most recent)
```

If the path doesn't match, ask to confirm or correct. If no sessions are found, tell the user to run `/hercules:discover` first.

## Step 2 — Read requirements

Read the confirmed `*-business-requirements.md`. Extract every distinct requirement item. Summarise in 1–2 sentences before proceeding.

## Step 3 — Classify complexity & confirm

> "I'm classifying this as **complexity:X** because [one sentence rationale]."  
> "Do you agree, or would you like to override?"

Wait for the user to confirm or override before proceeding.

## Step 4 — Design questions (one group per turn)

Ask only what is needed. Wait after each group. Skip groups already answered by `*-business-requirements.md`.

**Group A — Architecture:** ask first whether API contracts or ADRs apply; read them before proceeding. Then: target stack, system context, external integrations. Does this feature span multiple services or repositories? If yes, name them — I'll structure the Architecture and Behaviour sections per service.  
**Group B — Data & behaviour:** data produced/consumed; critical business rules; UI/UX scope — wireframes, flows, visual design references?  
**Group C — Non-functional:** performance, security, scalability, accessibility beyond basics

## Step 5 — Advisor recommendation

Follow the **Sub-agent consent** flow in `CLAUDE.md § Agent scaling`: recommend advisors for the Design phase, explain why, and proceed only on the user's go-ahead.

## Step 6 — Draft & feedback loop

Present the complete draft inline. Then ask:
> This is the draft. Review it and tell me what to change, add, or remove.  
> When you are satisfied, say **"approved"** and I will run the coverage check.

Iterate: apply every change, show updated draft, ask again.
Do not proceed to the validation gate until the user says "approved".

(medium+) Share this draft with stakeholders before locking. Say **"stakeholders approved"** or **"skip stakeholder review"** to continue.

## Step 7 — Validation gate (required before save)

Read `*-business-requirements.md`. For every requirement item, find the specific sentence in the spec drafts that addresses it. Do not declare coverage by assumption or paraphrase — cite directly.

Present the coverage matrix:
```
Requirements coverage:
  ✓ [requirement text]
    → "exact quote from the spec that addresses this"
  ✗ [requirement text]
    → NOT COVERED — no matching content found
  ~ [requirement text]
    → partially covered: "quote" — but missing [specific gap]
```

**Sub-spec ownership:** every requirement must map to at least one spec via that spec's `satisfies:` header. A requirement owned by no spec is a ✗ — it would never get built. Block the write until every requirement has an owning spec.

**Note on n-1:** `*-business-requirements.md` is both the validation source and the only prior artifact (n-1). One read is sufficient — the dual-source check becomes meaningful if a separate sequencing artifact is added later.

If any requirement is uncovered or partially covered, do not write the specs. Ask whether to:
- extend the specs to cover them, or
- mark them explicitly out of scope for this delivery (with a reason).

Only proceed once every requirement is covered (with a quote) and owned by a spec, or explicitly marked out of scope.

## Step 8 — Output

After approval and a passing coverage check, create one file per spec under the artifact root
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
- **Unit:** [list what to unit-test]
- **Integration:** [list integration scenarios]
- **API:** [list API contract tests, if applicable]
- **E2E:** [list end-to-end scenarios, if applicable]

## Acceptance criteria
Given / When / Then for each deliverable.

## Deletion note
Delete this file via `git rm` when its feature ships. Code is the source of truth after delivery.
```

The spec's depth is filled in by whichever specialist advisors ran in Step 5 — each contributing
into the relevant sections per its role. The template stays generic; the advisors make it specific.

**If the feature is single-track** (no meaningful split), emit one spec file (`spec-01`) covering the full scope.

Update `docs/INDEX.md`: set this session's `Status` to `active` if creating the row,
or update it in place if the row exists. Write atomically (temp + rename).

Update the project's entry in `~/.hercules/hercules-config.json`: set `current_phase` to `"design"`
and write `pending_specs` (the spec filenames in ascending delivery order). Write atomically,
preserving other entries.

Show the saved spec paths in delivery order. Then say: "The specs and delivery sequence are locked. Ready to **Build**? Run `/hercules:build` — I'll deliver each spec in order, tests first."
