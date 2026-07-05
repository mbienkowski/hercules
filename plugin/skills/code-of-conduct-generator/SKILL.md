---
name: code-of-conduct-generator
description: Generate or update a project's code-of-conduct — the single source of project standards every Hercules agent reads. Use on first run in a repo, or when a standard is missing.
---

# Code-of-Conduct Generator

The code-of-conduct is the highest-leverage file: every agent reads it, so careful answers compound
across every future feature. The generator drafts it **evidence-first** — from what this repo has
actually decided — then proves and gap-checks every rule before the user sees it.

## Invariants (hold in every step)

The emitted file states the **target repository's** enforced standards only. Every shipped rule traces
to a scan observation (file, count, or commit) or an explicit user answer — never invented, and never
Hercules's own process internals (its phases, commands, state, spec-first flow, or contributor rules).
The file reads as human-authored: no Hercules, AI, or generator attribution in it — that belongs in the
commit message. It states only what is **enforced today**; anything recommended-but-unmet is offered in
chat, not written as an aspirational marker in the file. Never average two conflicting values.

## Preconditions

Must run inside a git repository — if not, **stop** and tell the user to re-open Hercules inside the
target repository and re-invoke the skill. Resolve the **target** repo per
`CLAUDE.md § Code-of-conduct resolution` — the repo the standards govern, not always the launch
directory. When Claude was opened away from the code, or several candidate roots exist (multi-repo,
nested checkouts, sub-projects), list them (`ls`, `git rev-parse --show-toplevel`) and ask the user
which repo the CoC is for. Run every scan command against that root (`git -C <root>`), never bare `.`.

## Method

### Step 1 — Plan mode, roadmap, and mode

Call `EnterPlanMode` first, before any scanning. Give the user a chat summary of the flow and offer a
mode: **Quick** (the default for a small or low-stakes repo — scan → ~3 questions → draft → review →
commit) or **Thorough** (adds the coverage-map gap pass, priority tuning, and an advisor red-team).
Name the detected target root so the user can correct it.

### Step 2 — Find any existing code-of-conduct

Find it case-insensitively: `code-of-conduct.md` or `CODE_OF_CONDUCT.md` (any capitalization) — scan
the root, `.github/`, and `docs/` with `find <root> -maxdepth 2 -iname 'code[-_ ]of[-_ ]conduct.md'`.

- **One match** → read it; **update mode** below. But a lone `.github/` file that is a *behavioural*
  Contributor Covenant is not an engineering standard — treat it as none and create a separate file.
- **More than one** (a technical file and a `.github/` community doc are distinct) → never silently
  pick; list every match and confirm which is the standards target.
- **None** → default to `code-of-conduct.md` in the root; new-file flow.

### Step 3 — Scan the target repo (bounded ≤5 min, evidence-first)

Resolve the coverage-map points (`coverage-map.md`) from the repo, cheapest signals first, under a hard
**5-minute cap**. A sizing probe (`git ls-files | wc -l`, an extension histogram, workspace/monorepo
detection) picks the path: small → config plus a generous sample; large or monorepo → root config plus
a few representative modules per language, never every module — proceed sampled and invite the user to
point at key modules or grant more budget, never block. Standards live in tooling config, so read
manifests and config first, use grep counts as evidence, sample ~20–30 files, and note repeated design
patterns and test conventions. Mine bounded history: `git log -n 200` for the commit convention, branch
names and merge shape for the branching/merge strategy, `git tag` for releases. **Reconcile config
against code** — a rule the config states but the sampled code violates becomes a Step-4 question, never
an enforced rule. Capture each observation (`file:line` / count / commit) so a rule can cite it; on the
cap, stop and mark the rest `unknown`. Two live patterns for one concern become a question — never
majority rule. Exclude `.env*` and credential paths; record structure, never values. Persist the scan
and answers to `~/.hercules/state/{slug}-coc.json` so a re-invoke resumes.

### Step 4 — Questions

Thorough asks 5–10 questions in one message — no trickle; minimum 5 (Quick asks ~3). Ask for *intent*
(why this pattern? why this threshold?), resolve any split pattern, and force an explicit accept or
decline on each recommended gate so a recommendation is never silently assumed. Use a fixed
question-priority order (widest confidence-gap first) so repeated runs stay deterministic.

### Step 5 — Evidence-first draft

