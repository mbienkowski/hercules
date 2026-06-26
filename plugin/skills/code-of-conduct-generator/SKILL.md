---
name: code-of-conduct-generator
description: Generate or update a project's code-of-conduct.md — the single source of project standards every hercules agent and pillar reads. Use on first run in a repo, or when a needed standard is missing. Scans the repo, infers what it can, asks only what it must.
---

# Code-of-Conduct Generator

Produce `code-of-conduct.md` at the repo root: the one file that carries all project-specific variance (stack, conventions, quality bar) so the shipped agents can stay generic. Onboarding is lean — infer silently, ask rarely.

## Method
1. **Scan** the repo: directory structure, where/what tests live, mocking policy, lint/format command, language(s), business-vs-technical naming, branch/commit/PR norms from history.
2. **Seed the ~8–10 categories the pillars actually consume:** stack & frameworks, test command, lint/format command, test layout, mocking policy, churn ceiling / PR-line cap, branch & commit norms, readability-vs-performance weighting. (The full set can grow lazily when a skill first needs a missing category.)
3. **Ask ≤3–5 questions, only when a consumed standard is genuinely ambiguous** (with concrete example answers). A thin or empty repo routes straight to guided Q&A rather than fabricating values.
4. **Tag every category** with provenance + confidence: `inferred-high` / `inferred-low` / `stated-unverified` (README claim, unverified by code) / `q-and-a` / `human-edited` / `unknown` / `not-applicable`.
5. **Wire consumption:** add `@./code-of-conduct.md` to the project `CLAUDE.md` so it auto-loads.

## Corner cases
- **Existing file:** never clobber. Offer diff-preview, merge-gaps-only, or explicit full-regenerate (which first copies to `code-of-conduct.md.bak`). Re-runs respect `human-edited` fields.
- **Secrets/PII:** hard-exclude `.env*`, key material, and credential paths *before* reading; never echo a value — record only the structural fact ("uses an env-file").
- **Monorepo / polyglot:** emit per-module sections; cross-subdir conflicts are scoped by path, never averaged into a false global value.
- **README-only repo:** treat README claims as `stated-unverified`; code wins on conflict.

## Preconditions & write discipline
Confirm the target repo root before scanning; if it is not a repo, say so and stop. Write atomically (temp + rename); never blind-overwrite. Output is deterministic — stable category order, volatile data (timestamp, scan coverage) confined to a header — so a re-run on an unchanged repo produces a byte-identical body.

## Fallback
This skill *is* the code-of-conduct source. Where a value cannot be inferred or answered, write it as `unknown` (never a guessed default); downstream agents read `unknown` as "ask, don't assume."
