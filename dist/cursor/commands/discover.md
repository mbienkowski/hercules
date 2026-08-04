---
name: discover
description: Discover phase — turn a rough idea into a clear, approved business requirement
---

Turn a rough idea into a clear, approved business requirement — the foundation every other phase builds on. Plugin-file citations (`hercules-reference §…`, `protocols/…`) live in this plugin's directory.

**Plan mode — required.** Enter plan mode at the start. Every draft is a full inline proposal. Iterate freely; always regenerate the complete draft — never patch sections; never skip steps. At the **Plan approval** gate, on the user's approval, leave plan mode, then write.

## Step 0 — Artifact location & prior context

Resolve the **artifact root** per `hercules-reference § Artifact root resolution`: a `code-of-conduct.md`
directive wins (same-repo directory → use it; separate repo → ask its local path once), else
default to `docs/`. Note it as `docs_root` now — Step 7's session-init write persists it to the
registry entry (plan mode allows no writes). All paths below are relative to that root (shown as `docs/`).

Read `docs/INDEX.md` if present — one-line digest of recent sessions. Read `docs/learnings.md` if
present — surface entries matching the opening idea (key-match on topic); no-op if absent.

**Code of conduct (recommended).** No code-of-conduct file (any capitalization) in the repo? Tell the user it's the
biggest lever on output quality — every agent reads it for stack, test command, and bar — and offer
to generate one (`code-of-conduct-generator`). Proceed either way.

## Step 1 — Upfront context

Paste any documents you have — PRDs, ADRs, Figma links, QA test plans, API contracts, or a brain-dump. One sentence or ten pages. Say **"no documents"** to skip.

If documents provided: acknowledge them in 2–3 sentences. Note which groups (A–E) they already answer; skip those in Step 2.

If no documents: ask — > What do you want to build? Wait for the answer before anything else.

## Step 2 — Discovery (one group per turn)

One group per turn; wait for the answer before the next group. Plainly small idea (a fix, a
tweak)? Ask all six in one message instead — depth scales, the questions stay.

**Group A — Problem:** the real problem, and who is hurt by it today  
**Group B — Actors:** who uses this; how they cope now without it  
**Group C — Main flow & scope:** the path that matters; what is explicitly out of scope  
**Group D — Failure modes:** what has to fail gracefully, and what must never happen  
**Group E — Constraints:** time, compliance, integration; any API contracts or ADRs — link or paste them  
**Group F — Done:** the number or named standard that says it worked

Further banks open when the subject calls for them — data & privacy, money, access & roles,
volume, recovery & undo, regulatory, migration, adoption. The `document-contract` skill carries
those banks, the test for an answer too thin to build on, and the push-back ladder to use instead
of accepting it. Follow it rather than taking the first sentence offered: a vague answer here is
what a vague requirement is made of.

## Step 3 — Paraphrase, classify complexity & confirm

Paraphrase what you heard in 2–3 sentences so the user can correct any misunderstanding before scoring. Score against `${CURSOR_PLUGIN_ROOT}/protocols/debate-consensus-protocol.md` § complexity — both signal columns, then the higher of the two — and never restate its numbers here. Then show the judgement together with the choices open to the user:
> "I'm classifying this as **{tier} complexity** because [one sentence rationale]."
> "That convenes {n} advisors and allows {r}. Your call:"
> **keep it** at {tier} (recommended) · **lower it** to {next-lower} · **raise it** to {next-higher} · **answer freely**

At `trivial` there is nothing lower and at `critical` nothing higher, so offer the direction that exists and say the other does not.

This is shown **at every level**, trivial included, so the user always knows what is about to happen; it is never skipped to save a turn. Where the host offers a native selection control the four choices are presented through it, and everywhere else as a plain numbered list carrying the same four.

Wait for the user to confirm or override. On confirmation, record `tier` and `tier_rationale` — Step 7's session-init write persists them (plan mode allows no writes, and the session slug doesn't exist yet). Complexity is scored **once, here**, and read forward by Design and Build.

Neither this gate nor the roster gate writes state — the session-init write is Step 7. A session that ends between them leaves nothing half-written: say so and restart the phase rather than reconstructing an answer.

Every tier continues through Steps 4–7; the tier sets how many advisors run plus how far they debate, never which steps.

## Step 4 — Advisor debate

Advisors and debate depth both scale with the tier — the rubric is `protocols/debate-consensus-protocol.md` § complexity: `trivial` runs none, so skip to Step 5; `low` runs a reduced set that returns findings without cross-examining them; `medium` and up run the fuller set, with a later round only where the one before it left a topic contested. Read every count from the rubric; none is restated here. When advisors apply, follow the **Sub-agent consent** flow and pick the advisors the task needs (default: **business-analyst, challenger, simplicity-advocate**) — choose deliberately different, even opposing, perspectives so they argue, not echo. Productive disagreement beats easy consensus. On the user's go-ahead, run the debate per `${CURSOR_PLUGIN_ROOT}/protocols/debate-consensus-protocol.md`, scaled to the tier — each spawn carries the delegation packet (`${CURSOR_PLUGIN_ROOT}/protocols/workflow-protocol.md#packet`); fold the synthesis into the draft and flag contested points.

