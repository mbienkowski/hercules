# Spec 10: docs-split
satisfies: [2026-07-10-universal-plugin-distribution-business-requirements.md §v1.1 R5]
complexity: medium

## Scope
Finish the half-done docs split so end-user and contributor instructions live in separate,
non-duplicated documents. `CONTRIBUTING.md` becomes a thin contributor entry point (orient + link,
never restate); README's contributor island moves out; cross-links are added; README becomes
end-user-only. Fix two nits found in passing.

## Affected code
- `README.md` — remove the `## Contributing` + `### For maintainers — testing a branch before
  release` island and the "Building from source" subsection; add a one-line pointer to
  `CONTRIBUTING.md`; correct the trust/audit pointer from "audit the source in `src/`" to the
  installed artifact `dist/<ecosystem>/`. Keep `## Plugin permissions` and `## Why sub-agents?`
  (end-user trust/rationale).
- `CONTRIBUTING.md` — thin entry: the src→dist model, `make build`/`make test`, local-plugin testing
  (incl. the marketplace-name gotcha), and links to `CODE_OF_CONDUCT.md` (deep rules) and
  `RELEASE.md` (release). Clarify that `hercules-dev` is a temporary *local* marketplace name to
  remove after testing.
- `CODE_OF_CONDUCT.md` — in the "when the change is visible at the four-phase level, also update…"
  instruction (≈ lines 63/80), name `CONTRIBUTING.md` alongside the README/diagram.

## Implementation
- Ownership after the split: `CODE_OF_CONDUCT.md` = deep reference (repo layout, adding
  commands/agents/skills/hooks, branching, invariants, testing regime); `CONTRIBUTING.md` = entry
  point (GitHub surfaces it in the PR/issue UI); `RELEASE.md` = release process + the Cursor manual
  checklist from Spec 08; `README.md` = end-user only.
- Resolve duplication by **moving/linking, not restating**: repo layout, `make build`/`make test`,
  and branch naming are owned by `CODE_OF_CONDUCT.md`; `CONTRIBUTING.md` links to them.
- README has no TOC/intra-page anchors, so reordering breaks no internal links; still verify external
  file links (LICENSE, workflow diagrams) remain valid.
- Simplicity guard: `CONTRIBUTING.md` must not become a third place that re-describes the workflow —
  keep it short and link-heavy so the three contributor docs cannot drift.

## Test suite
- **Unit:** `tests/docs/test_docs.py` stays green — update any assertion that pinned content now
  moved (e.g. auto-update wording). Mocking: none; these are file-content assertions.
- **Integration:** a link-check that README → CONTRIBUTING → CODE_OF_CONDUCT/RELEASE cross-links
  resolve and that README contains no contributor build/test instructions (only a pointer).
- **API:** n/a.
- **E2E:** render README + CONTRIBUTING and eyeball audience separation.

## Acceptance criteria
- Given README, Then it contains no contributor build/test instructions — only a pointer to
  `CONTRIBUTING.md` — and the audit pointer names `dist/<ecosystem>/`.
- Given `CONTRIBUTING.md`, Then it links (not restates) the deep rules and clarifies the temporary
  `hercules-dev` marketplace name.
- Given `CODE_OF_CONDUCT.md`'s "update the docs" instruction, Then it names `CONTRIBUTING.md`.
- Given all four docs, Then every cross-link resolves and no build/test guidance is duplicated across
  them.

## Deletion note
Delete this file via `git rm` once its feature is delivered in code (a keep-specs code-of-conduct
refreshes it instead). Code is the source of truth after delivery.
