# /hercules:discover

**Plan mode — required.** Every draft is a full inline proposal. Iterate freely; write only on "approved". Always regenerate the complete draft — never patch sections. Never skip steps.

## Step 0 — Artifact location & prior context

Resolve the **artifact root** — where all documents are written — per `CLAUDE.md §
Artifact root resolution`: a `code-of-conduct.md` directive wins (same-repo directory →
use it; separate repository → ask for its local path once and cache it in the project's
home-config entry), otherwise default to `docs/` in the current directory. Record the resolved
path as `docs_root` in the project's home-config entry (see `CLAUDE.md § Machine-local state`).
All paths below are relative to that root (shown as `docs/`).

Read `docs/INDEX.md` if present; show a one-line digest of recent sessions.
Read `docs/learnings.md` if present; surface entries matching the user's opening idea
(key-match on topic). No-op if absent or no match.

## Step 1 — Upfront context

Paste any documents you have — PRDs, ADRs, Figma links, QA test plans, API contracts, or a brain-dump. One sentence or ten pages — bring it all. Say **"no documents"** to skip to questions.

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

## Step 3 — Classify complexity & confirm

State:
> "I'm classifying this as **complexity:X** because [one sentence rationale]."  
> "Do you agree, or would you like to override?"

Wait for the user to confirm or override before proceeding.

### Lightweight path (trivial / low only)

At `complexity:trivial` or `complexity:low`, run all pillars in a single auto-approved
pass; pause only on genuine ambiguity.

Produce: `docs/YYYY-MM-DD-{short-desc}/YYYY-MM-DD-{short-desc}-session.md`

Sections: `# Session` (complexity, date), `## Requirements` (goal + criterion, 2–4 sentences),
`## Spec` (1–3 Given/When/Then + one-line test note), `## Delivery` (empty).

Append a new row to `docs/INDEX.md` (create if absent) with status `active`.
Then say: "This is a lightweight task — running Design in one fast pass, then we Build." Point the user to `/hercules:build`. Do not proceed to Steps 4–7.

**Medium+ complexity:** continue to Steps 4–7 (normal flow).

## Step 4 — Advisor recommendation (medium+)

Follow the **Sub-agent consent** flow in `CLAUDE.md § Agent scaling`: recommend advisors for the Discover phase, explain why, and proceed only on the user's go-ahead.

## Step 5 — Draft & feedback loop

Present the complete draft inline. Then ask:
> This is the draft. Review it and tell me what to change, add, or remove.  
> When satisfied, say **"approved"** and I will save the file.

Do not create the file until the user says "approved".

## Step 6 — Validation gate

Before writing: verify all five core sections (Goal, Users, Scope, Constraints, Success criteria) have content — no placeholders. Design references is optional and omitted when there is no visual scope.

(medium+) Share this draft with stakeholders before locking. Say **"stakeholders approved"** or **"skip stakeholder review"** to proceed.

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

**Business language only** — this file is committed and read by business stakeholders at a high level. No class/method names, code, or file paths. Anything implementation-specific belongs in the spec, not here. Design references hold links to visual artifacts (Figma, wireframes), never implementation detail.

Write the session-init state to the project's `~/.hercules/hercules-config.json` entry (see
`CLAUDE.md § Machine-local state`) — never into the repo: `directory`, `active_session`
(`YYYY-MM-DD-{short-desc}`), `current_phase` `"discover"`, `docs_root`, empty `repositories`,
`last_updated`. Write atomically, preserving other entries and CLI-managed keys.

Append a new row to `docs/INDEX.md` (create if absent) with `tier`, `active` status,
and a one-line goal summary.

Show the saved path. Then say: "The requirements are locked. Ready to move to the **Design** phase? Run `/hercules:design` — we'll shape the technical solution and delivery sequence there."