## Step 5 — Draft & feedback loop

Present the complete draft inline. Then ask:
> This is the draft. Review it and tell me what to change, add, or remove.

Do not create the file until formal **Plan approval** in Step 6 (the stakeholder nudge runs first, at medium+).

## Step 6 — Plan approval

This is the single **Plan approval** gate — *you approve the phase after reviewing the plan*, the same gate every phase ends on. Before accepting approval, verify all five core sections (Goal, Users, Scope, Constraints, Success criteria) have real content — no placeholders. Design references is optional (omit when no visual scope).

The gate accepts the canonical Plan-approval trigger words defined in `persona.md § Delivery workflow` — any other utterance is feedback; regenerate the draft, never silently proceed.

(medium+) Share this draft with stakeholders before locking. Say **"stakeholders approved"** or **"skip stakeholder review"** to proceed.

On the user's approval, leave plan mode, then write (Step 7) — no further prompts.

## Step 7 — Output

After approval, create (under the resolved artifact root, default `docs/`):
```
docs/YYYY-MM-DD-{short-desc}/YYYY-MM-DD-{short-desc}-business-requirements.md
```
- `{short-desc}` — 2–4 kebab-case words from the idea

File structure:
```markdown
# Business Requirements: {short-desc}

## Goal
...

## Users
...

## Scope
### In scope
...
### Out of scope
...

## Flows
### F1 — {flow name} ({actor})
- **Story** — as a {actor} I {do the thing} so that {outcome}.
- M1 | {trigger} → {observable outcome}
- N1 | {what goes wrong} → {what the user gets instead}

## Constraints
...

## Success criteria
...

## Risks & unknowns
(medium+ — what could bite, and the assumptions still open)

## Technical suggestions (non-binding)
(optional — the only place technical vocabulary is legal, and only as an option. Closes with:
"These are suggestions from Product, not decisions. Design owns the technical choice.")

## Design references
(Figma, wireframes, mockups, or other external design links — omit if none. Links only, no code.)
```

Section depth follows the tier — `python3 ${CURSOR_PLUGIN_ROOT}/tools/doc_lint.py template --kind business-requirements --tier {tier}` prints exactly the skeleton this tier expects. `M`/`N`/`C` are main, negative and corner scenarios; every flow names at least one way it can fail. The `document-contract` skill carries the notation, the corner-case selection heuristic, and the containment rules.

**Business language only** — committed and read by stakeholders. No class/method names, code, or file paths; implementation detail belongs in the spec. Design references hold visual-artifact links (Figma, wireframes), never implementation detail.

Write the session-init state under `~/.hercules/` (see `hercules-reference § Machine-local state`), never the repo. First, create or update the registry entry if needed (`directory`, `docs_root`, `state_file`), preserving `repositories`, `frozen_hook`, `keep_specs` on existing entries. Then run `python3 ${CURSOR_PLUGIN_ROOT}/tools/state_patch.py apply --project-slug {slug} --session-id {new-session-id} --set active_session={new-session-id} --set current_phase=discover --set tier={tier} --set tier_rationale={rationale} --confirm` to write the state file's session atomically. Non-zero exit: relay the output and stop. Preserve other entries/sessions.

Append a new row to `docs/INDEX.md` (create if absent) with `tier`, `discover` status,
and a one-line goal summary.

Show the saved path.

## Step 8 — Review

The requirements are reviewed by someone who did not write them — an **independent review**
(`hercules-reference § Independent review`), never a self-check.
Spawn `cynical-reviewer` with the delegation packet
(`${CURSOR_PLUGIN_ROOT}/protocols/workflow-protocol.md#packet`).
It reads the document **directly** and answers every category in the rubric
(`python3 ${CURSOR_PLUGIN_ROOT}/tools/doc_report.py rubric` prints them; `… template --kind
business-requirements` prints the shape), writing its answers beside the document as
`{same-name}-report.json`.

A category left unanswered is not a pass, and a pass must name what was checked — the judge refuses
a review that does neither, so an incomplete one costs a round rather than passing quietly.

Surface the reviewer's findings to the user as input, never as an auto-veto: a `blocker` or `major`
is theirs to accept, fix, or overrule with a reason.

Design will not open until this review says proceed — that gate runs on its own, so there is nothing
here to remember. Then say: "The requirements are locked. Ready for **Design**? Run `/design` — we'll shape the solution and delivery sequence there."