Draft rules only from scan observations and user answers. Lead the file with a flat
`## Non-negotiables (MUST)` block — the ~10 rules that must never be violated — then themed sections:
Architecture (with the design patterns in use and why they exist), Development, Testing, Quality Gates
(coverage; mutation), Security & Data, and Delivery. Each rule is a one-line imperative that names its
**mechanical check** inline (a grep, a lint rule, a CI gate, or a numeric threshold), tagged **MUST** or
**SHOULD**. A numeric threshold must quote a user answer or a computed repo statistic, never a padded
default. Explain a rule's *why* only where it changes interpretation. Scale the file to the evidence — a
thin repo ships a small, clearly-labelled seed, never padded to fill a band.

### Step 6 — Gap pass, then red-team

Run the coverage-map once as a **gap detector** (stack-gated — load only the groups the scan detected):
for each applicable point with no drafted rule, surface it in chat as a recommendation — accept makes it
a real rule, decline drops it. Then **red-team** the draft: one challenger, consented per
`CLAUDE.md § Sub-agent consent` and carrying the A2A Core plus the captured observations, hunts
no-evidence rules, platitudes, hidden conflicts, and rules the code contradicts; fix and re-gate. A full
trio (lead-architect, senior-qa-engineer, challenger) is opt-in, or automatic for a contested or
high-blast-radius repo, debated per `CLAUDE.md § Debate protocol`. Advisors return findings only, never
write; in update mode they may propose dropping a stale bullet — Step 8 decides.

### Step 6b — Validation gate

Hold the draft until every rule: reads exactly one way; conflicts with no other; is backed by a captured
observation or a user answer — "it looks nice" is not proof; and names a mechanical check a reviewer can
run from a diff, the repo, or CI. Emit the rule→evidence citations as an auditable appendix and
re-verify a sample of them against the source. Break-test each rule as a hostile reader before
presenting.

### Step 7 — Present and iterate

Present the draft plus a short summary: the most important standards, what was added, any conflict
surfaced, and what was deferred. Surface only the **genuine decisions** — the few rules near the budget
line and any unresolved conflict — ranked by marginal information so obvious hygiene never outranks a
repo-specific invariant; do not hand the user a long list to curate. Feedback applies **surgically**,
with a diff of exactly what changed; regenerate the whole draft only when the user reopens the scope,
and re-run the gate only on what changed.

### Step 8 — Approve, then write

On the user's approval: `ExitPlanMode` (`auto`) → write atomically (temp + rename) → add an
`@`-reference to the written file (default `@./code-of-conduct.md`) to the **target** repo's `CLAUDE.md`
if absent, creating `CLAUDE.md` when missing and never duplicating an existing reference.

### Step 9 — Review, then commit

Show the written file and ask the user to review it. On their go-ahead, **stage then commit** exactly
the code-of-conduct file plus `CLAUDE.md` when touched — `git add -- <paths>` then
`git commit -m … -- <paths>` — in the repo's mined commit convention, or a plain imperative subject when
history gave none; never reset or unstage the user's other work. Attribution lives in the commit
message, never in the file. Offer a push; never push automatically. No go-ahead → reply:
"Left uncommitted: {paths}. Say 'commit' when ready, or edit first."

## Update mode

Never rename, reorder, delete, or restructure existing sections or bullets on the generator's own
initiative — additions only. Exceptions: a red-team-proposed drop of a stale, conflicting, or ambiguous
existing bullet after the user's explicit yes, and any edit the user directs. Gap analysis surfaces
missing items, conflicts (the CoC says X, the code does Y — a question, never auto-resolved), and
missing sections; present an additions-only diff plus any drop questions, insert bullets in place, and
append new sections at the end.

## Output budget

**Directive budget.** Every agent reads this whole file on top of its own instructions — aim for
**30–40** directives (one bullet = one directive; the section-opening WHY sentences don't count);
up to **50** for a large or polyglot repo; **70 is the hard ceiling**. Past 40 the delegate total
crosses the ~150-directive adherence line — 50–70 trades adherence for coverage; say so when
reporting the count. Near the band, merge near-duplicates and cut what the code makes obvious
(new-file flow only — in update mode existing bullets are never cut or merged; surface the overage
as a question). A mutation gate ships only when a mutation tool exists in the repo; otherwise
mutation testing is a chat recommendation, never a file rule.

## Corner cases

- Monorepo/polyglot: per-module subsections in the one root file; never average conflicting values.
- Multi-repo or opened elsewhere: generate for the target repo only; one CoC per repo, never merged.
- Thin/empty repo: skip the scan, ask a few forward-looking questions, ship a small labelled seed.
