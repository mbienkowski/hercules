---
name: code-of-conduct-generator
description: Generate or update a project's code-of-conduct — the single source of project standards every Hercules agent reads. Use on first run in a repo, or when a standard is missing.
---

# Code-of-Conduct Generator

The code-of-conduct is the highest-leverage file: every agent reads it, so careful answers compound
across every future feature. The generator drafts it through an advisor debate and proves every
directive against repo evidence before the user sees it.

The output states the **target repository's** standards only. Every enforced rule traces to that
repo's own code, tests, docs, or git history, or to an explicit user answer. Never leak Hercules's
process internals — its phases, commands, state, spec-first flow, or contributor rules — into a user's
file. Do, though, proactively **recommend** the engineering bar Hercules holds for AI-assisted code
(Step 4): a proposal for the user to accept or adjust, marked `(target)` where the repo does not yet
meet it, never a number silently assumed.

## Preconditions

Must run inside a git repository — if not, stop and tell the user to re-open Hercules inside the
target repository and re-invoke the skill. Resolve the **target** repo per
`CLAUDE.md § Code-of-conduct resolution` — the repo the standards govern, not always the launch
directory. When Claude was opened away from the code (a docs or requirements repo), or several
candidate roots exist (multi-repo, nested checkouts, sub-projects), list them from a real listing
(`ls`, `git rev-parse --show-toplevel`) and ask the user which repo the CoC is for before scanning.
Name the chosen root in the Step 1 roadmap so the user can still correct it.

## Method

### Step 1 — Plan mode, then the roadmap

Call `EnterPlanMode` first, before any scanning. Then give the user a chat summary of the flow —
scan → single-batch questions → advisor debate → validated draft → feedback → write →
review-and-commit — naming the detected root and the default advisor trio (final set settled
after the scan).

### Step 2 — Find any existing code-of-conduct

Find it case-insensitively: `code-of-conduct.md` or `CODE_OF_CONDUCT.md` (any capitalization) — scan
the root, `.github/`, and `docs/` with `find . -maxdepth 2 -iname 'code[-_ ]of[-_ ]conduct.md'`; an
uppercase-only repo is not one without standards.

- **One match** → read it; **update mode** below (in place, never a duplicate).
- **More than one** (a technical file and a `.github/` community doc are distinct) → never silently
  pick; list every match and confirm which is the standards target — that file enters update mode.
- **None** → ask where to create it (default `code-of-conduct.md` in the root), then new-file flow.

### Step 3 — Scan silently

Tag each checklist item `inferred-high`, `inferred-low`, `stated-unverified`, or `unknown`. Git
history is evidence, not just the tree: mine `git log` for the commit convention in use (format,
scope, tense, ticket refs), branch names and merge shape (merge commits vs. linear) for the
branching and merge strategy, and `git tag` for the release cadence. Mine repetition across code,
tests, and docs — design patterns, test naming and structure, annotation and comment habits. A
repeated pattern is a rule candidate; a one-off never is; two live patterns for one concern become a
Step 4 question — never majority rule. Hard-exclude `.env*` and credential paths; record structure,
never values.

### Step 4 — Single-batch questions

Ask 5–10 questions in one message — no trickle; minimum 5. Ask for *intent* (why this pattern? why
this threshold?), put every checklist `suggest` value (coverage, mutation) to the user so their
answer becomes its Step 6 proof, and chase whatever the scan or an existing code-of-conduct left
unclear — a stale bullet, a convention the code contradicts, a split pattern. Among them, recommend
the engineering bar Hercules holds for AI-assisted code: ≥90% coverage on **branches, not just
lines**; mutation testing at a ≥90% kill rate; architecture/dependency tests via the framework's
standard tool; a linter plus formatter so human- and AI-authored code read identically. Where the
repo lacks the tooling, recommend adopting it and mark the standard `(target)` — never silently drop
it. Tell the user plainly: AI-assisted code takes longer to bring to proper shape, but these gates
catch issues before production; they do not remove production-bug risk, they cut it sharply.

### Step 5 — Advisor debate

Recommend advisors and wait for consent per `CLAUDE.md § Sub-agent consent`. Default trio:
`lead-architect`, `senior-qa-engineer`, `challenger`; swap or extend to fit the repo. Debate per
`CLAUDE.md § Debate protocol`, complexity classified ad hoc (no session tier exists here). Each
advisor prompt carries the A2A Core (`CLAUDE.md § Agent-to-agent communication`), the tagged scan
findings, the Step 4 answers, and — update mode — the existing file: data no advisor can otherwise
see. Advisors weigh each candidate rule against contemporary practice — a dated convention becomes a
modernize-or-keep question for the user, never a silent choice — and return findings only; never ask
an advisor to write. In update mode they may propose dropping a stale, conflicting, or ambiguous
existing bullet — a proposal only; Step 7 decides.

### Step 6 — Synthesize, then prove

Synthesize the findings — on advisor skip or a trivial debate, the tagged scan and Step 4 answers
directly — into a full draft, held at a validation gate before presenting:

- **One reading** — every directive admits exactly one reading; reword or split any that reads two
  ways.
