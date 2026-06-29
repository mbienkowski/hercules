---
name: code-of-conduct-generator
description: Generate or update a project's code-of-conduct — the single source of project standards every Hercules agent reads. Use on first run in a repo, or when a standard is missing.
---

# Code-of-Conduct Generator

The code-of-conduct is the highest-leverage file: every agent reads it. Tell the user: careful answers here compound across every future feature — less ambiguity, faster delivery.

## Method

**1. Filename.** Scan existing files for casing — uppercase stems → `CODE_OF_CONDUCT.md`; lowercase → `code-of-conduct.md`; ambiguous → propose `CODE_OF_CONDUCT.md`. Confirm before writing anything.

**2. Existing CoC check.** File found → read in full; switch to **update mode** below. No file → new-file flow.

**3. Scan silently.** Work through the checklist below — tag each item `inferred-high`, `inferred-low`, `stated-unverified`, or `unknown`. Hard-exclude `.env*` and credential paths; record structure only, never values.

**4. Single-batch questions.** Ask 5–10 questions in one message — no trickle. Minimum 5. Ask for *intent* behind choices (why this pattern? why this threshold?) — that depth makes the CoC useful across future features.

**5.** Call `EnterPlanMode`. Present the full CoC draft as the plan.

**6.** On approval: `ExitPlanMode` (`auto`) → write atomically (temp + rename) → add `@./code-of-conduct.md` to the project's `CLAUDE.md` if absent.

## Update mode

Rules that never bend: never rename, reorder, delete, or restructure existing sections or bullets. Additions only.

Gap analysis: missing items, conflicts (CoC says X, code does Y — surface as question, never auto-resolve), missing sections. Call `EnterPlanMode`; present an additions-only diff. Execute by inserting bullets in place and appending new sections at the end.

## Scan checklist (internal agent guide — not CoC output)

- **Architecture:** directory layout · package strategy · primary pattern + enforcement · design patterns in use (name, problem solved, location) · module boundaries · dependency direction rules · DI/IoC approach · cross-cutting concerns
- **Development:** naming conventions · comment policy · error handling strategy · logging standards · null/Optional handling · async model · immutability · config management
- **Testing:** framework(s) · naming convention · structure (G/W/T vs. AAA) · BDD/Gherkin — scan for `.feature` files; if found, document runner; if absent, omit · mocking policy (per layer) · unit/integration/e2e/API scope · file locations · test data strategy · isolation requirements · performance tests
- **Quality Gates:** branch coverage threshold (suggest ≥90%) · mutation kill rate (suggest ≥90%) · arch-unit checks · linter + config · formatter + config · static analysis tools · pre-commit hooks · CI gates · security/dependency scanning
- **API** *(omit section if no public API):* style · versioning · schema approach · docs format · backward-compat policy · error format · auth
- **Delivery:** branch model · commit format · PR requirements · merge strategy · release process · rollback · migration policy

## Output structure

5–6 `##` sections (`## API` conditional on public API). **Each section opens with 1–3 sentences explaining WHY these standards exist** — the constraint, tradeoff, or lesson behind them. Then bullet points only; no prose in bullets; no intro or closing outside sections.


**Never add Hercules attribution, AI mention, or generator reference to the output file.** It reads as a human-authored standards document.

## Corner cases

- Monorepo/polyglot: per-module subsections; never average conflicting values.
- Unknown values: write `unknown` — never invent defaults.
- Thin/empty repo: skip the scan; go straight to Q&A.

## Preconditions

Must run inside a git repository. If not, stop immediately and say so. Confirm the target root before scanning.
