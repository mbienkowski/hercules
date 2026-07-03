---
description: Guided end-to-end delivery — all four Hercules phases in one flow
disable-model-invocation: true
---

# /hercules:workflow

Guided end-to-end delivery: all four phases in one flow. Plugin-file citations (`CLAUDE.md §…`, `protocols/…`) resolve under `${CLAUDE_SKILL_DIR}/..` — the plugin's install root, not this repo.

**Plan mode — required across all four phases.** Open each phase with `EnterPlanMode`; present a full inline proposal; at the **Plan approval** gate, on the user's "approved", call `ExitPlanMode` (`auto`) — the phase then writes or executes without further prompts — then `EnterPlanMode` for the next phase. Iterate freely; write only on approval. Never patch sections — always regenerate the complete draft.

Guided end-to-end delivery: **Discover → Design → Build → Ship**. Runs all four phases in sequence with a human-approved transition between each. The more detail you put in early, the better the outcome.

---

## Opening

> Welcome to Hercules. We'll build this together, one phase at a time.
> Four phases: **Discover → Design → Build → Ship**
>
> Discovery is where we invest the most time — the better the requirements, the smoother the build.
> Bring everything you have: PRDs, ADRs, Figma links, QA scenarios. One sentence or ten pages.
> Let's start. 🔍 Entering the **Discover** phase.

---

## Phase 1 — Discover

*Purpose: pin the real need, not the first thing you said.*

Run the full `/hercules:discover` flow (Steps 0–7). When all five discovery groups (Goal, Users, Scope, Constraints, Success criteria) are covered, complexity is classified, and the `*-business-requirements.md` draft is approved and saved, pause:

> I think we have a clear picture of what you want to build.
> Before we move on — is there anything else you'd like to add or change here?
> This is the right moment — after this, requirement changes need a fresh Discover pass.
>
> Say **"move to Design"** or **"not yet"** to keep going here.

On "move to Design": announce "📐 Entering the **Design** phase." and continue.

---

## Phase 2 — Design

*Purpose: turn the requirement into one or more self-contained specs and a delivery sequence.*

Run the full `/hercules:design` flow (Steps 1–9), reading the `*-business-requirements.md` written in Phase 1. When the design is approved, stakeholder review is complete (or skipped), coverage gate passes, and the sub-spec files are saved, pause:

> The specs and delivery sequence are solid. Before we move on — any final thoughts or changes here?
> After this, spec changes go through `/hercules:design` again.
>
> Say **"move to Build"** or **"not yet"** to keep going here.

On "move to Build": announce "⚒ Entering the **Build** phase." and continue.

---

## Phase 3 — Build

*Purpose: present the delivery plan, then write failing tests, implement, validate, and deliver each spec.*

Run the full `/hercules:build` flow, reading `*-business-requirements.md` and the numbered spec files. Build opens in plan mode with a **delivery plan** (which specs, the requirement each satisfies, the order and grouping) — you approve it and set the cadence (deliver all in one pass, or ship each), then it auto-executes. When delivery is complete and `docs/INDEX.md` is marked delivered:

> ✓ Build complete — tests green, traced, delivered.
>
> Review the diff, run the tests, make any final adjustments. When ready:
> Say **"move to Ship"** or run `/hercules:ship` directly.

---

## Phase 4 — Ship

*Purpose: commit the delivered work and push to the remote.*

Run the full `/hercules:ship` flow (Ship will draft its own plan — files to stage, commit
message, push target — and wait for your approval). When complete:

> ✓ Shipped. Commit: [conventional commit one-liner]
> Run `/hercules:workflow` any time to start the next feature.
