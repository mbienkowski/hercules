---
name: solution-complexity-scoring
description: Score competing solution options on six prioritised dimensions and rank them lexicographically. Use in the Design pillar (medium+ complexity) when choosing between approaches, after the requirements exist. Produces a ranking and trade-off notes; writes no file of its own.
---

# Solution Complexity Scoring

Score each candidate solution 1–10 on six dimensions, in strict priority order:

1. **Production-readiness** — ship today with confidence?
2. **Readability** — a new contributor understands it in minutes; simple beats clever.
3. **Maintainability** — effort to change or extend later.
4. **Testability** — clear, automatable scenarios.
5. **Performance** — runtime/resource efficiency.
6. **Trade-offs** — how few compromises are forced.

Format: `Prod=8 Read=9 Maint=8 Test=9 Perf=7 Trade=8` plus an explicit trade-off list.

## Ranking — lexicographic, never an average
Compare by priority order: the option leading on Production-readiness wins; ties break on Readability, then Maintainability, and so on. **A weak low-priority dimension never flips an option that wins the higher-priority ones** — it only triggers a `<7` justification and a recorded trade-off. Averaging is banned because it lets a low Performance score sink the option that is actually best.

## Discipline
- Any score `<7` **or** `≥8` carries a one-line justification (justify both extremes; near-uniform all-9s is a smell → name each candidate's weakest dimension).
- **N=1** (only one candidate): score on the absolute rubric, not comparatively, and require either a real alternative or an explicit "no viable alternative — risk accepted".
- **Genuine tie** after walking all six: surface it to the human rather than inventing a tiebreaker.
- **Non-code task:** mark a dimension `N/A` (excluded from ranking) when it has no referent; never score a dimension that does not apply.
- **Unknowable dimension:** emit `Unknown` with the evidence that would resolve it — never a fabricated digit; an Unknown on a high-priority dimension blocks a confident verdict.

## Preconditions
The design must exist; if it is missing or empty, stop and ask the user to run `/hercules:design` first rather than scoring against guesses.

## Project standards
Read `code-of-conduct.md` if present; if it overrides the priority order (e.g. performance-first), echo the effective order in the output and re-rank under it. If absent, use the order above (readability beats performance) and state the assumption.
