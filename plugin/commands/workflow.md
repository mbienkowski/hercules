# /hercules:workflow

**Plan mode — required across all phases.** Open each phase with `EnterPlanMode`; present a full inline proposal; on the user's "approved", call `ExitPlanMode` (choose accept-edits) to write the phase artifact, then `EnterPlanMode` for the next phase. Iterate freely; write only on "approved". Never patch sections — always regenerate the complete draft.

Guided end-to-end delivery: **Discover → Design → Build**. Runs all three phases in sequence with a human-approved transition between each. The more detail you put in early, the better the outcome.

---

## Opening

> Welcome to Hercules. We'll build this together, one phase at a time.
> Three phases: **Discover → Design → Build**
>
> Discovery is where we invest the most time — the better the requirements, the smoother the build.
> Bring everything you have: PRDs, ADRs, Figma links, QA scenarios. One sentence or ten pages.
> Let's start. 🔍 Entering the **Discover** phase.

---

## Phase 1 — Discover

*Purpose: pin the real need, not the first thing you said.*

Run the full `/hercules:discover` flow (Steps 0–6). When all five discovery groups (Goal, Users, Scope, Constraints, Success criteria) are covered, complexity is classified, and the `*-business-requirements.md` draft is approved and saved, pause:

> I think we have a clear picture of what you want to build.
> Before we move on — is there anything else you'd like to add or change here?
> This is the right moment: once we move to Design, the requirements are locked.
>
> Say **"move to Design"** or **"not yet"** to keep going here.

On "move to Design": announce "📐 Entering the **Design** phase." and continue.

### Lightweight shortcut
If complexity is `trivial` or `low` after Step 3 of Discover:
> "This is a lightweight task — I'll Design and sequence in one fast pass, then we Build."

Run the lightweight `*-session.md` path, then jump directly to Phase 3 (Build).

---

## Phase 2 — Design

*Purpose: turn the requirement into one or more self-contained specs and a delivery sequence.*

Run the full `/hercules:design` flow (Steps 1–8), reading the `*-business-requirements.md` written in Phase 1. When the design is approved, stakeholder review is complete (or skipped), coverage gate passes, and the sub-spec files are saved, pause:

> The specs and delivery sequence are solid. Before we move on — any final thoughts or changes here?
> Once we move to Build, the specs are locked.
>
> Say **"move to Build"** or **"not yet"** to keep going here.

On "move to Build": announce "⚒ Entering the **Build** phase." and continue.

---

## Phase 3 — Build

*Purpose: write failing tests, implement, review, and ship — one spec at a time.*

Run the full `/hercules:build` flow (Steps 1–6), reading `*-business-requirements.md` and the numbered spec files. When delivery is complete and `docs/INDEX.md` is marked delivered:

> ✓ Done. Here's what was built: [one-line summary]
> Check `docs/INDEX.md` for the full session record.
