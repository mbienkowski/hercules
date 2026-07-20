# Spec 09: mutation-performance
satisfies: [2026-07-10-universal-plugin-distribution-business-requirements.md §v1.1 R4]
complexity: high

## Scope
Cut the mutation-quality gate from ~40 minutes to well under 10 minutes without weakening it, by
aligning the per-mutant test runner with the test directories that actually cover the mutated
modules. Add a guard so the scope cannot silently drift, and harden the crash-masking that could
otherwise report a false green. Do **not** change the mutant population, the 90% threshold, or the
per-mutant timeout.

## Affected code
- `pyproject.toml` `[tool.mutmut]` — `runner` scoped to the covering directories:
  `python -m pytest tests/build/ tests/hooks/ tests/metrics/ -x -q --tb=no --no-header`.
- `Makefile` — `test-mutation` target: keep the gate script; make a crashed/interrupted `mutmut run`
  fail loud instead of being swallowed by `|| true`.
- `scripts/check_mutation_gate.py` — harden so an interrupted/empty/corrupted run (the `_count()`
  path that swallows a broken mutmut cache to `0`) is a hard failure, not a pass.
- `.github/workflows/ci.yml` — `mutation` job `timeout-minutes` 40 → ~15 (headroom). This spec owns
  only `runner`/`timeout`/gate-hardening on that job; Spec 07 owns its `needs`/`if`.
- New guard test under `tests/` — fails if any module in `paths_to_mutate` is exercised by a test
  living outside the runner's directory set.

## Implementation
- Root cause (fresh independent board): the 40 minutes is a *runner mismatch*, not a mutant-count
  problem. mutmut runs the whole `tests/` suite (~530 tests / 62 files) per mutant, but only
  `tests/build/`, `tests/hooks/`, `tests/metrics/` import/exercise the mutated modules; the other ~25
  directories cannot kill any mutant yet pay full cost every iteration.
- **Why safety is preserved:** because no excluded test imports a mutated module, no excluded test can
  kill any mutant — so the kill rate is *provably unchanged* and the 90% threshold keeps its exact
  meaning (no recalibration). This is verified empirically once (kill-rate before == after).
- The runner scope is **directory-level** (coarse), which is why it survives the cross-ecosystem
  coupling that breaks per-file selection: `tests/hooks/test_cursor_write_gate.py` reaches into
  claude-code's hooks, and drift tests live in `tests/build/` — all three are kept wholesale.
- **Explicitly rejected** (adversarially reviewed, higher risk / lower value here): diff-scoped
  mutation (all CI checkouts are shallow `fetch-depth: 1`, so a diff-base can't be computed; also
  misses regressions in unchanged dependents), pytest-xdist sharding (suite hermeticity unaudited;
  the `tiktoken-cl100k` shared cache is a named collision candidate), moving the full run to nightly
  (would break the `release.yml` gate — a release could ship before mutation ran on that commit),
  and shortening the per-mutant timeout (the gate excludes timeouts from its denominator, so this
  inflates the score while proving less). If the runner fix alone misses the target, the next lever
  is trimming `paths_to_mutate`, not new machinery.

## Test suite
- **Unit:** the mutate-scope guard test (every `paths_to_mutate` module maps to a covering test inside
  the runner dirs); a gate-hardening test simulating an interrupted/empty mutmut result and asserting
  a non-zero exit. Mocking: the gate-hardening test mocks the `mutmut result-ids` subprocess boundary
  to simulate a corrupted/empty cache; the counting logic itself is exercised directly.
- **Integration:** run `make test-mutation` once before and after the runner change; assert wall-clock
  ≤ 10 min and the kill rate is identical.
- **API:** n/a.
- **E2E:** the `mutation` CI job completes within the reduced timeout on a representative PR.

## Acceptance criteria
- Given the scoped runner, When `make test-mutation` runs in CI, Then wall-clock ≤ 10 minutes AND the
  kill rate equals the pre-change rate (same mutants, same threshold).
- Given a mutated module whose only covering tests live outside `tests/build|hooks|metrics`, When the
  guard test runs, Then it fails (scope cannot silently drift).
- Given a crashed or interrupted `mutmut run`, When the gate evaluates, Then it exits non-zero (no
  false green).

## Deletion note
Delete this file via `git rm` once its feature is delivered in code (a keep-specs code-of-conduct
refreshes it instead). Code is the source of truth after delivery.
