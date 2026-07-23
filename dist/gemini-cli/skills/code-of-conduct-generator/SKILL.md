---
name: code-of-conduct-generator
description: Generate or update a project's code-of-conduct — the single source of project standards every Hercules agent reads. Use on first run in a repo, or when a standard is missing.
---

# Code-of-Conduct Generator

The code-of-conduct is the highest-leverage file — every agent reads it, so careful answers compound.
The generator drafts it **evidence-first**, then proves each rule before the user sees it. The detailed
scan tactics and output format live in the companion `coverage-map.md`; this file is the spine.

## Invariants

The file states the **target repository's** enforced standards only — never Hercules's process internals
(phases, commands, state, spec-first flow, contributor rules). It states only what is enforced today;
anything recommended-but-unmet is offered in chat, not written in the file. Never average two
conflicting values.

## Preconditions

Must run inside a git repository — else **stop** and tell the user to re-open Hercules in the target
repository and re-invoke. Resolve the **target** repo per `hercules-reference § Code-of-conduct resolution`, not
the launch directory; if Gemini was opened away from the code or several candidate roots exist, list
them (`ls`, `git rev-parse --show-toplevel`) and ask which repo the CoC is for. Run every scan, `find`,
and git command against that root (`git -C <root>`), never bare `.`.

## Method

1. **Plan mode & mode** — enter plan mode first, before any scanning; give a chat summary of the
   flow and offer **Quick** (small/low-stakes default: scan → a few questions → draft → gate → review →
   commit) or **Thorough** (adds the coverage-map gap pass and an advisor critical-review pass). Name the detected
   root so the user can correct it.
2. **Find existing CoC** — find it case-insensitively (any capitalization of `code-of-conduct.md` or
   `CODE_OF_CONDUCT.md`) across root/`.github/`/`docs/` (`find <root> -maxdepth 2 -iname
   'code[-_ ]of[-_ ]conduct.md'`). One match → **update mode**; but a lone `.github/` behavioural
   Contributor Covenant is not an engineering standard — treat it as none and create a separate file.
   **More than one** → never silently pick; list every match and confirm the target. None → default
   `code-of-conduct.md` in the root.
3. **Scan (≤5 min)** — run the **§ Scan playbook** in `coverage-map.md`: bounded and config-first,
   size-adaptive, mining git history for the commit/branch/merge/release conventions, reconciling config
   against code, capturing a citation per observation.
4. **Questions** — ask a single batch in one message — no trickle. The main agent decides the count
   each run but **never asks fewer than 5–8 questions** (minimum 5, up to 8 or more for a large or
   polyglot repo); even Quick asks at least this many, since a fuller interview signals deeper, more
   thorough work. Ask *intent*, resolve split patterns, and force an explicit accept/decline on each recommended gate.
   Recommend in chat the AI-assisted quality bar — branch (not just line) coverage, a mutation gate
   where a mutation tool exists, architecture/dependency tests via the framework's standard tool, a
   linter + formatter; accepted-with-tooling becomes a rule, the rest stay chat advice.
5. **Draft** — draft rules only from scan observations and user answers, formatted per **§ Output
   format** in `coverage-map.md`: lead with a `## Non-negotiables (MUST)` block, then themed sections —
   Architecture (design patterns in use, and why), Development, Testing, Quality Gates (coverage;
   mutation), Security & Data, Delivery — each rule naming its check inline and tagged MUST/SHOULD;
   explain a rule's *why* only where it changes interpretation.
6. **Gap pass & critical review** (Thorough) — run `coverage-map.md` once as a stack-gated gap detector: each
   load-bearing omission is a chat recommendation (accept → rule, decline → absent), offered
   highest-value first and never past the directive budget. Then one `challenger` critically reviews the draft
   per `hercules-reference § Sub-agent consent`, carrying the A2A § Agent-Injected Core plus the observations; a full trio is
   opt-in or automatic for a contested repo, per `hercules-reference § Debate protocol`; advisors return findings
   only, never write. Quick runs a light platitude/no-evidence self-scan instead.
7. **Gate & present** — hold the draft until every rule clears the gate: reads exactly one way;
   conflicts with no other; is backed by a captured observation or a user answer ("it looks nice" is not
   proof); names an objective mechanical check — and **dry-run each cited check, dropping any that
   fails** (full rationale in **§ Output format**). Then present it with a short summary (top standards,
   added, conflicts, dropped), surfacing only the ~5 genuine decisions ranked by marginal information —
   never a long list to curate. Feedback applies **surgically** with a diff of what changed; regenerate
   wholesale only when the user reopens the scope, and re-gate only what changed.
8. **Approve & write** — on approval: leave plan mode → write atomically (temp + rename) → add a
   deduplicated `@`-reference (default `@./code-of-conduct.md`) to the **target** repo's `GEMINI.md`,
   creating it when missing.
9. **Review & commit** — show the file and ask the user to review it. On their go-ahead, **stage then
   commit** exactly the code-of-conduct file plus `GEMINI.md` when touched — `git add -- <paths>` then
   `git commit -m … -- <paths>` — so an untracked new file commits cleanly and the user's other staged
   work is never reset or swept in; use the mined commit convention or a plain imperative subject.
   Attribution lives in the commit message, never in the file. Offer a push; never push automatically.
   No go-ahead → reply: "Left uncommitted: {paths}. Say 'commit' when ready, or edit first."

## Update mode

Never rename, reorder, delete, or restructure existing sections or bullets on the generator's own
initiative — additions only. Exceptions: a critical-review-proposed drop after the user's explicit yes, and any
edit the user directs. Gap analysis surfaces missing items, conflicts (the CoC says X, the code does Y —
a question, never auto-resolved), and missing sections; present an additions-only diff plus any drop
questions, insert bullets in place, and append new sections at the end.

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

- Monorepo/polyglot: per-module subsections in the one root file.
- Multi-repo or opened elsewhere: one CoC per repo, never merged.
- Thin/empty repo: lean on Q&A and ship a small labelled seed.
