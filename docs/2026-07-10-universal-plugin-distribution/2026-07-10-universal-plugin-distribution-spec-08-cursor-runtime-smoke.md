# Spec 08: cursor-runtime-smoke
satisfies: [2026-07-10-universal-plugin-distribution-business-requirements.md §v1.1 R1]
complexity: critical

## Scope
Make the Cursor distribution actually work as a plugin — not just structurally valid. Fix the
write-gate so it fires inside Cursor, correct the minimum-version claim, add a two-tier smoke check
(always-on structural + main-only live `cursor-agent`), and document — with a mandatory manual
release checklist — exactly what CI can and cannot prove about Cursor.

## Affected code
- `src/targets/cursor/hooks/hooks.json` + `src/targets/cursor/hooks/hercules_gate.py` — replace the
  unverified `${CURSOR_PLUGIN_ROOT}` reference with the plugin-root mechanism **verified on a real
  Cursor install**; if Cursor injects no such variable for plugin-bundled hooks, resolve the gate
  script path robustly (e.g. the hook resolves its own directory) so the command cannot silently fail.
- `src/targets/cursor/CAPABILITIES.md` — minimum version 2.4 → **2.5** (plugin packaging is a 2.5
  feature); document the accepted external risks: Cursor's plugin-in-CLI loading is experimental
  (feature-flagged, may regress) and `readonly` subagents depend on a Cursor server-side behavior
  Hercules cannot pin.
- `src/targets/cursor/smoke.json` — the leg config consumed by Spec 07's matrix; mark it as the
  non-npm (script-installer) ecosystem.
- `scripts/ci/*` — a structural validator (no key, every run) and the keyed live-check invocation.
- `tests/build/test_cursor_smoke.py`, `tests/hooks/test_cursor_write_gate.py` — structural + gate
  tests, incl. a test asserting the hook command carries the *verified* plugin-root token (guards
  against regressing to a non-existent variable).
- `RELEASE.md` — a Cursor manual smoke checklist (GUI-only surfaces).

## Implementation
- Web-verified facts driving this spec: `cursor-agent -p --force` is a real headless mode requiring
  `CURSOR_API_KEY`; `beforeShellExecution`/`afterFileEdit` fire in the CLI; plugin *loading* in the
  CLI is experimental; `${CURSOR_PLUGIN_ROOT}` is not in Cursor's documented hook env vars; plugin
  packaging requires Cursor ≥ 2.5.
- **Two-tier smoke:**
  1. **Structural (always-on, no key):** `.cursor-plugin/plugin.json` is valid JSON with the required
     fields; `hooks/hooks.json` valid; `rules/hercules-persona.mdc` has `alwaysApply: true` as a
     boolean; agent frontmatter present; the hook command's plugin-root token matches the verified
     mechanism. This is the reliable CI signal.
  2. **Live (main-only, `CURSOR_API_KEY` secret, `fail-fast: false`):** install `cursor-agent`,
     register the built `dist/cursor` plugin locally, run a `cursor-agent -p --force` prompt that
     attempts a write to a protected/frozen path, and assert the `beforeShellExecution` gate blocks
     it. Annotate clearly on failure that the live leg depends on Cursor's experimental plugin
     loading (known-fragile), so a red leg is triaged, not blindly trusted.
- **Manual (RELEASE.md, not claimed by CI):** on a real Cursor ≥ 2.5 install, confirm `/discover`
  appears as a command, the persona `.mdc` rule applies, subagents load, and the write-gate blocks a
  frozen-path edit from the IDE. This is the real gate for the GUI-only surfaces.
- Honesty rule (from R1 and `CODE_OF_CONDUCT` disclosure constraint): a capability CI cannot prove is
  documented as manual-verified, never asserted as automatically covered.

## Test suite
- **Unit:** structural validator (each assertion above); write-gate block/allow reusing the canonical
  `frozen_tests._override_allows`; the plugin-root-token guard test. Mocking: the write-gate unit
  tests exercise the real `hercules_gate.py` against a temp `$HOME`/repo (never the real one, per the
  existing hook-test conftest); do **not** mock `frozen_tests`/`hercules_state` — they are the
  single-source-of-truth logic under test.
- **Integration:** `--check` includes `dist/cursor` (byte-stable); enforcement-gate test confirms
  Cursor ships a declared write-gate.
- **API:** the Cursor live leg is the contract test against the real `cursor-agent` CLI (main-only).
- **E2E:** the RELEASE.md manual checklist run on a real install before release.

## Acceptance criteria
- Given a Cursor install, When a hook runs, Then `hercules_gate.py` is located and a frozen-path write
  is blocked (verified by the manual checklist pre-merge and reproduced headlessly by the keyed live
  leg when the key is present).
- Given any CI run, When the structural leg runs, Then the manifest/hook/rule shape is validated and a
  regressed plugin-root token fails the build.
- Given `CAPABILITIES.md`, Then it states Cursor ≥ 2.5 and discloses the plugin-loading + readonly
  external risks.
- Given the release process, Then `RELEASE.md` contains a Cursor manual smoke checklist covering the
  GUI-only surfaces CI does not prove.

## Deletion note
Delete this file via `git rm` once its feature is delivered in code (a keep-specs code-of-conduct
refreshes it instead). Code is the source of truth after delivery.
