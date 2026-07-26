# Business requirements: migrate Hercules' build & test tooling from Python to TypeScript

## Problem

The maintainer is a TypeScript native, not a Python native. Maintaining the build system
currently requires trusting AI-generated Python he cannot confidently review, debug, or modify
unaided. The project is already fundamentally *JSON descriptors compiled to file trees* — a
domain TypeScript's types and schema validation fit better than Python does.

## Who benefits

The maintainer, as the sole contributor responsible for reviewing and extending the build
compiler, the CI scripts, and the test estate.

## Outcome

The compiler, the CI scripts, and the test estate become TypeScript on Node 22. The shipped
enforcement hooks (`src/hooks/*.py`) stay Python 3 forever — they run as `python3` in every
user's environment across all six ecosystems, and porting them would force a Node runtime
dependency on every consumer. The migration is invisible to end users of all six ecosystems:
no change to `src/content/`, `src/ecosystems/` formats, or `dist/` output bytes.

## Success criteria

- The maintainer can read, review, and extend the build compiler without relying on trust alone.
- Every quality gate the Python compiler enforced today (≥90% branch coverage, ≥90% mutation
  kill rate) is met or exceeded by the TypeScript replacement.
- `dist/` — the actual shipped product across all six ecosystems — is byte-for-byte unchanged
  throughout and after the migration.
- The two-runtime end state (TypeScript for the compiler and tests, Python for the hooks island)
  is discoverable: an on-call contributor can tell which runtime owns a red check within seconds,
  by name alone (`test-py`/`test-ts`, `mutation-py`/`mutation-ts`).
- The mutation testing that currently takes 40–50 minutes in one Python job runs as two parallel
  jobs (Python hooks, TypeScript compiler) — a CI wall-clock win, not merely a lateral move.

## Out of scope

- Rewriting `src/hooks/*.py` in TypeScript or shipping a Node runtime dependency to users.
- Any change to `src/content/`, `src/ecosystems/` formats, or `dist/` output bytes.
- Any user-visible behaviour change of any kind, in any ecosystem.
- Cucumber/Gherkin E2E testing (evaluated and explicitly declined in an earlier debate captured
  in `.opencode/plans/hercules-migration-to-typescript.md`).

## Constraints

- Delivered as one long-lived branch (`feat-typescript-build-tooling`), ~17 commits, single merge
  to `main`. Every commit must independently compile and pass its tests — the branch must be safe
  to abandon at any point without leaving `main` in a broken state.
- Per tool: add the TypeScript version *alongside* the Python original and mechanically prove
  identical output, before deleting the Python original in a later commit.
- Full fresh-eyes advisor review (parallel specialist agents, then independent adversarial
  verification) before every commit lands — no self-certification.

## Governing artifact

The technical plan — locked architectural decisions, the full commit sequence, the fault-injection
parity harness design, and the few-shot DO/DON'T catalogue the implementing work followed — was
carried in a companion spec file that was **retired at delivery**, per the project convention that a
spec is write-once and deleted once its feature ships in code (see `CODE_OF_CONDUCT.md`). The delivered
work is now the source of truth; the git history of this branch preserves the commit sequence.
