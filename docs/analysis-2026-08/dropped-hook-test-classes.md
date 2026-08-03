# src/hooks/tests/ reduction — dropped test classes

> **How to read this record.** It is a historical account, kept verbatim as it was written, and it is
> cited by the header of the test file whose coverage it explains. The tree has been restructured
> since: the shipped Python moved to `src/scripts/hooks/` and its tests to `tests/scripts/hooks/`, so
> `src/hooks/tests/test_frozen_core.py` below now lives at `tests/scripts/hooks/test_frozen_core.py`.
> The reasoning is unchanged and nothing in the body has been edited — a record that gets corrected
> after the fact stops being evidence of what was actually decided.

Owner-approved amendment: comprehensibility over micro-protection. Unit-level coverage of
`src/hooks/` internals is intentionally dropped from `src/hooks/tests/`; protection for the
dropped behaviours is consciously delegated to the config-driven end-to-end suites
(`test_gate_surfaces.py`, `test_enforcement_gates.py`, `test_pre_tool_write_gate.py`,
`test_after_write_gate.py`, `test_generated_js_plugin.py`, `test_shipped_guard_runs_standalone.py`)
plus manual `make test-mutation` runs. No 1:1 test-to-test mapping is claimed or required — the
classes below are the behaviour *shapes* no longer proven at unit granularity in this tree.

## Whole files deleted

- **`test_hercules_gate_internals.py`** (~251 lines) — unit tests reaching into `hercules_gate.py`'s
  internal decision-shape construction and path-extraction-strategy functions directly (via
  `load_gate_module()`), rather than through its `main()` CLI surface. The CLI surface itself stays
  covered by `test_gate_surfaces.py` / `test_pre_tool_write_gate.py` / `test_after_write_gate.py` /
  the new `test_gate_shapes.py`.
- **`test_hercules_gate_mcp_and_dispatch.py`** (~234 lines) — unit tests of MCP tool-name
  dispatch/routing internals, same internals-not-CLI pattern as above.

Both files' only shared helpers (`load_gate_module`, `write_gate_state` in `conftest.py`) are now
unused; `conftest.py` is left untouched per instruction, so they remain as dead but harmless code.

## `test_frozen_guard.py` → folded into `test_frozen_core.py`

Dropped: two of four "every request shape is blocked" variants (frozen-notebook target, multi-edit
with no shared location — the remaining two, bundled multi-edit and full overwrite, keep the shape
class alive); the missing-spec-details and true-round-number block-message wording variants; the
"any one of several frozen files triggers a block" case; the decoy-`hercules_state`-shadowing
resolution-precedence case; the redundant `live_override_grant` allow-case (now proven by the
override-lifts tests instead of duplicated here).

## `test_frozen_acceptance.py` → folded into `test_frozen_core.py`

Dropped: 4 of 8 `frozen_drift` parametrize cases (no-baseline-recorded, only-the-drifted-file-reported,
multi-root-tamper-under-any-root, missing-baseline-hash-counts-as-drift — the remaining 4 keep the
match/tamper/override/delete classes alive); all 3 build.md-Step-5 "sanctioned correction" doctrine
regression tests (rebaselined-is-not-drift, unrebaselined-would-false-halt, stale-baseline-after-retire).

## `test_frozen_overrides.py` → folded into `test_frozen_core.py`

Dropped: multi-file-grant-unblocks-several-at-once; invalid-entries-mixed-into-a-valid-grant-list;
missing-round-never-matches-a-grant-with-no-round; single-file-name-instead-of-a-list; the
whitespace-only variant of the missing-reason class (blank and missing are kept); 3 of 6
`frozen_hook` opt-out values ("", `True`, `0` — "off"/"on"/"OFF"/unset are kept, covering the
exact-match and case-sensitivity classes).

## `test_frozen_resilience.py` → folded into `test_frozen_core.py`

Dropped: "importing the hook module doesn't itself run blocking logic" (an import-side-effect unit
check). All fail-open scenarios (no state, unmanaged directory, corrupted state, empty/unparseable
stdin, resolver exception, override-check exception, garbled real-stdin bytes) are kept.

## `test_frozen_resolver.py` (29 cases) → ~8 principal cases in `test_frozen_core.py`

**Dropped class: resolver corner cases.** Kept: nested-service attribution, cross-repository frozen
test, unrelated-project-listed-first search continuation, custom state-file location, active-build-
beats-design-in-same-folder, monorepo-plus-inner-service dual guard, relative-path resolution
against editor cwd, macOS-only case-insensitive path comparison.

Dropped: project-without-custom-state-file default; project-with-no-active-work does not hide a real
build; corrupted-data-for-one-project does not hide another; creating-a-new-file at a frozen path;
switching-feature does not unfreeze an earlier one; idle-inner-project does not hide an outer active
build; two-state-file-escape-path cases; two-features-both-frozen attribution; corrupted-session-data
skip-and-continue; two-projects-registered-at-the-same-folder; one-bad-entry-in-frozen-list; frozen
test protected under every reachable path; two-paused-builds-storage-order independence; and 6 direct
unit tests of `hercules_state.py` internals (`resolve_session`, `resolve_build_contexts`, `canon`)
called directly rather than through the hook's `main()` — the reference gate's public surface.

## `test_write_gate_shapes.py` + `test_gate_patch_and_shell.py` → `test_gate_shapes.py`

Kept: FLAT deny+allow, NESTED deny (the shape unique to this module), patch-body extraction
deny+allow (using the shipped `PATCH_AND_SHELL` codex config, multi-hunk, frozen-file-in-a-later-
hunk), shell-command extraction deny, fail-open on an unrecognized path / uncovered tool, and one
packaged-on-disk-gate subprocess proof (`Add` operation).

Dropped: the NESTED-shape allow case (redundant with FLAT's allow, which already proves the
allow path; NESTED's own value-add is only the deny-shape wrapping, kept); the PATCH-only (no Bash)
config variant of the patch-deny/patch-allow tests, superseded by the more thorough
`PATCH_AND_SHELL` version; the FLAT batched-multi-edit-list "frozen file named later in the batch"
case; the broken-configuration-never-blocks fail-open case (config-shape brokenness is a corner of
the same "fail open on breakage" class already unit-proven for the frozen-tests hook, and remains
exercised end-to-end by the real shipped configs in `test_gate_surfaces.py`); the `Delete`-operation
half of the packaged-hook parametrize (the `Add` half keeps the packaged-bytes class alive).

## `test_hook_hygiene.py` + `test_hooks_wiring.py` → `test_hook_hygiene.py`

No drops — all 5 hygiene scans and both wiring tests are carried forward whole; wiring is folded in
as this file is now "the one safety scan file with wiring folded in" per the amendment.
