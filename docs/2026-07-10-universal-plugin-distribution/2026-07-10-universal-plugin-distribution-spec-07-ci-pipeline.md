# Spec 07: ci-pipeline
satisfies: [2026-07-10-universal-plugin-distribution-business-requirements.md §v1.1 R3]
complexity: critical

## Scope
Restructure the pull-request/main CI pipeline so it is honest and correctly gated: retire the
standalone "Discover ecosystems" job by deriving the smoke matrix from the build registry (Spec 06);
make Smoke a peer of Test and Validate; and gate the ~40-minute Mutation job behind Test + Validate +
Smoke with **corrected success-semantics** (a latent bug makes today's `needs:` gating a no-op).
Preserve the fail-closed guard so the smoke gate can never silently vanish.

## Affected code
- `.github/workflows/ci.yml` — job graph: remove the `discover` job; `smoke.needs: [build]`;
  `mutation.needs: [test, validate, smoke]`; corrected `if:` on `smoke` and `mutation` (see below);
  print the derived matrix to the log.
- `scripts/ci/smoke_matrix.py` — rewrite to iterate `targets.registered_target_names()` (Spec 06's
  single source of truth) and read each target's `src/targets/<eco>/smoke.json`. Fail-closed **both**
  directions: a registered target with no `smoke.json`, and a `smoke.json` with no registered target.
- `tests/build/test_ci_smoke_matrix.py` — update to the registry-driven behavior and both fail-closed
  paths.

## Implementation
- The pre-existing bug: a custom `if:` on a job **replaces** GitHub's implicit `if: success()`, so a
  red `test` does not currently stop `mutation`/`smoke`. Fix with an explicit success-aware guard:
  `mutation.if: ${{ (github.event_name == 'pull_request' || github.ref == 'refs/heads/main') && !cancelled() && needs.test.result == 'success' && needs.validate.result == 'success' && needs.smoke.result == 'success' }}`.
  Apply the same `!cancelled() && needs.test.result == 'success'` pattern to `smoke` so a red unit
  suite blocks the real-CLI installs.
- Because `smoke` and `mutation` share the identical PR/main `if:` prefix, they skip together on
  non-PR pushes — so gating mutation on smoke does not deadlock on a legitimately-skipped smoke.
- Keep the fail-closed guard from the old discover job: if the registry-derived matrix is empty, the
  matrix step exits non-zero (red), never an empty matrix that GitHub counts as skipped==success.
- `smoke` stays `fail-fast: false` (one ecosystem leg's failure must not cancel the others).
- Cursor's smoke leg is defined in Spec 08 (it is not an npm CLI); this spec only wires the matrix
  and gating so Spec 08 can slot its leg in.

## Test suite
- **Unit:** `smoke_matrix.build_matrix()` — registry-driven output shape; raises on empty; raises on
  registered-but-no-smoke.json; raises on smoke.json-but-not-registered. Mocking: mock the filesystem
  listing only where needed to simulate the mismatch cases; never mock the registry itself (the point
  is that it *is* the source of truth).
- **Integration:** a workflow-graph assertion test (in the style of `test_version_process.py`)
  confirming `mutation.needs` includes `smoke` and the `if:` references all three job results.
- **API:** n/a.
- **E2E (manual, documented):** push a deliberately-red `test` on a scratch branch and confirm in the
  Actions UI that `smoke` and `mutation` are skipped, not started.

## Acceptance criteria
- Given a red `test` on a PR, When CI runs, Then `smoke` and `mutation` do not start.
- Given Test + Validate + Smoke all green on a PR or main, When CI runs, Then `mutation` runs.
- Given the registry lists N ecosystems each with a `smoke.json`, When CI runs, Then the smoke matrix
  has exactly N legs and the chosen list is printed to the log.
- Given an empty registry or a registered target missing its `smoke.json`, When the matrix step runs,
  Then it exits red (the gate cannot silently vanish).
- Given a non-PR branch push, When CI runs, Then `smoke` and `mutation` both skip (no deadlock, no
  wasted minutes).

## Deletion note
Delete this file via `git rm` once its feature is delivered in code (a keep-specs code-of-conduct
refreshes it instead). Code is the source of truth after delivery.
