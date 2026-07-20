# Spec 06: generic-build-seam
satisfies: [2026-07-10-universal-plugin-distribution-business-requirements.md §v1.1 R2]
complexity: critical

## Scope
Close the last hardcoded per-ecosystem seam in the build so that onboarding an ecosystem is a
*closed* operation: `scripts/build/cli.py` contains **zero** `if target == …` branches, there is a
single file-destination mechanism (not two), and the serializer registry is the one authoritative
list of ecosystems that also feeds CI (Spec 07). Strictly behavior-preserving — every byte of
`dist/claude-code/`, `dist/opencode/`, and `dist/cursor/` is unchanged.

## Affected code
- `scripts/build/cli.py` — remove the `if target == "claude-code" / elif "opencode" / elif "cursor"`
  extras tail, `_RENAMES`, `_CLAUDE_COPIES`, `_CURSOR_COPIES`, `_emit_opencode_extras`,
  `_emit_cursor_extras`, `_copy_map`/`_copy_shared_hooks`, `_write`; `build_target` becomes
  `spec = targets.get(target); dest_rel = spec.dest(rel); written += spec.emit_extras(ctx)`.
- `scripts/build/emit.py` — **new** leaf I/O module: `write()`, `copy_map()`, `copy_shared_hooks()`
  extracted verbatim from `cli.py` (no target knowledge).
- `scripts/build/targets/{__init__,base,claude_code,opencode,cursor}.py` — **new** package. `base.py`
  defines the `Target` descriptor (`name`, `serializer`, `dest(rel)`, `emit_extras(ctx)`) and an
  `ExtrasContext`. `__init__.py` aggregates registration and exposes `get()` /
  `registered_target_names()`. Each ecosystem module registers one `Target`; OpenCode's `plugin.js`/
  `opencode.json` codegen and Cursor's `dest`/hook wiring stay inside their own module.
- `scripts/build/serialize.py` — keep `cursor_dest` (imported by `targets/cursor.py`); registry role
  unchanged.
- `scripts/build/version_targets.py` — unchanged behavior; referenced by CI only.
- `pyproject.toml` `[tool.mutmut]` — add `scripts/build/targets/` (and `emit.py` if it carries real
  logic) to `paths_to_mutate` so relocating logic does not silently drop mutation coverage.

## Implementation
- Follow the lead-architect's Stage 1 + dest unification. `_RENAMES` (claude persona→CLAUDE.md,
  opencode persona→instructions.md) and `cursor_dest` (persona→rules/hercules-persona.mdc) are all
  static 1:1 maps → collapse into one `dest(rel)` on the `Target`, defaulting to identity.
- **Do not** abstract genuinely bespoke logic into a shared framework: OpenCode's generated
  `plugin.js`/`opencode.json` and each ecosystem's write-gate adapter stay per-target (rule of three
  not met; two occurrences is not a pattern). No "hook DSL".
- Keep `tests/hooks/test_enforcement_gates.py`'s manual `GATE_EXPECTATIONS` checklist exactly as is —
  it is the security forcing-function that makes "did we wire the write-gate" a conscious decision;
  do not fold it into the registry.
- Constraint from `CODE_OF_CONDUCT.md`: `dist/` is generated, never hand-edited; `src/content/`
  authored once; the frozen-guard hooks are authored once under claude-code and byte-copied.
- Migration is staged and each stage is gated by `--check` (zero byte-diff) before proceeding:
  (1) extract `emit.py` (pure move); (2) introduce `targets/` wrapping existing functions 1:1 behind
  `Target` objects — this alone removes every per-ecosystem branch from `cli.py`.

## Test suite
- **Unit:** `serialize` registry conformance (`test_serialize.py`), `dest(rel)` per target, each
  `Target.emit_extras` produces the same file set as the retired branch. Mocking: **mock nothing** in
  the build round-trip — it is pure filesystem in/out; mocking would hide the exact defect this spec
  risks (a wrong path). Only external process boundaries (none here) would ever be mocked.
- **Integration:** `python -m scripts.build.cli --target all --check` byte-diff gate;
  `test_dist_drift.py`, per-target determinism (`build twice → identical`), `test_cutover.py`,
  `test_roster_sync.py`.
- **API:** n/a.
- **E2E:** full `make test` green with new modules inside the mutmut include set.

## Acceptance criteria
- Given the refactor, When `python -m scripts.build.cli --target all --check` runs, Then it exits 0
  with zero byte-diff against committed `dist/**` (all three ecosystems).
- Given a grep of `scripts/build/cli.py`, When searching for `target ==` or an ecosystem name, Then
  there are no matches (zero per-ecosystem branches).
- Given a hypothetical 4th ecosystem, When it adds `src/targets/<eco>/` + registers one `Target`,
  Then no edit to `cli.py` or `emit.py` is required to build it.
- Given the new `targets/` modules, When mutation runs, Then they are within `paths_to_mutate`
  (coverage not silently dropped).

## Deletion note
Delete this file via `git rm` once its feature is delivered in code (a keep-specs code-of-conduct
refreshes it instead). Code is the source of truth after delivery.
