---
name: code-of-conduct-generator
description: Generate or update a project's code-of-conduct — the single source of project standards every Hercules agent reads. Use on first run in a repo, or when a standard is missing.
---

# Code-of-Conduct Generator

The code-of-conduct is the highest-leverage file: every agent reads it. Tell the user: careful answers compound across every future feature.

## Method

**1. Filename.** Always `code-of-conduct.md` — the one name every command and agent reads. Confirm before writing anything.

**2. Existing CoC check.** File found → read in full; switch to **update mode** below. No file → new-file flow.

**3. Scan silently.** Work through the checklist below — tag each item `inferred-high`, `inferred-low`, `stated-unverified`, or `unknown`. Hard-exclude `.env*` and credential paths; record structure only, never values.

**4. Single-batch questions.** Ask 5–10 questions in one message — no trickle; minimum 5. Ask for *intent* (why this pattern? why this threshold?) — depth makes the CoC useful across features.

**5.** Call `EnterPlanMode`. Present the full CoC draft as the plan.

**6.** On approval: `ExitPlanMode` (`auto`) → write atomically (temp + rename) → add `@./code-of-conduct.md` to the project's `CLAUDE.md` if absent.

## Update mode

Rules that never bend: never rename, reorder, delete, or restructure existing sections or bullets. Additions only.

Gap analysis: missing items, conflicts (CoC says X, code does Y — surface as question, never auto-resolve), missing sections. Call `EnterPlanMode`; present an additions-only diff. Insert bullets in place; append new sections at the end.

## Scan checklist (internal agent guide — not CoC output)

- **Architecture:** directory layout · package strategy · primary pattern + enforcement · design patterns (name, problem, location) · module boundaries · dependency direction · DI/IoC approach · cross-cutting concerns
- **Development:** naming conventions · comment policy · error handling strategy · logging standards · null/Optional handling · async model · immutability · config management
- **Testing:** framework(s) · naming convention · structure (G/W/T vs. AAA) · BDD/Gherkin (scan `.feature` files; document runner, else omit) · mocking policy (per layer) · unit/integration/e2e/API scope · file locations · test data · isolation · performance tests
- **Quality Gates:** branch coverage threshold (suggest ≥90%) · mutation kill rate (suggest ≥90% when a mutation tool exists in the repo; else omit) · arch-unit checks · linter + config · formatter + config · static analysis tools · pre-commit hooks · CI gates · security/dependency scanning
- **API** *(omit section if no public API):* style · versioning · schema approach · docs format · backward-compat policy · error format · auth
- **Delivery:** branch model · commit format · PR requirements · merge strategy · release process · rollback · migration policy

## Output structure

5–6 `##` sections (`## API` conditional on public API). **Each section opens with 1–3 sentences explaining WHY these standards exist** — the constraint or lesson behind them. Then bullet points only; no prose in bullets; no intro or closing outside sections.

**Directive budget.** Every agent reads this whole file on top of its own instructions — aim for
**30–40** directives (one bullet = one directive; the section-opening WHY sentences don't count);
up to **50** for a large or polyglot repo; **70 is the hard ceiling**. Past 40 the delegate total
crosses the ~150-directive adherence line — 50–70 trades adherence for coverage; say so when
reporting the count. Near the band, merge near-duplicates and cut what the code makes obvious
(new-file flow only — in update mode existing bullets are never cut or merged; surface the
overage as a question).

**Never add Hercules attribution, AI mention, or generator reference to the output file** — it
reads as a human-authored standards document; note the generator's role in the commit message
instead.

## Corner cases

- Monorepo/polyglot: per-module subsections; never average conflicting values.
- Unknown values: write `unknown` — never invent defaults.
- Thin/empty repo: skip the scan; go straight to Q&A.

## Preconditions

Must run inside a git repository — if not, stop and say so. Confirm the target root before scanning.
