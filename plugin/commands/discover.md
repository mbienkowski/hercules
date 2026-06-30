# /hercules:discover

Turn a rough idea into a clear, approved business requirement — the foundation every other phase builds on.

**Plan mode — required.** Call `EnterPlanMode` at the start. Every draft is a full inline proposal. Iterate freely; always regenerate the complete draft — never patch sections; never skip steps. At the **Plan approval** gate, on the user's approval, call `ExitPlanMode` (`auto`), then write.

## Step 0 — Artifact location & prior context

Resolve the **artifact root** per `CLAUDE.md § Artifact root resolution`: a `code-of-conduct.md`
directive wins (same-repo directory → use it; separate repo → ask its local path once, cache it),
else default to `docs/`. Record it as `docs_root` in the project's registry entry (`~/.hercules/config.json`; see `CLAUDE.md
§ Machine-local state`). All paths below are relative to that root (shown as `docs/`).

Read `docs/INDEX.md` if present — one-line digest of recent sessions. Read `docs/learnings.md` if
present — surface entries matching the opening idea (key-match on topic); no-op if absent.

**Code of conduct (recommended).** No `code-of-conduct.md` in the repo? Tell the user it's the
biggest lever on output quality — every agent reads it for stack, test command, and bar — and offer
to generate one (`code-of-conduct-generator`). Proceed either way.

## Step 1 — Upfront context

Paste any documents you have — PRDs, ADRs, Figma links, QA test plans, API contracts, or a brain-dump. One sentence or ten pages. Say **"no documents"** to skip.

If documents provided: acknowledge them in 2–3 sentences. Note which groups (A–E) they already answer; skip those in Step 2.

If no documents: ask — > What do you want to build? Wait for the answer before anything else.

## Step 2 — Discovery (one group per turn)

One group per turn; wait for the answer before the next group.

**Group A — Goal & problem:** problem solved; who benefits and how  
**Group B — Users:** who uses this; current workflow without it  
**Group C — Scope:** what's in scope for v1; what's explicitly out of scope  
**Group D — Constraints:** technical, time, team size, compliance; any API contracts, ADRs, or integration specs? If yes, link or paste them.  
**Group E — Success criteria:** how you know it's done; what "good enough" looks like for v1

Ask 2–3 follow-ups within a group if the answer is thin. Move on only when the group is clear.

## Step 3 — Paraphrase, classify complexity & confirm

Paraphrase what you heard in 2–3 sentences so the user can correct any misunderstanding before scoring. Then state:
> "I'm classifying this as **complexity:X** because [one sentence rationale]."  
> "Do you agree, or would you like to override?"

Wait for the user to confirm or override. On confirmation, persist `tier` and `tier_rationale` to the active session in the project's state file (`~/.hercules/state/{slug}.json`; see `CLAUDE.md § Machine-local state`). Complexity is scored **once, here**, and read forward by Design and Build.

Every tier continues through Steps 4–7; the tier sets how many advisors run, never which steps.

## Step 4 — Advisor debate

The advisor count scales with the tier (`CLAUDE.md § Agent scaling`): `trivial` runs none — skip to Step 5; `low` runs a reduced set; `medium` and up run the fuller set. When advisors apply, follow the **Sub-agent consent** flow and pick the advisors the task needs (default: **business-analyst, challenger, simplicity-advocate**; at `low`, 1–2) — choose deliberately different, even opposing, perspectives so they argue, not echo. Productive disagreement beats easy consensus. On the user's go-ahead, run the debate per `protocols/debate-consensus-protocol.md`, scaled to the tier; fold the synthesis into the draft and flag contested points.

## Step 5 — Draft & feedback loop

Present the complete draft inline. Then ask:
> This is the draft. Review it and tell me what to change, add, or remove.  
> When satisfied, say **"approved"** and I will save the file.

Do not create the file until the user says "approved".

## Step 6 — Plan approval

This is the single **Plan approval** gate — *you approve the phase after reviewing the plan*, the same gate every phase ends on. Before accepting approval, verify all five core sections (Goal, Users, Scope, Constraints, Success criteria) have real content — no placeholders. Design references is optional (omit when no visual scope).

(medium+) Share this draft with stakeholders before locking. Say **"stakeholders approved"** or **"skip stakeholder review"** to proceed.

On the user's approval, call `ExitPlanMode` (`auto`), then write (Step 7) — no further prompts.

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

## Constraints
...

## Success criteria
...

## Design references
(Figma, wireframes, mockups, or other external design links — omit if none. Links only, no code.)
```

**Business language only** — committed and read by stakeholders. No class/method names, code, or file paths; implementation detail belongs in the spec. Design references hold visual-artifact links (Figma, wireframes), never implementation detail.

Write the session-init state under `~/.hercules/` (see `CLAUDE.md § Machine-local state`), never the
repo, atomically (temp + rename): the registry entry (`directory`, `docs_root`, `state_file`, empty
`repositories`) and the state file's session (`active_session`, `current_phase` `"discover"`, the
`tier` + `tier_rationale` from Step 3, `last_updated`). Preserve other entries/sessions.

Append a new row to `docs/INDEX.md` (create if absent) with `tier`, `active` status,
and a one-line goal summary.

Show the saved path. Then say: "The requirements are locked. Ready for **Design**? Run `/hercules:design` — we'll shape the solution and delivery sequence there."
