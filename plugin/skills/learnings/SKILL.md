---
name: learnings
description: Reconcile a reusable, project-scoped learning at Build close-out, and read relevant ones back in Discover. Use in the deliver pillar (write the learning) and in refinement (read prior learnings for the task's domain). Keeps a useful store, not a write-only log.
---

# Learnings

Accumulate decisions, patterns, and anti-patterns that make the next task better — a reconciled store keyed by stable id, never an append-only log.

## Write (Build close-out)
- **Reconcile, never blind-append:** match the candidate against existing entries by key; on a hit, update in place rather than stacking a near-duplicate.
- **Contradiction → newest-wins supersession:** the new learning replaces the one it contradicts; git history carries the "we changed our mind", so the live store states only what is currently true.
- **Stale → remove:** a learning contradicted by what shipped is deleted or superseded, not annotated with history.
- **Present-tense standing rules:** re-express anti-patterns as current truths — "writes are async; sync writes deadlock under load", not "we tried sync writes and they failed".
- **Classify:** project-specific business decisions stay in the store; genuinely generic rules are promoted to `code-of-conduct.md`.
- **Entry budget:** keep **20–30** entries; **40 is the hard ceiling** — Discover reads the
  whole store, so every entry is instruction load. At the cap every write is a trade: rank by
  **universality** (helps many future features, not one) and **importance** (cost of not knowing
  it), remove the weakest, and report what was dropped.
- **Secrets/PII gate:** scan before writing; a learning states the decision abstractly, never a secret value (the store is committed).

## Read (refinement)
Select by relevance keyed on the task's traceability IDs / domain — deterministic, not vibes. "No store" and "no relevant learning" are both a clean no-op, never an error.

## Preconditions & write discipline
Create the store on first write (create-or-update); write atomically (temp + rename) with whole-entry granularity so concurrent sessions merge cleanly. Hard-stop loud rather than producing a malformed entry.

## Project standards
Read `code-of-conduct.md` if present; it defines where the store lives and what counts as a
promotable generic rule. If absent, default the store to `docs/learnings.md` and state
the assumption.