- **No conflicts** — no two directives may conflict; an existing-vs-new clash becomes a question for
  the user, never a silent resolution.
- **Proof** — every directive is backed by scan evidence, a line of the existing code-of-conduct, or
  an explicit user answer — "it looks nice" is not proof.
- **Checkable** — a reviewer can verify compliance from a diff, the repo, or CI output; reword or cut
  anything vague-aspirational.

Then break-test each directive yourself as a hostile reader — a second reading, a hidden conflict, a
claim the repo contradicts; fix and re-gate before presenting.

### Step 7 — Present and iterate

Present in plan mode: the full draft plus a summary naming the most important standards, what was
added, conflicts surfaced, what was dropped, and the directive count. Each debate-proposed drop is
its own explicit question; on the user's yes it is applied and the regenerated draft's summary lists
it as dropped. Iterate on feedback — always regenerate the complete draft, never patch sections; ask
more clarifying questions when feedback opens a gap. Every revision re-passes the Step 6 gate.

### Step 8 — Plan approval, then write

On the user's approval: `ExitPlanMode` (`auto`) → write atomically (temp + rename) → add an
`@`-reference to the written file's path (default `@./code-of-conduct.md`) to the project's
`CLAUDE.md`, creating `CLAUDE.md` when missing.

### Step 9 — Review, then commit

Show the written file and ask the user to review it. On their go-ahead, commit exactly the
code-of-conduct file plus `CLAUDE.md` when touched via pathspec (`git commit -- <paths>`) — never
reset or unstage the user's other work — in the repo's mined commit convention (Step 3), or a plain
imperative subject line when history gave none; note the generator's role in the message. Attribution
lives in the commit message, never in the file. Offer a push; never push automatically. No go-ahead →
reply: "Left uncommitted: {paths}. Say 'commit' when ready, or edit first."

## Update mode

Never rename, reorder, delete, or restructure existing sections or bullets on the generator's own
initiative — additions only. Exceptions: a debate-proposed drop (Step 5) after the user's explicit
yes (Step 7), and any edit the user directs in feedback — the rule binds the generator's initiative,
never the user.

Gap analysis: missing items, conflicts (CoC says X, code does Y — surface as question, never
auto-resolve), missing sections. Present an additions-only diff plus any drop questions; insert
bullets in place; append new sections at the end.

## Scan checklist (internal agent guide — not CoC output)

- **Architecture:** directory layout · package strategy · primary pattern + enforcement · design
  patterns (name, problem, location) · module boundaries
- **Development:** naming conventions · comment policy · error handling strategy · logging
  standards · null/Optional handling
- **Testing:** framework(s) · naming convention · structure (G/W/T vs. AAA) · BDD/Gherkin (scan
  `.feature` files; document runner, else omit) · mocking policy (per layer) ·
  unit/integration/e2e/API scope
- **Quality Gates:** branch (not just line) coverage ≥90% · mutation kill rate ≥90% when a
  mutation tool exists; else recommend adopting one, marked `(target)` · architecture/dependency
  tests (the framework's standard tool) · linter + config · formatter + config · CI gates ·
  security/dependency scanning
- **API** *(omit section if no public API):* style · versioning · schema approach · docs format ·
  backward-compat policy · error format · auth
- **Delivery:** branch model + merge strategy (mined from branches and history shape) · commit
  format (mined from `git log`) · PR requirements · release process (mined from `git tag`) ·
  rollback · migration policy

## Output structure

5–6 `##` sections in the scan checklist's order (`## API` conditional on public API); within a
section, most load-bearing bullets first. Each section opens with 1–3 sentences explaining WHY these
standards exist — a real constraint or lesson from evidence or user answers, never invented history.
Then bullets only — each a one-line imperative naming its concrete value (tool, threshold, format),
never a status-quo description; one terse inline example where showing beats telling, never a code
block; no intro or closing outside sections. Still unknown after Q&A → omit the bullet and name the
gap in the Step 7 summary (never invent defaults). Mark any standard the repo does not yet meet
`(target)` so a reader can tell enforced from aspirational.

**Directive budget.** Every agent reads this whole file on top of its own instructions — aim for
**30–40** directives (one bullet = one directive; the section-opening WHY sentences don't count);
up to **50** for a large or polyglot repo; **70 is the hard ceiling**. Past 40 the delegate total
crosses the ~150-directive adherence line — 50–70 trades adherence for coverage; say so when
reporting the count. Near the band, merge near-duplicates and cut what the code makes obvious
(new-file flow only — in update mode existing bullets are never cut or merged; surface the
overage as a question).

**Never add Hercules attribution, AI mention, or generator reference to the output file** — it must
read as a human-authored standards document; note the generator's role in the commit message.

## Corner cases

- Monorepo/polyglot: per-module subsections in the one root file; never average conflicting values.
- Multi-repo or opened elsewhere: generate for the target repo only — the service repo the work
  targets, never the launch or docs repo because it sits closest; one CoC per repo, never merged.
- Thin/empty repo → skip the scan, go straight to Q&A — the questions then carry the whole load.
