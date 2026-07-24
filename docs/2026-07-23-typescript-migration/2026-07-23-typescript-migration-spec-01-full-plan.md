# Spec 01: migrate Hercules' build & test tooling from Python to TypeScript

**Satisfies:** `2026-07-23-typescript-migration-business-requirements.md` (all sections).

**Branch:** `feat-typescript-build-tooling` (no slashes — CoC § Branching)
**Shape:** one long-lived branch, 17 commits, single merge. Every commit leaves the repo green.
**Review:** every commit gets a fresh-eyes advisor panel (parallel specialists, then independent
adversarial verification) before it lands — no self-certification.

---

## Context

Hercules authors ecosystem-neutral markdown in `src/content/` plus one JSON descriptor per
ecosystem in `src/ecosystems/<eco>.json`, and a generic Python compiler in `scripts/build/`
emits per-ecosystem plugin trees into `dist/` for six targets. `dist/` is committed and gated
for drift and determinism.

Outcome: the compiler, CI scripts, and test estate become TypeScript on Node 22; the shipped
enforcement hooks stay Python 3; the migration is **invisible to users of all six ecosystems**.

### Ground truth (`main` @ `3f898e5`, when this spec was written)

| Layer | Files | Lines | Fate |
|---|---|---|---|
| `scripts/build/` compiler | 11 `.py` | 1,183 | → TypeScript |
| `scripts/ci/*.py` + `scripts/*.py` | 5 `.py` | 275 | → TypeScript |
| `scripts/ci/*.sh` | 7 `.sh` | — | stay bash, delegate to `make` |
| `src/hooks/` (byte-copied, run as `python3`) | 3 `.py` | 741 | **stay Python** |
| `tests/` | 90 `.py` | 11,568 | → Vitest, except the hook island (~2,600) |

---

## Locked decisions

1. **Hooks stay Python 3, stdlib-only, shipped byte-identical.**
2. **A Python island survives: `pytest` + `mutmut`, scoped to `src/hooks/` only** — split into
   parallel `mutation-py` / `mutation-ts` CI jobs, a wall-clock win over one serial ~40–50 min job.
3. **One long-lived branch, 17 commits, single merge.** Per tool: add the TS tool *alongside*
   Python, prove identical output, delete the Python one in a later commit.
4. **Parity proven by fault injection.** Inject a known defect; **both** suites must go red for
   the same reason. A ported test that stays green under injection is decorative and rejected.
5. **`descriptor.py` ports as-is first (byte-identical errors), Zod lands in the very next
   commit.** Two commits, never one.
6. **Instruction splitter is V2** — over-count, ignoring fragments under two words.
7. **Ceiling is absolute: 150 hard, 130 warn.** No `÷3` scaling.
8. **The instruction counter ports as a commit pair** — 1:1 port, then atomic upgrade.
9. **The orchestrator instruction-budget breach is surfaced via a named, expiring waiver.**
10. **`package.json` becomes the canonical version source** (against the advisor panel's
    recommendation to keep `pyproject.toml` canonical — the maintainer's explicit call). Isolated
    into its own commit (14) with a release-path dry-run gate.
11. **Layout: parallel trees.** `scripts-ts/` + `tests-ts/`; the island ends as
    `tests-python/hooks/`. `.mts` never sits beside the `.py` it replaces.
12. **Commits 9 and 10 stay whole.** Each Python test dies in the same commit its TS
    replacement lands.
13. **If the token-parity spike (commit 2) shows any delta, the branch stops** for a re-baseline
    decision. No shim, no silent re-baseline.

### Defaults taken without escalating

Zod **v4** · `GATE=90`/`WARN=95` sourced from **one shared JSON file** both gate scripts read ·
the six per-CLI smoke specs **port as-is** to Vitest · Cucumber/Gherkin is **out of scope**.

### Out of scope

Rewriting hooks in TS · shipping Node to users · any change to `src/content/`,
`src/ecosystems/` formats or `dist/` bytes · Cucumber/Gherkin E2E · any user-visible change.

---

## ⚠ Correction to this spec, learned executing commit 2 (read before writing any `.ts` file)

**The toolchain is `.mts` → `.mjs` (ESM), not CommonJS, and file extensions throughout this spec
should read `.mts` wherever an earlier draft said `.ts`.**

Commit 1 originally chose CommonJS emit reasoning that `package.json`'s `main` is
`dist/opencode/plugin.js` — the compiled, shipped OpenCode plugin, itself CommonJS
(`require`/`__dirname`/`module.exports`) — so `package.json` must never gain a `"type"` field.
That constraint is still true and still enforced (see below). But CommonJS-emitting `scripts-ts/`
broke in commit 2: `js-tiktoken` publishes **one shared `types` condition** for both its CJS and
ESM entry points, so a CommonJS consumer gets `TS1479` and cannot type-check against it at all,
even though `require()` works fine at runtime.

The fix that survived review: **`scripts-ts/` sources are `.mts`, which Node always loads as ESM
regardless of any `"type"` field**, however `.mjs` files are named or referenced. That gives the
toolchain modern ESM (needed for `js-tiktoken` and any future ESM-only dependency) while
`package.json` keeps no `"type"` field and `dist/opencode/plugin.js` stays exactly the CommonJS
file it always was. `tests-ts/packaging.spec.ts` pins the absent `"type"` field with a paired
positive assertion that the shipped plugin still contains `require(` and `__dirname`, and a
second guard (`the module format of the toolchain` describe block) asserts every source under
`scripts-ts/` is `.mts` and that no config describes it as CommonJS — both fault-injected to
confirm they fail.

Two tsconfig projects, not one:
- `tsconfig.build.json` — `scripts-ts/**/*.mts` → ESM, emitted to gitignored `.ts-out/` as `.mjs`.
- `tsconfig.tests.json` — `tests-ts/**/*.ts` + `*.config.mts` → ESM, type-checked only (Vitest
  compiles tests from source; nothing here is ever emitted).

`tsconfig.base.json` holds the shared strict compiler options; the root `tsconfig.json` is a
zero-file project that references both. Every `import` between `scripts-ts/*.mts` files carries
an **explicit `.mjs` specifier** (`from './pyCompat.mjs'`), matching what Node's ESM resolver
requires — this is not optional and every new file must follow it.

TypeScript is pinned to **6.0.3**, not `latest`. TypeScript 7 is a Go rewrite that drops API
surface Stryker 9.6.1 depends on (`ts.parseConfigFileTextToJson is not a function`); 6.0.3 is the
last JS-based compiler. It also caught three real type errors 7 had silently accepted — a
second, independent reason to stay on it.

---

## Commit sequence

Each row states what proves it and why the repo is green at that commit. Status reflects this
spec's authoring moment; update the ✅/🔶/⬜ marker as work lands — this file is the durable
record, not a point-in-time snapshot.

**Process note (from commit 6 onward):** per-commit review was scaled back to `tsc` + `vitest` +
`make parity` only — no per-commit `make mutation-ts` run and no per-commit multi-agent review
panel. Both are deferred to ONE pass over the whole branch after commit 17 lands, per explicit
maintainer direction mid-migration (the earlier commits already paid that cost individually and
it bought real findings, but scaled per-commit across 17 commits is disproportionate). Any row
below commit 6 that doesn't cite a mutation score or a review round is not a gap — it is this
policy, not an oversight.

| # | Status | Commit | What lands | Proven by |
|---|---|---|---|---|
| 1 | ✅ `631a0c1` | `chore(build): scaffold the typescript toolchain and supply-chain guards` | `package.json` devDeps exact-pinned + committed lockfile, `.npmrc` `ignore-scripts=true`, `engines: node>=22`, ESM `.mts`→`.mjs` toolchain (see correction above), `vitest.config.mts` (90% branch), `stryker.conf.json`, TS mutation-gate mirroring `check_mutation_gate.py`'s GATE=90/WARN=95 sourced from a shared `scripts/mutation-gate.json`, dependabot npm entry, `make test-ts/mutation-ts/test-py/mutation-py`, `setup-node@v7` | `npm ls --prod` = zero runtime deps; `npm pack --dry-run` ships only `dist/opencode`; `make test`/`make ci-build` behaviourally unchanged |
| 2 | ✅ `b12c2c5` | `test(metrics): pin cl100k_base token parity between python and node` | **Go/no-go spike — passed, no re-baseline needed.** `js-tiktoken@1.0.21` exact-pinned, imported as `js-tiktoken/lite` + `js-tiktoken/ranks/cl100k_base`. `make parity-tokens` counts every file in `thresholds.json` with both tokenizers | 44/44 corpus entries identical (real files + 15 adversarial strings: ZWJ emoji, CJK, whitespace runs, `<\|endoftext\|>` — both engines throw identically on the control-token case, and that refusal is compared too); self-check (delete a byte → both counts move identically) |
| 3 | ✅ `039a331` | `feat(build): add the dual-run parity harness and port the six leaf modules` | `scripts/ci/parity.sh` (`make parity`) + `parse/render/modelMap/layout/emit/versionTargets.mts` + `pyCompat.mts` (Python string-primitive fidelity: `pySplitlines`/`pyStrip`/`pyRepr`/`pyReprMapping`, tables generated from and verified against CPython, with a `make pycompat-golden-check` CI gate proving the golden matches the Unicode version the running interpreter ships) | 66 fixtures byte-diffed; 7 deliberately injected defects across the six modules, all caught (first pass caught only 2/7, exposing 3 real fixture gaps since closed — see Lesson below) |
| 4 | ✅ done | `feat(build): port descriptor validation to typescript as-is` | `descriptor.mts` — same closed vocabulary, same control flow, same validation *order* (guard→roles→routes→artifacts→gate→templates), `pyRepr`/`pyReprValue` for byte-identical `DescriptorError` strings. No Zod. Two documented non-ported Python quirks: bool-is-int (`schema: true` doesn't ambiguously pass) and set-membership-crashes-on-unhashable (TS `Set.has()` never crashes; fixtures redirected to a tuple-backed check to avoid asserting a crash as correct). Five further documented divergences (see the top-of-file comment): `load()`'s `*.json` glob crashing on a directory in Python but not TS (NOTE narrower than an earlier draft claimed — `validateLayout`/`distFiles` already carry an equivalent `is_file()` guard on the Python side too, so that half is faithful parity, not a divergence); `load()` crashing on a bare `NaN`/`Infinity` JSON token where Python doesn't; `Object.entries()` reordering integer-like string keys ahead of others in `vars`/`gate.tools`, affecting which of MULTIPLE simultaneous bad entries is reported first; and an integer-valued JSON float (`5.0`) being indistinguishable from an int once parsed. All four TS-only unit-tested (pinned, not parity-fixture-able) rather than fixed — see lesson 12 for why | 164 fixtures byte-diffed (incl. all 6 real shipped descriptors through `discover()`); 389 tests across 5 files (split from one, none over 474 lines — CoC's 500-line/20-line test caps); ≥95% branch coverage; `descriptor.mts` mutation score 98.49% (911 killed / 14 non-killed, all 14 independently re-verified equivalent by an adversarial review pass — see lessons 11–12), repo-wide `make mutation-ts` 97.15%, both clear of the 90% gate and the 95% warn threshold. A full fresh-eyes review round (4 parallel dimensions + independent adversarial verification of every finding) ran AFTER the mutation-closing round and found 11 further confirmed issues — 3 real correctness divergences, 2 mis-scoped tests, 2 wrongly-classified "equivalent" mutants that were actually real gaps, 2 doc-accuracy gaps in lesson 11, and 2 test-hygiene issues — all fixed; see lesson 12 |
| 5 | ✅ done | `feat(build): validate descriptors with zod and a custom error map` | Zod v4 `discriminatedUnion` on the five discriminators, two cross-field `.check()` rules (wrap-mode literal-only, `toml_command` exactly `['description']`), nullable partial record for model tiers, custom error map. Signatures unchanged | Commit-4 fixtures re-run through a redesigned harness (byte-identical obligation ends here — descriptor fixtures now compare accept/reject only, via a shared placeholder string on both sides; every other module unchanged); 410 TS tests across 18 files (177 in the 7 descriptor spec files); 165 parity fixtures, all green (98 of them descriptor-module); `descriptor.mts` mutation score 95.88% (repo-wide 95.81%), both cross-field rules pinned by named tests; a post-mutation fresh-eyes review round (lesson 19) found and fixed 6 further issues, none reachable by the mechanical gates alone |
| 6 | ✅ done | `feat(build): port genserialize to typescript` | `genSerialize.mts`; `descriptor.mts`'s `FieldSpec.source` narrowed to a `FieldSource` literal union so `computeFields` dispatches through an exhaustive switch ending `satisfies never`; 30 new TS unit tests ported 1:1 from `test_generic_serialize.py`, all passing against the real shipped descriptors | Parity leg added (`genserialize.serialize_file_for_fixture`, a small fixture-composition helper on both sides, since the harness calls one module-level function per fixture); 10 new fixtures across every mode; fault-injection verified live (a corrupted output key turned the matching fixture red, then reverted) |
| 7 | ✅ done | `feat(build): port genextras to typescript` | `genExtras.mts`; JSON via plain `JSON.stringify(x, null, 2) + "\n"`; `${version}` exactly-one-token guard (`GenExtrasError`); 16 new TS unit tests | All 6 ecosystems' extras (artifacts/siblings/guard/gate/templates) rendered by both engines via a `emit_extras_for_fixture` composition helper (same pattern as commit 6's `serialize_file_for_fixture`) against the REAL `src/hooks`/`src/content`, sha256+mode-diffed; fault-injection verified live. The adversarial numeric-string-key case for `jsObjectLiteral`'s plain-object branch genuinely diverges (V8 reorders, Python preserves insertion order) — NOT a parity fixture (byte-identical is impossible for that input), documented in the module's own top comment and pinned by a dedicated TS unit test instead; latent in practice since the one real caller always passes an (unaffected) Map |
| 8 | ✅ done | `feat(build): port serialize and cli, and gate the full dual-build parity` | `serialize.mts` as an explicit `buildRegistry()` factory (per-caller instance, not a module singleton); `cli.mts` (`scripts-ts/bin/`) with lazy `targets()`/`buildTarget()`/`checkTarget()`/`main()` — both closing the import-time filesystem scans `serialize.py`/`cli.py` ran as a side effect of a bare `import`. `checkTarget` gains an optional `distRoot` param over the Python original (test-only; defaults to the real `dist/`), so its divergence path is directly testable rather than only trusted. `make build`/`make ci-build` are NOT flipped yet (commit 15) | Zero-fs-syscalls-at-import proven live via a `vi.mock('node:fs')` spy on every function, fault-injection-verified (a stray top-level `readdirSync` call fails the test). `scripts/ci/parity.sh` gained Leg 2 (full-tree parity): both `build_target`/`buildTarget` called directly (not through either CLI's argv layer) for all 6 real targets into isolated temp trees, `diff -r` content plus a `stat`-mode walk, fault-injection-verified live. `checkTarget` against the REAL committed `dist/` (built by Python) reports 0 for all 6 targets — the TS pipeline reproduces Python's own build byte-for-byte, content and mode, end to end |
| 9 | ✅ done (scope reconciled — see below) | `test(build): port the compiler test suite to vitest` | Most of the plan's original "40 files → tests-ts/build/*.spec.ts" was already written incrementally alongside commits 4–8 (descriptor: 177 tests over 7 files; genSerialize: 30; genExtras: 16; serialize: 6; cli: 17), not deferred to one commit as originally planned. Commit 9 itself adds 8 new `tests-ts/bin/*.spec.ts` files (101 tests) porting the remaining CLI-dependent Python suites: `distDrift`, `modelTiering`, `opencodeMirror`, `cursorBuild`, `conformance`, `universalConformance` (the two large hand-authored per-ecosystem tables — 84 tests alone), plus the **synthetic 7th ecosystem** positive-path test the plan named directly (verification step 7's keystone: a new ecosystem needs zero `.mts` changes) | 577 TS tests total, all green; fault-injection verified live on `universalConformance` (a corrupted field-generator output key crashes `buildTarget` immediately) and on the synthetic-ecosystem test's own composition. `make mutation-ts` deferred to the final commit per the maintainer's mid-migration process note (see above) — NOT run per-commit from here on |
**Commit 9 scope note — `tests/build/*.py` files NOT yet ported, by reason:**
- Belong to a LATER commit, not skipped: `test_workflows_use_make.py`, `test_validate_package.py`,
  `test_ci_smoke_matrix.py` (commit 13, CI/release scripts); `test_version_process.py`'s
  release-script slice (commit 13); the six per-CLI `test_*_smoke.py` files (deferred — "port
  as-is" per the plan's own defaults, but genuinely lower priority since they exercise a REAL
  installed CLI binary, none of which are present in this environment to prove parity against).
- Already redundant, confirmed by direct comparison: `test_model_map.py` (commit 3's
  `modelMap.spec.ts` already covers `resolve`/`ModelMapError` identically).
- Genuinely not yet ported, real remaining commit-9-shaped work: `test_frontmatter_roundtrip.py`,
  `test_render.py` (additional parse/render regression cases beyond commit 3's base specs),
  `test_edge_cases.py`, `test_mutation_hardening.py`, `test_cutover.py`, `test_target_switches.py`,
  `test_roster_sync.py`, `test_opencode_entrypoint.py`, `test_cli_generation.py`,
  `test_cursor_serialize.py`, `test_gemini_cli_build.py`. None of these were skipped for being
  low-value — they were triaged out of THIS turn's scope for time, not for redundancy. Left as an
  explicit follow-up rather than silently dropped: the highest-value, highest-risk-of-becoming-
  decorative files (the two conformance suites, at 84 tests) are already done, matching lesson
  12's rule to be honest about what a "done" commit actually covers.

| 10 | ✅ done (scope reconciled) | `test: port the remaining non-hook test suites to vitest` | `scripts-ts/metrics/{a2aGrammar,markdownMetrics,thresholdRunner}.mts` (new production modules, alongside commit 1's `tokenCounter.mts`); `tests/{metrics,commands,workflow,protocols,plugin,skills,agents,docs}/` fully ported to `tests-ts/{metrics,commands,skillsAndAgents,docsAndPlugin,workflowAndProtocols}/` via 4 parallel background agents plus this commit's own metrics work, each independently verified against `pytest --collect-only` counts (104+88+37+60+66 = 355 new tests, exact 1:1 or better). All 8 fully-ported Python directories deleted (47 files) — and so were commits 4–9's now-superseded `tests/build/*.py` originals (12 files: `test_descriptor_schema`, `test_generic_serialize`, `test_manifests`, `test_serialize`, `test_model_map`, `test_target_registry`, `test_opencode_commands`, `test_opencode_mirror`, `test_dist_drift`, `test_model_tiering`, `test_conformance`, `test_universal_conformance`), retroactively satisfying locked decision 12 ("each Python test dies in the same commit its TS replacement lands") for the whole compiler port, not just this commit — a real gap found and closed during this commit's own pre-deletion audit. `tests/budgets/` (commit 11 — its instruction-counting logic is what commit 11 rewrites), `tests/release/` (commit 13 — tests a not-yet-ported script), `test_workflows_use_make`/`test_validate_package`/`test_ci_smoke_matrix` (commit 13), the six per-CLI smoke specs (deferred, no installed CLIs here to prove parity against), and ~11 smaller `tests/build/*.py` files (frontmatter roundtrip, render edge cases, mutation hardening, etc.) are explicitly NOT ported — recorded as a follow-up, not silently dropped | 934 TS tests total, all green; `make parity` (181 fixtures + full-tree leg) unaffected; remaining Python suite (420 tests) unaffected by the deletions. Pre-deletion audit caught and fixed 3 real issues: a vacuous test (`join(out, 'command')` singular vs the real `commands` directory — the `existsSync` guard was always false, so the test ran zero assertions), two Python tests silently un-ported from `test_opencode_commands.py` (now added), and one legitimate compile-time-only divergence (`ExtrasContext`'s Python `frozen=True` dataclass has no TS runtime equivalent — documented and pinned via `@ts-expect-error` instead of a runtime throw-assertion) |
| 11 | ✅ done | `feat(budgets): count atomic directives across loading chains` | **The metric upgrade — a real feature, not a port.** `instructionCounter.mts`'s `countAtomicInstructions`: same unit-detection as the old `_count_instruction_blocks` (bullets/numbers/bold-labels/fenced-numbered-rules), then splits each unit on `,`/`;`/`&`/`and`/`or`/`then` and counts every ≥2-word fragment — no vocabulary filter (one was tried, measured LOW against real content, dropped; see lesson 22). Absolute 150/130 ceiling (`÷3` deleted) applied UNIFORMLY, not per-chain-type. `loadingChains.mts`: chain definitions as data (`ChainTemplate[]`, a fixed-parts list + one optional glob that fans a template into one chain per matching file — agents/commands/skills), plus a `WAIVERS` list recording the one over-gate chain by name and exact measured value, checked both ways (a growing chain fails, a since-fixed chain's stale waiver fails too). `markdownMetrics.countInstructions` and `_count_instruction_blocks` (Python, deleted) collapse into this one counter; `thresholdRunner.mts`'s `instruction_count` metric now resolves to it | Hand-labelled golden corpus (`instructionCounter.spec.ts`) plus a reference-measurement pin against real shipped content; the measured table below reproduced EXACTLY (all six numbers, not approximately) by the real algorithm against real files, not asserted; every non-`build.md` chain — all 16 sub-agents, both smaller commands, all 4 skills — measures under the 150 gate; fault-injection-verified live (a waiver value edited to sit below the real measurement correctly fails the gate) |
| 12 | ✅ done (scope reconciled) | `test(hooks): decouple the python island and re-home its wiring tests` | Six island tests (`test_cursor_write_gate`, `test_enforcement_gates`, `test_hooks_wiring`, `test_opencode_write_gate`, `test_grok_build_write_gate`, `test_pre_tool_write_gate`) re-pointed at the committed `dist/<eco>/hooks/` tree instead of importing `scripts.build` — `build_target(...)` calls replaced with direct reads, `discover()[eco].gate` replaced with reading the shipped `hooks/gate.json` verbatim (exact, since `universalConformance.spec.ts`'s own "shipped gate config is the descriptor gate verbatim" test is what makes that substitution provably lossless). `tests/hooks/` → `tests-python/hooks/`, a tree fully OUTSIDE `tests/` so it survives commit 16's Python-compiler deletion untouched. **Deviation from the original text:** `test_enforcement_gates`/`test_hooks_wiring` stay Python (re-pointed, not ported to TS) rather than moving to `tests-ts/build/` — porting their per-ecosystem wiring-detail tables (`GATE_EXPECTATIONS`, six protocol shapes) would have been substantial new TS work whose main benefit is organizational, not functional: the actual decoupling goal (no import of the compiler) is already fully met by reading committed `dist/`, and several of their checks (guard byte-identity, gate-config verbatim-ness) already overlap with `universalConformance.spec.ts`'s existing coverage from commit 9/10. CoC/CONTRIBUTING path references updated in the same diff, plus `pyproject.toml`'s `testpaths`/`pythonpath`/`[tool.mutmut]` (`runner`, `tests_dir`, and a stale `tests/metrics/` entry in `paths_to_mutate` left over from commit 10) and the Makefile's `test-py` target — all of which would have SILENTLY broken `tests-python/`'s discoverability without being caught by any existing gate | `grep -rl 'scripts\.build' tests-python/` empty (verified); all 223 hooks-island tests pass reading committed `dist/`; full suite (`tests/` + `tests-python/`) 416 Python tests green under both explicit paths AND bare `pytest` (proving the `testpaths` fix); `make parity` and the TS suite unaffected (977 tests) |
| 13 | ✅ done | `chore(ci): port the ci and release scripts and isolate npm from the release job` | `build_gates.sh`'s four hardcoded compiler calls → `make build`/`make build-check`; `scripts-ts/ci/{smokeMatrix,validatePackage}.mts` + top-level `scripts-ts/{setVersion,updateChangelog}.mts` port the four remaining `.py` CI/release scripts (Python originals + their `tests/` deleted in this commit: `scripts/ci/{smoke_matrix,validate_package}.py`, `scripts/{set_version,update_changelog}.py`, `tests/build/{test_ci_smoke_matrix,test_validate_package,test_version_process,test_workflows_use_make}.py`, `tests/release/`). `release.yml` split into an unprivileged `prepare` job (`contents: read`, runs `npm ci`/`tsc`, uploads compiled `.ts-out/` as a build artifact) and the privileged `release` job (`contents: write`, downloads the artifact, never runs `npm ci` itself) — workflow-level `permissions` dropped to `contents: read` to match, `release` raises it back at job level. `ci.yml`'s `build`/`validate` jobs gained `setup-node`+`make install-ts`+`make compile` since `smokeMatrix.mts` now transitively imports the Zod-validated descriptor module. Two source-side testability seams added, matching the project's established `distRoot`-param pattern rather than Python-style monkeypatching (ESM bindings aren't reassignable): `cli.mts main()` gained an optional `distRoot` param (closing a real gap — the "stale build reports `make build`" case had no test at all before this commit), and `smokeMatrix.mts buildMatrix()`/`validatePackage.mts` gained an injectable `registered` param / split-out `validateManifests()`. New `tests-ts/releasePipeline.spec.ts` carries the workflow-YAML-structural assertions (make-only `run:` steps, CI job-graph invariants, the release pipeline's ordering/CI-validated-commit/no-`npm-ci`-in-privileged-job checks) | `make ci-build`, `make parity` (181/181 + full-tree leg), `make validate`/`make smoke-matrix` all green and cross-checked against the (still-live, pre-deletion) Python originals' output; `tsc -b` clean; `vitest run` 1006 passed/1 skipped (was 977/1 — +29 net after also porting the pre-existing gap); Python suite 372 passed/16 skipped (was 416/16 — exact 44-test count-match against the 4 deleted files' combined `--collect-only` count, confirming no coverage silently dropped) |
| 14 | ✅ done | `feat!: make package.json the canonical version source` | **Isolated by design, flagged to the user before starting per the plan's own risk table.** `readCanonicalVersion`/`read_canonical_version` flipped in BOTH engines (`versionTargets.mts` and its still-live Python mirror `version_targets.py`, kept in lockstep since the compiler stays dual-engine until commit 16) to read `package.json`; `pyproject.toml` becomes the cross-checked mirror. `genextras.py`'s matching inline comment, the `version-read-canonical` parity fixture (strengthened to use DIFFERENT values per file, so a wrong-engine bug would actually be caught instead of passing vacuously), and every "canonical = pyproject.toml" prose reference in `CODE_OF_CONDUCT.md`/`CONTRIBUTING.md`/`RELEASE.md`/`release.yml`/`test_gemini_cli_build.py` updated in the same diff. Caught and fixed 3 tests in `versionTargets.spec.ts` that the flip would have silently made vacuous (they exercised `pyproject.toml`-format-parsing edge cases but read the result via `readCanonicalVersion`, which now resolves to `package.json` instead — same value in the fixture either way, so they'd have kept passing while testing nothing) | `tsc -b` clean; `vitest run` 1006/1 unchanged; Python suite 372/16 unchanged; `make parity` 181/181 + full-tree leg, now with a fixture that can actually distinguish the two engines; `make ci-build` green, `dist/` untouched (package.json and pyproject.toml already agreed in the real repo, so the flip is a no-op today). **Full `release.yml` dry-run**, run in an isolated `git worktree` on a throwaway branch (never touching the real repo): `make release-version` bumped both files via `setVersion.mjs`, `make build` correctly injected the NEW package.json-sourced version into all 5 versioned `dist/*/plugin.json`/`gemini-extension.json` manifests (opencode has no versioned dist artifact — it reads the root `package.json` directly — correctly showed no diff), `make validate` passed, `make ci-build`'s untracked-dist guard correctly flagged the bump as needing a commit (the exact state `release-commit.sh` commits next in the real flow), `make changelog` produced a real entry from the worktree's own git log. Worktree and throwaway branch removed afterward; real repo confirmed untouched throughout |
| 15 | ⬜ | `feat!: cut the build, ci and release pipeline over to typescript` | Two Makefile lines flip `build`/`build-check` to Node | `make ci-build` green against committed `dist/`, `git diff dist/` empty |
| 16 | ⬜ | `chore(build): delete the python compiler and split the mutation gates` | Removes `scripts/build/`; rescopes `[tool.mutmut]` to `src/hooks/` **in the same commit**; splits CI into parallel `mutation-py` + `mutation-ts` | `grep -rn 'scripts\.build'` across the repo returns zero; both gates report a real kill rate ≥90% |
| 17 | ⬜ | `docs: describe the two-runtime world` | CoC updated throughout; § Hooks' "Stdlib-only Python" kept **verbatim** with a `LOCKED` comment | `grep -rn 'All checks live in Python' src/ dist/` empty; rebuild shows only the expected diff |

**Abandonment safety.** Commits 1–13 are purely additive or behaviour-preserving. Commits 14–15
are single-edit flips backed by the drift gate. The destructive commit is 16, last but one.

---

## Lessons learned executing commits 1–4 (read before continuing)

These are corrections and additions to the plan discovered only by building it. Future commits
must account for them; do not re-derive them from scratch.

1. **The parity canonicalizer sorts every object's keys, on both engines, rather than relying on
   matching insertion order.** Two field-order mismatches surfaced during commit 4 (Python
   `dataclasses.fields()` declaration order vs TypeScript object-literal construction order) that
   had nothing to do with the port's correctness — purely how each engine happened to build the
   object. `scripts/ci/parity_run.py`'s `_canonical()` and `scripts-ts/bin/parityRun.mts`'s
   `canonical()` both sort object/dict keys before serializing; only **array** order stays
   significant (it's the thing being tested in ordering-sensitive fixtures like layout's).
   Apply the same sorted-canonicalization discipline to every future parity leg.

2. **Python dataclass fields with snake_case names need an explicit rename table when compared
   against idiomatic camelCase TypeScript, scoped to real dataclass attributes only.**
   `_DATACLASS_FIELD_RENAME` in `parity_run.py` maps `resolve_model_tier`→`resolveModelTier`,
   `from_suffix`→`fromSuffix`, `to_suffix`→`toSuffix`, `body_key`→`bodyKey`,
   `key_prefix`→`keyPrefix` — applied only when walking `dataclasses.fields()`, never inside a
   free-form dict a descriptor carries as *data* (`Artifact.content`, gate params), where a key
   that happens to spell `body_key` must pass through untouched. Extend this table, never
   silently rename inside a data dict, when commits 6–8 port more dataclass-shaped structures.

3. **`readdirSync` returns alphabetically-sorted entries on APFS regardless of creation order** —
   which means a real-filesystem test **cannot** prove an explicit `.sort()` call is doing real
   work; removing the sort passes every such test on a Mac. ext4 (the CI runner) makes no such
   guarantee. The fix, used in `tests-ts/build/layoutSort.spec.ts` and
   `tests-ts/build/descriptorSort.spec.ts`: a **dedicated spec file** using
   `vi.mock('node:fs', ...)` to force reversed `readdirSync` output, proving the explicit sort
   recovers correct order. `vi.mock` is hoisted and module-scoped, so it must live in its own
   file — it would otherwise silently break every other test sharing that file. A `vi.spyOn` on a
   plain `require('node:fs')` object does **not** work for this: it mutates a separate CJS-interop
   object that an ESM `import { readdirSync } from 'node:fs'` never observes. Any future
   `readdirSync(...).sort()` call site (commits 6–13 will have several) needs this same treatment.

4. **A hand-mutated `while (condition)` loop test is dangerous — verify it terminates before
   running it against the real suite.** During commit 4's mutation cleanup, a hand-constructed
   mutant replaced a bounded loop condition with a literal `while (true)`, which hung the Vitest
   worker process indefinitely (had to be found via `ps aux` and `kill -9`). Prefer reasoning from
   Stryker's own reported `replacement` field over hand-rolled mutations, and always run
   subprocess verification with an explicit `timeout`.

5. **Stryker's isolated single-file `--mutate` runs can disagree with direct `vitest run`
   verification of the identical mutant.** Confirmed once directly (the `isDict` boolean
   composition in `descriptor.mts`): an isolated Stryker run reported it Survived; manually
   applying the exact same source change and running `vitest run` directly showed 15 tests
   failing. Root cause not fully characterized — treat an isolated-run "Survived" verdict as a
   *lead to verify*, not a fact, especially late in a commit when the marginal value of chasing
   one more percentage point is low. The full, non-isolated `make mutation-ts` run remains the
   authoritative gate.

6. **`js-tiktoken` throws on `<|endoftext|>` and other control tokens, exactly like Python
   `tiktoken`.** Not a bug to work around — the refusal is part of the parity contract. Both
   engines' `dump`/`tokenParity.mts` record `throws: true` for such entries and compare that
   flag like any other result, rather than excluding the case from the corpus.

7. **`pyCompat.mts`'s golden character tables are Unicode-version-specific and must be generated
   with the interpreter CI actually pins (3.9 / Unicode 13.0), never a developer's newer local
   Python.** A first draft was generated on local Python 3.12 (Unicode 15.0) and disagreed with
   CI's 3.9 (Unicode 13.0) on 93 code points below U+3101 — invisible to every test because none
   exercised those specific code points. `scripts/ci/gen_pycompat_golden.py` now records
   `unidataVersion` in its output, and `make pycompat-golden-check` (wired into CI) fails loudly,
   naming the mismatch, if the committed golden doesn't match the running interpreter's Unicode
   database. Any future character-classification table needs the same version-pinning discipline.

8. **`raw[key] ?? fallback` is NOT `dict.get(key, fallback)`.** Python's `.get` returns `fallback`
   only when `key` is *absent*; JS's `??` also collapses an explicit `null` (or `undefined`) to
   `fallback`, silently discarding a value Python would have passed on to its own type check and
   raised `DescriptorError` over. Found by review at 8 call sites in `descriptor.mts`
   (`role.body`, `field.render`, `role.resolve_model_tier`, `role.required`,
   `artifact.versioned`, `templateValue.drop`, `templateValue.key_prefix`, `template.values`) and
   fixed with a small `pyGet<T>(raw, key, fallback)` helper (`key in raw ? raw[key] : fallback`).
   Every future `raw.get(key, default)` port needs `pyGet`, never `??` or `||`.

9. **A Python dataclass field's declared default and an explicit `raw.get(key, default)` call are
   two DIFFERENT defaulting mechanisms that can look identical until you check which one the
   constructor call site actually uses for each variant.** `TemplateValue.key_prefix: str = ""` is
   one dataclass field shared by all four `from=` kinds, but only the `role_entries_js` branch of
   `_parse_template_value` passes `key_prefix=raw.get("key_prefix", "")` explicitly — the other
   three branches (`js_string`, `js_string_list`, `js_root_joins`) never mention `key_prefix` in
   their constructor call at all, so they get the dataclass's structural `""` default *always*,
   never influenced by the JSON input (which can't even carry a `key_prefix` key for those kinds —
   it isn't in their allowed key set, so `_check_keys` rejects it first). Porting this as "every
   kind defaults `keyPrefix` to `pyGet(raw, 'key_prefix', '')`" is subtly wrong: it would let a
   would-be `key_prefix` on e.g. a `js_string` value flow through if `_check_keys` were ever
   relaxed, and — the mistake actually made and caught by this same commit's own test suite — the
   opposite error (defaulting the shared literal to `null` instead of `''`) breaks `make parity` on
   every real shipped descriptor with template values, not just a hand-written fixture. When a
   Python dataclass has ONE default shared by several constructor call sites, check EACH call site
   for whether it re-derives the value from raw input or just relies on the field default silently
   — the TS port needs to mirror the call site, not just the field declaration.

10. **A full `make mutation-ts` run after a "done" commit can still surface real gaps the review
    round missed — always run it, read every non-killed mutant's actual code, and don't stop at the
    aggregate percentage.** Commit 4's post-review `descriptor.mts` mutation score was 93.30%
    (comfortably above the 90% gate), but reading all 62 non-killed mutants individually surfaced
    ~24 genuine test gaps (raw=null/string/boolean/number type-name branches, an empty-string
    `checkStr` case, `models: {}`/`smoke.expect` "empty-but-right-shape" cases the corresponding
    `vars: {}` case already covered, a `toml_command` two-field case, a position-preserving
    4-role-keys-one-wrong case, three missing `<section> must be a list` cases, a real `mkdirSync`
    directory literally shadowing a descriptor/dist-sibling filename, and more) — each fixed with a
    small, targeted test following the file's existing exact-message-assertion style.

11. **Several "surviving" mutants are genuinely equivalent, not gaps — and knowing WHY matters more
    than the count.** Recurring classes found in `descriptor.mts`, all likely to reappear verbatim
    in commits 5–13:
    - **`typeof x !== 'string'` guards ahead of a MEMBERSHIP check are structurally redundant in
      TypeScript**, because the three membership mechanisms this file uses — `Set.has(x)`,
      `Array.prototype.includes(x)`, and `Object.hasOwn(obj, x)` — all handle a non-string `x`
      gracefully rather than crashing (unlike Python's `x not in <set>`, which crashes on unhashable
      types — the very reason this port's top-of-file doc comment calls out that divergence). Six of
      the eight sites (`field.from`, `role.mode`, `role.body`, `route.kind`, `gate.protocol`,
      `dispatch`) use `Set.has()`, which is empirically verified never to throw for ANY JS value
      (tested `null`/`undefined`/objects/arrays/`Symbol`/`NaN`/functions/`Object.create(null)`). Two
      (`templateValue.kind` via `Object.hasOwn(TEMPLATE_VALUE_KINDS, kind)`, `templateValue.role` via
      `ROLE_NAMES.includes(role)`) use a different mechanism each — `Array.includes()` is equally
      throw-proof, but `Object.hasOwn()` technically CAN throw for a key value Property-Key coercion
      rejects (e.g. `Object.create(null)`); the equivalence conclusion still holds here only because
      `kind` can only ever be a JSON.parse()-produced value (string/number/boolean/null/plain-
      object/array), none of which trigger that throw. State the mechanism precisely per site rather
      than a blanket "Set.has()" description — a reader who trusts the blanket claim without
      re-deriving it reaches the right conclusion for a site-specific wrong reason.
    - **A `Set`/`Array` constant that happens to already be declared in alphabetical order** makes
      the `.sort()` call formatting its values into an error message unobservable for THAT constant
      specifically (`BODY_POLICIES`) — even though the identical `.sort()` pattern is proven to
      matter elsewhere in the same file (`MODES`, whose declaration order is NOT alphabetical). Do
      not "fix" this by reordering the source constant purely to satisfy a mutation tool.
    - **A ternary's fallback branch can be dead code for TWO DIFFERENT reasons that both need their
      own independent proof — don't let one explanation stand in for the other.** Two visually
      identical `Array.isArray(x) ? x : []` ternaries in `descriptor.mts` are both unreachable in
      their `: []` arm, but not for the same reason: (1) `routesRaw` (`parseDescriptor`, ~line 561)
      is dead because `routes` is a TOP-LEVEL key in `parseDescriptor`'s own
      `for (const key of [...required...])` loop — a raw missing it fails earlier, before this line
      ever runs. `artifacts`/`guard`/`templates` are NOT required keys and their identical-looking
      ternaries were genuinely reachable, real gaps (lesson 10's "three missing list-shape cases").
      (2) `fieldsArr` (`parseRole`, ~line 352) is dead for an UNRELATED reason: `fields` is not a
      top-level key at all, it's role-nested, so the required-key loop never touches it. It's
      unreachable because (a) for modes that don't allow `fields` at all (`preserve`/`plain`),
      `ROLE_KEYS` excludes it from the per-mode allowed-key set, so `checkKeys` rejects any raw
      `fields` before this line runs, leaving `fieldsRaw` structurally equal to the `[]` literal from
      `raw['fields'] ?? []`; and (b) for modes that DO require `fields` (`fields`/`wrap`/
      `toml_command`), an explicit `!Array.isArray(fieldsRaw) || fieldsRaw.length === 0` check a few
      lines earlier already fails for any non-array value before this ternary is reached. Two
      lookalike ternaries, two independently-necessary proofs — tracing ONE and assuming it covers
      the other is exactly the gap that let this happen the first time.
    - **A redundant, PARITY-INTENTIONAL second sort can look like a TS-only redundancy but isn't.**
      `names()`'s `Object.keys(discover(root)).sort()` is unobservable once `discover()`'s OWN
      internal sort is separately proven (`descriptor.mts` line ~669) — but checking the Python
      original (`descriptor.py`'s `names()` is `sorted(discover(root))`, independently) shows this
      is a faithful 1:1 port of an equally "redundant" Python line, not a TS artifact. Same for
      `validateLayout`'s `[...names].sort()` in its error message once `discover`'s and
      `validateLayout`'s OWN readdir sorts are proven. Confirm the redundancy is real by reading the
      Python original before writing it off — grep it, don't assume.
    - **A Node API's fallback behavior for a "wrong" argument can coincide with the correct one.**
      `readFileSync(path, '')` (an invalid encoding) does not throw — it silently returns a
      `Buffer`, and `JSON.parse(buffer)` implicitly calls `Buffer.prototype.toString()`, which
      defaults to `'utf8'` — the exact encoding the un-mutated call requested explicitly. Verified
      empirically (`node -e "readFileSync(path, '')"` returns a Buffer, no throw), per lesson 5's
      "verify, don't assume" discipline, before writing this off as equivalent.
    None of these are "skip mutation testing" — each was individually verified (by static analysis
    against the actual guard order, by checking the Python original, or by direct empirical
    reproduction) before being accepted rather than chased. An unverified "looks equivalent" guess
    is not the same thing and should still get a test.

    **This lesson's own first draft got two calls wrong, caught by an independent fresh-eyes review
    pass over this exact reasoning** — worth recording because it's a sharper example of "verify,
    don't assume" than any of the classes above. `validateLayout`'s `at === -1` marker-not-found
    guard (`descriptor.mts` ~line 610, reimplementing Python's `path.name.partition(marker)` via
    manual `.indexOf`/`.slice` arithmetic) was judged equivalent using a 3-character example
    ecosystem name (`'eco'`), where the fallback math's `dest` slice always lands past the string's
    end and is coincidentally always empty. Every REAL ecosystem name in this repo is 6+ characters
    (`cursor`, `opencode`, `claude-code`, ...) — long enough that the same fallback math produces a
    NON-empty `dest` (verified: for `entryName = 'cursorZ'`, mutating the guard away makes
    `validateLayout` wrongly ACCEPT a marker-less stray file as a valid dist sibling). The
    counter-example only exists past a length threshold the 3-character test case never crossed.
    `distFiles`'s own separate `isFile()` guard (~line 636) was assumed covered by a test that
    actually only exercises `validateLayout`'s DIFFERENT `isFile()` call site (reached via
    `discover()`, never via calling `distFiles()` directly) — two distinct guards, one test,
    silently 0% coverage on the second. Both are now real, killable tests (not classes 6/7 above)
    rather than accepted equivalents. The generalizable takeaway: a hand-verified "this can't be
    triggered" claim is only as strong as the concrete example used to check it — reach for the
    LONGEST/MOST REALISTIC input in the domain when hand-testing reachability, not the shortest one
    that's convenient to reason about by hand.

12. **A "done" mutation-testing pass is not the same thing as a "reviewed" commit — run the
    fresh-eyes review round AFTER closing mutation gaps, not before, and expect it to still find
    things.** After lesson 10/11's mutation-closing work left `descriptor.mts` at 98.16% with a
    fully-documented equivalent-mutant list, a 4-dimension parallel review (production-code
    correctness, new-test honesty, an independent audit of the equivalent-mutant reasoning itself,
    and file-split integrity), each finding adversarially re-verified by a SEPARATE agent instructed
    to try to refute it, surfaced 11 further confirmed issues zero of the mechanical gates (parity,
    coverage, mutation score, tsc, vitest, pytest) had any way to catch:
    - **Two genuine parity bugs mutation testing structurally cannot find**, because they only
      differ in WHICH of multiple simultaneous errors gets reported, not WHETHER an error is
      reported: `Object.entries()`'s integer-like-key reordering in the `vars` and `gate.tools`
      validation loops. A mutation tool proves existing tests distinguish correct code from a
      mutant; it has no way to notice that the correct code itself quietly disagrees with the
      Python original on ONE specific edge case neither engine's test suite exercised. Only a human
      (or an agent) reading both implementations side by side and asking "what if this key looks
      like an integer" finds this class of bug.
    - **Two of the equivalent-mutant "audit" agent's OWN findings caught wrong calls from the
      audit's own subject matter** — the `at === -1` guard and `distFiles`'s `isFile()` guard (see
      lesson 11's closing note) — proving that even a dedicated adversarial-audit dimension benefits
      from a SECOND independent pass rather than trusting its own first conclusion.
    - **A test whose comment claims it proves something it structurally cannot** ("a directory named
      `<eco>.dist.<dest>` is silently skipped by validateLayout") slipped past this same session's
      own fault-injection discipline, because the fault-injection check that WOULD have caught it
      (temporarily removing the guard, confirming the test goes red) was never actually run for that
      specific test — it was written by analogy to a sibling test that WAS fault-injection-verified,
      and the analogy was wrong. Writing a test "in the same shape as" a verified one is not the same
      as verifying the new one.
    - **Six tests used a substring `.toThrow()` check the file's own shared helper's docstring
      explicitly calls out as the anti-pattern this suite exists to avoid** — added faster than they
      were checked against the suite's own stated convention, across a review round whose OWN stated
      goal was tightening exactly this class of assertion elsewhere in the same file.
    The general lesson: mechanical gates (coverage/mutation/parity) prove ported code behaves like
    the code that's actually THERE to compare against — including a human's own possibly-mistaken
    equivalent-mutant reasoning, which mutation testing cannot audit itself against. They cannot
    prove the port is complete (an untested edge case both engines happen to handle differently
    stays invisible to a parity harness that never constructs that input) or that a test asserts
    what its own comment claims. A fresh-eyes review pass earns its cost precisely by not sharing the
    blind spots the mechanical gates and the original author share — run one after every commit's
    mechanical gates are green, not as a substitute for them, and expect real findings even after a
    thorough self-review, because "I already checked this carefully" and "an independent pass will
    find nothing" are not the same claim.

13. **Zod's object-level `error` callback fires for MULTIPLE distinct issue codes at once, and a
    code-blind callback silently produces the WRONG message for whichever one it wasn't written
    for.** `z.strictObject(shape, {error})`'s callback fires for both `invalid_type` ("not an object
    at all") and `unrecognized_keys` ("has a key I don't recognise") — a plain `() => "must be an
    object"` string swallows the unrecognized-keys case under the wrong text unless the callback
    checks `issue.code` first (this file's `objectError(label)` helper). `z.record()`/
    `z.partialRecord()` are worse: their callback ALSO fires for `invalid_key` ("this key doesn't
    match my key schema") — and unlike `unrecognized_keys`, an `invalid_key` issue's own `.message`
    stays the generic "Invalid key in record" wrapper text even when the callback returns
    `undefined` for it (verified empirically); the real message is nested one level down at
    `issue.issues[0].message` and has to be read out and returned explicitly. Two real bugs shipped
    from getting this wrong and were caught by review, not by writing the code carefully the first
    time: `ModelsSchema` reported "must be a non-empty object" for an unknown model TIER name
    (`models: {high: null, turbo: 'x'}`) instead of naming the allowed tiers, and a template's
    `values` record reported the same generic text for a malformed PLACEHOLDER instead of the key
    schema's own "must match `__UPPER_SNAKE__`" message. Both are now dedicated, named tests, not
    just an assumption the code map covers.

14. **A field that looks like its siblings in the schema can carry a DIFFERENT requiredness in the
    original — check the required-key list by name, not by "this looks like the same shape".**
    `DescriptorSchema.routes` was given the identical `.default([])` treatment as `artifacts`/
    `guard`/`templates` — reasonable by analogy, since all four are array-shaped optional-looking
    sections — but Python's own required-key list is `schema, name, vars, models, smoke, dispatch,
    roles, ROUTES`, and only those eight. A descriptor omitting `routes` entirely was SILENTLY
    ACCEPTED (defaulting to `[]`) instead of rejected with "missing required key 'routes'", a real,
    verified divergence from Python — caught only because `minimal()`'s test fixture always sets
    `routes: []` explicitly, so no existing test exercised the fully-omitted case, and the review's
    mutation-closing pass specifically asked "is this `.default([])` proven necessary by a test" for
    every array field, not just assumed correct because four fields were written the same way.

15. **Zod validates the WHOLE shape and collects every issue, not just the first — this changes what
    "one problem, in order" tests need to assert, not just their expected strings.** Commit 4's
    hand-written checks failed fast (guard before roles before routes...); a descriptor with several
    simultaneous problems now reports ALL of them, semicolon-joined, regardless of which one a
    fail-fast implementation would have hit first. The three tests that used to pin a specific
    fail-fast ORDER were rewritten to pin the NEW guarantee instead (nothing is hidden behind an
    earlier problem) — patching their expected strings without reconsidering what property they were
    actually proving would have left them testing something that no longer exists.

16. **A mutation that would be a TypeScript compile error under `tsc -b` is invisible to Stryker's
    mutation testing, because Stryker's test execution goes through Vitest's esbuild transform,
    which strips types without checking them — this is a REAL protection, just not one mutation
    testing can observe.** Two "BlockStatement → {}" mutants emptied the ENTIRE body of `nonEmptyStr()`
    and `oneOf()` (helper functions with explicit `: z.ZodString` / `: z.ZodEnum<...>` return type
    annotations) and were reported "Survived". Manually applying the identical mutation and running
    `npx tsc -b` directly produces `TS2355: A function whose declared type is neither 'undefined',
    'void', nor 'any' must return a value` — a real developer introducing this exact regression gets
    a compile error before ever running a test. Don't write a test to "prove" this class of mutant is
    caught; the type system already proves it, by a mechanism the mutation tool's own pipeline can't
    see. (Contrast with lesson 5's Stryker isolated-run unreliability: that was a MEASUREMENT
    artifact needing re-verification; this is a genuinely different, valid protection mechanism.)

17. **`raw.get(key, default)`-shaped Python fields aren't always typed — some are genuinely
    untyped passthrough, and assuming otherwise produces a false rejection of real, currently-shipping
    data.** `smoke.install`/`npm_package`/`npm_version` are ALLOWED keys in Python's `_SMOKE_KEYS`
    with no type check anywhere in `_parse_smoke` — `install` carries an OBJECT
    (`{method, url, flags}`) for at least one real, currently-shipping ecosystem (`cursor.json`), not
    a string. An initial draft of `SmokeSchema` assumed all three were non-empty strings (`nonEmptyStr()`
    seemed the "obviously correct" type for a field named `install`) and the mistake was caught
    immediately by `make parity` failing on a REAL fixture, not a hypothetical one — the parity
    harness running all 6 real shipped descriptors through `discover()` earns its cost here directly.
    The fix: `z.unknown().optional()` for all three, matching Python's actual (lack of) validation.

18. **Retiring byte-identical PARITY comparison for a module needs an explicit, symmetric mechanism
    in the harness itself, not just an agreement to stop checking.** Once `descriptor.mts` moved to
    Zod, its error TEXT diverges from Python's by design (see the module's own top comment) — but the
    harness's byte-diff would report every one of the 98 descriptor fixtures as a false failure if
    left unchanged. Both runners now substitute the SAME fixed placeholder string
    (`_DESCRIPTOR_ERROR_PLACEHOLDER` / `DESCRIPTOR_ERROR_PLACEHOLDER`, kept byte-identical across the
    two files by a comment cross-referencing the other) for `descriptor` module errors before
    comparison — so `make parity` still proves both engines reach the SAME accept/reject decision for
    every fixture (it caught the `routes`-required regression above, plus the `smoke.install` one)
    without asserting they explain it identically. Each side's own unit tests, not the parity
    harness, now own message-text correctness for this module going forward.

19. **The code-blind-`error`-callback bug class (lesson 13) recurs a THIRD time in the one place
    the first two fixes didn't look — the shared helper, not a per-field schema.** A 4-dimension
    fresh-eyes review of commit 5's full diff (schema fidelity, error-callback code-blindness, test
    quality, parity-harness/doc accuracy — each finding adversarially re-verified 3x by agents
    instructed to try to refute it, by rerunning the actual scenario against the live code, not just
    re-reading it) surfaced 6 further confirmed issues after `make tsc`/`vitest`/`parity`/
    `mutation-ts` were all already green:
    - **`discriminantError`, shared by all five `discriminatedUnion`s, never checked `issue.code`** —
      exactly the bug class `ModelsSchema` and `TemplateSchema.values` already shipped and fixed
      (lesson 13), but this time in the one HELPER function meant to prevent it being duplicated
      five times, not in an individual schema. A non-object discriminated-union input (e.g.
      `routes: ['oops']`) reported `"'kind' must be one of [...], got None"` — discarding the actual
      offending value — because `issue.input?.[field]` silently evaluates to `undefined` when
      `issue.input` isn't an object at all. Verified live: Zod's `invalid_type` (not-an-object) and
      `invalid_union` (bad discriminant on a real object) issue codes ARE distinguishable inside the
      same callback, exactly the way `objectError` already distinguishes `invalid_type` from
      `unrecognized_keys` for `strictObject` — an in-repo test comment claiming otherwise was itself
      wrong. Fixed by branching on `issue.code`, same pattern as `objectError`.
    - **`gate` carried a stray `.nullable()` no sibling optional field had**, silently making an
      EXPLICIT `"gate": null` equivalent to omitting the key entirely — Python's `_parse_gate` runs
      whenever `'gate' in raw` regardless of value and rejects `None`. Same lesson-14 shape (check
      requiredness/nullability against Python field-by-field, not by analogy to siblings) recurring
      on a THIRD axis: not required-vs-optional this time, but nullable-vs-not.
    - **Six `.toThrow(<string>)` assertions across two files contradicted their own inline "exact
      message, not a substring" comments** — `.toThrow(string)` is a Vitest/Jest SUBSTRING check, not
      equality; a live mutation experiment (appending a suffix to every message in `formatError`)
      sailed through all six undetected while the identical mutant failed 45 tests elsewhere in the
      same suite that used the established `expectMessage`/`toBe` helper instead. Two of the six were
      brand-new tests added in this very commit, so the weak pattern was actively re-introduced, not
      merely inherited. Fixed by converting all six to `expectMessage`.
    - **A test named "smoke requires both cli and test" only ever tested `test`** — no sibling test
      omitted `cli` while supplying `test`, so `cli`'s requiredness was asserted by the schema but
      unproven by any test; confirmed by live regression injection (`cli` made optional) passing the
      full suite undetected before the missing sibling test was added.
    - **`key_prefix`'s stricter Zod typing (`z.string()` vs Python's unenforced `str` annotation) was
      undocumented** and contradicted the file's own top-comment claim that NaN/Infinity was "the
      ONE divergence where TS is less forgiving than Python" — a self-inconsistency only a full
      re-read of the documented-divergences list against the actual schema catches. Fixed by adding
      it as a second, explicit bullet rather than changing the (safer) stricter behavior.
    - **A freshly-written lesson (18, written earlier in this same commit's documentation pass) had
      the wrong fixture count** — "93 descriptor fixtures" against an actual 98 — caught by an agent
      that independently recounted rather than trusting the number as already-verified because it
      was recently written. Being newly-authored is not evidence of being correct.
    None of these were reachable by the mechanical gate quartet (`tsc`, `vitest`, `make parity`,
    `make mutation-ts`) that had ALL already passed before this review ran — mutation testing proves
    existing tests distinguish real code from a mutant, not that the real code or the tests
    themselves are asking the right question. The meta-lesson from commit 4's lesson 12 holds again,
    one commit later, in a codebase this session itself already knew to watch for it in.

20. **"Delete the Python original once its TS replacement lands" (locked decision 12) was silently
    not happening — for SIX commits in a row — until commit 10's own pre-deletion audit caught it.**
    Commits 4–9 each wrote a faithful, verified TS test suite for its module, but never actually
    removed the corresponding `tests/build/*.py` file — both engines' tests for the SAME behavior
    kept running in parallel, 934 TS tests and 420+ Python tests covering overlapping ground, with
    no test ever flagging the duplication because nothing checks for it. It surfaced only because
    commit 10 needed to decide what to delete and a routine `ls tests/build/*.py` after supposedly
    "finishing" commits 4–9 showed 37 files still present. Fixed retroactively in this commit
    (12 files deleted alongside commit 10's own 8 directories) rather than deferred further. The
    generalizable lesson: a "done" checklist item with no verification step of its own (nothing
    asserts a Python file's ABSENCE) can silently not happen for an arbitrary number of commits: the
    build stays green, the tests stay green, and the omission is invisible until something forces a
    fresh look at the actual file list rather than trusting the commit's own summary of itself.

21. **A pre-deletion coverage audit — comparing `pytest --collect-only` counts file-by-file against
    the TS port, not just "does everything build" — found a genuinely silent test bug and two fully
    un-ported Python tests, both already sitting in a supposedly-"done" commit-9 file.**
    `tests-ts/bin/cli.spec.ts`'s "binds every standalone opencode command file to its owning agent"
    test read `join(out, 'command')` (singular) instead of the real `commands` directory; the
    `existsSync` guard around the loop was therefore always false, so the test executed ZERO
    assertions and had been reporting green since commit 9 without ever checking anything. Separately,
    `test_opencode_commands.py`'s other two tests (real descriptions/clean prompt text on the inlined
    plugin.js entries; no leftover Claude-only settings in the built bundle) had no TS counterpart at
    all — commit 9's port covered only 1 of that file's 3 tests, and nothing caught the gap because
    the file being "ported" was never checked against an actual per-test list, only trusted by name.
    Both are now fixed (the vacuous test corrected to check the real directory and drop the
    always-false guard; the two missing tests added to `opencodeMirror.spec.ts`/`cli.spec.ts`). The
    checking method that found both — running `pytest <file> --collect-only -q` for every
    Python file with a claimed TS port and diffing the count against the actual TS `it()` count,
    then reading the outlier files in full rather than trusting a summary — is the same discipline
    this migration's earlier lessons (11, 12, 19) already established for reviewing DIFFS; this
    extends it to reviewing DELETIONS, which carry the same risk of an unverified "this is covered"
    claim standing in for actually checking.

22. **A prose specification's stated mechanism ("a closed imperative vocabulary anchors the count")
    can be wrong about ITS OWN reference numbers — measuring against real content beats parsing the
    spec text more carefully.** The first implementation of `countAtomicInstructions` followed the
    plan's own words literally: split each unit on `,`/`;`/`and`/`or`/`then`/`&`, then count a
    fragment only when it was the unit's leading clause OR contained a word from a closed imperative
    vocabulary (`always`/`never`/`ensure`/the RFC 2119 subset/etc.). Measured against the real,
    current `dist/claude-code/` content, it came in LOW on every single reference number in the
    plan's own table — CLAUDE.md 23 vs. a stated 39, the full orchestrator chain 84 vs. 160 — by a
    consistent ~40-50%, not close enough to be a rounding difference. Dropping the vocabulary
    requirement entirely — count EVERY separator-delimited fragment of at least two words, no
    filter beyond that — reproduced all six reference numbers EXACTLY (39, 13, 38, 83, 160, 83) on
    the first try. The corrected reading, only obvious after measuring: "closed imperative
    vocabulary" in the plan's prose most likely refers to the CONJUNCTION words chosen for the
    separator itself (`and`/`or`/`then`, matched as whole words), not a per-fragment counting
    filter — but this is inferred FROM the working implementation, not independently confirmed,
    because the reference implementation that produced the original table was never available to
    consult directly. The generalizable lesson: when a spec describes an algorithm by prose AND
    supplies concrete expected outputs, treat the outputs as the actual spec and the prose as a
    hint — implement the simplest reading, measure against the real reference numbers immediately
    (not after building out the surrounding feature), and let disagreement drive the design instead
    of debugging a prose interpretation that already doesn't match. Also surfaced in passing: the
    plan's "worst sub-agent (cynical-reviewer)" reference row (29 blocks) turned out to describe the
    FULL sub-agent chain total (agent + A2A core + CLAUDE.md: 8+8+13=29), not the agent file alone
    (8) — the same "measure, don't assume" check resolved the ambiguity in minutes once tried,
    versus indefinitely if reasoned about from the table's row label alone.

---

## The instruction budget: a live breach the old metric hid

**✅ Executed in commit 11.** `scripts-ts/metrics/instructionCounter.mts` (`countAtomicInstructions`)
plus `scripts-ts/metrics/loadingChains.mts` (chain definitions as data, the `HARD_GATE`/`WARN_AT`
constants, and the `WAIVERS` list) implement everything this section describes. The measured table
below was reproduced EXACTLY (39/13/38/83/160/83, all six numbers) by the shipped algorithm against
the real, current `dist/claude-code/` content — see lesson 22 for how, and for the vocabulary-based
design this section's prose implies that was tried, measured LOW, and abandoned in favor of the
simpler one that matched. The orchestrator's `build.md` chain measures exactly the predicted 160 and
carries the described named waiver (`WAIVERS[0]` in `loadingChains.mts`); every other chain —
including all 16 sub-agent chains and 5 orchestrator-per-command chains, not just the two this
section originally measured — is under the 150 gate (`commands/ship.md` at 132 is the closest,
flagged as near-warn, not gated). See `tests-ts/metrics/instructionBudget.spec.ts` for the live gate
and `tests-ts/metrics/instructionCounter.spec.ts` for the hand-labelled golden corpus.

`tests/budgets/test_instruction_budget.py` already sums loading chains — sub-agent
(`agent.md` + A2A core + `CLAUDE.md`), orchestrator (`CLAUDE.md` + heaviest command + every
protocol), and each skill alone — but counts *blocks* and divides the 150 ceiling by 3.

Counting atomically (split each unit on `,` `;` `and` `or` `then` `&`):

| Chain component | blocks | V1 | **V2 (chosen)** | V3 |
|---|---|---|---|---|
| `CLAUDE.md` | 13 | 49 | 39 | 35 |
| A2A Agent-Injected Core | 8 | 17 | 13 | 11 |
| all 3 protocols | 27 | 42 | 38 | 35 |
| `build.md` (heaviest command) | 11 | 94 | 83 | 72 |
| **Orchestrator chain** | 51 *(gate 55)* | 185 | **160** | 142 |
| Worst sub-agent (`cynical-reviewer`) | 29 *(gate 35)* | 100 | 83 | 70 |

**Resolution.** Ship the measurement visibly via a **named, expiring waiver**: the config records
the measured `160` with an inline `# WAIVER: ceiling 150, over by 10 — trim build.md, see
<follow-up>`. CI stays green, no other chain may grow, the trimming follow-up deletes the waiver
line. Raising the ceiling is refused — 150 is the stated maximum.

**The 150 figure is grounded in** Jaroslawicz et al., *"How Many Instructions Can LLMs Follow at
Once?"* ([arXiv:2507.11538](https://arxiv.org/abs/2507.11538), Jul 2025, IFScale — 500
instructions × 20 models × 7 providers): top models *"maintain near-perfect performance through
150 or more instructions before declining."* It describes frontier-reasoning models specifically
(`claude-3.5-haiku` is at 43% accuracy by 100 instructions), and primacy bias peaks at 150–200
(later instructions in a chain are dropped first — an unmodelled property worth a future gate).
**130 is not a research figure** — a project safety margin, documented as such rather than implied.

**Splitter is V2**, hand-rolled regex over any NPM package: no package counts instructions, and
every NLP option (`compromise`, etc.) fails the determinism test — non-major releases have shipped
tokenization/tagging changes that would silently move counts. A closed imperative vocabulary
(`always|never|ensure|make sure|prefer|apply|run|verify|…` plus RFC-2119 `must|should|shall|may`)
keeps a miscount fixable with a one-line reviewed diff.

---

## Few-shot catalogue — the rules every commit follows

Each is a verified finding from building commits 1–4, not a style preference. New entries append;
none is ever removed once a commit depends on it.

**1 — Translate Python inline regex flags to JS flag syntax; never copy the pattern string.**
`version_targets.py:27` holds `r'(?m)^(version\s*=\s*")[^"]+(")'`. `new RegExp('(?m)^(version)')`
**throws** on Node. ❌ copy the string into `new RegExp(...)`. ✅ `/^(version\s*=\s*")[^"]+(")/m`.

**2 — A script invoked by a Makefile target calls back through `make`; it never hardcodes the
compiler.** `build_gates.sh` calls `python -m scripts.build.cli` at four sites; CI runs
`make ci-build`, never `make build` directly. Flipping the Makefile without editing this file is
provably a no-op.

**3 — Python-island tests read the committed `dist/` artifact; they never import the compiler.**
mutmut's runner is `pytest -x` — one collection `ImportError` after the compiler is deleted
zeroes the kill count for *every* mutant, reported as a real 0% regression.

**4 — Byte-identical error text is scoped to the as-is port commit only.** After Zod, the
contract is the substrings the real ported tests assert, never Python `repr()` punctuation.

**5 — Convert import-time work into an explicit factory called from the composition root.**
`serialize.py`/`cli.py` run filesystem scans as import side effects.
❌ `export const TARGETS = discover(...)` at module scope.
✅ `export function buildRegistry(descriptors) { … }` called explicitly.

**6 — Dispatch on a Zod discriminant through an exhaustive switch; only `descriptor.mts` imports
zod.** End every such switch with `default: return spec satisfies never` — a new variant becomes
a **compile error**, not a runtime failure.

**7 — Prove fault injection with a documented one-time edit per port commit, not a standing
framework.** A `tests/parity-harness/` with a defect schema and AST rewriter is new,
permanently-maintained, itself-untested tooling — the opposite of less code to review.

**8 — Emit JSON with plain `JSON.stringify` and let the drift gate be the safety net.**
`JSON.stringify(x, null, 2) + "\n"` matches `json.dumps(content, indent=2, ensure_ascii=False)`.
The V8 integer-key reordering hazard is latent (zero such keys exist); a hand-rolled writer is
new logic needing its own tests for no proven benefit.

**9 — Sort every directory walk explicitly; decode every source file with a fatal UTF-8 decoder;
prove the sort with a mocked filesystem, not a real one.** `readdirSync` order is not guaranteed
— and APFS's *is* alphabetical regardless of creation order, so a real-fs test cannot prove an
explicit sort matters. Use `vi.mock('node:fs', ...)` in a **dedicated spec file** to force reversed
order and prove the sort recovers it (see Lesson 3 above). Separately: `Path.read_text()` raises
on invalid UTF-8; `fs.readFileSync(p,'utf-8')` substitutes `U+FFFD` — decode strictly and re-check
for a genuinely manufactured replacement character (see `emit.mts`'s `readSource`), and preserve a
leading BOM (`TextDecoder(..., { ignoreBOM: true })`) since Python's `read_text` does.

**10 — Normalize copied file modes to `0o644`, and make the parity gate diff mode as well as
content.** `shutil.copyfile` copies content only; `fs.copyFileSync` propagates source permission
bits. Every `dist/` file is git mode `100644` today, invisible to `diff -r`/`cmp`.

**11 — Rescope mutmut in the same commit that deletes the paths it names, never earlier.**
An early rescope silently stops mutating live compiler code with no red signal.

**12 — One token per parallel runtime: the CI job id, its display name and its make target are
the same string.** `mutation-py` / `mutation-ts`, everywhere, no translation step.

**13 — Fix a doc's literal path reference in the same commit as the move that invalidates it.**

**14 — Never run `npm ci` in a CI job holding a push-capable or publish credential.**
`release.yml`'s checkout carries `contents:write`; a malicious `postinstall` could push to `main`.

**15 — Pin a generated golden data table to the exact interpreter/toolchain version that produced
it, and gate the mismatch in CI.** (Lesson 7.) A table generated on a newer local Python silently
encoded a different Unicode database than CI's pinned interpreter — invisible until a code point
outside the tested range appeared. `make pycompat-golden-check` regenerates and diffs against the
committed file, leading with "you're running a different interpreter than CI" rather than a raw
diff dump.

**16 — Canonicalize parity comparisons by sorting object keys on both engines; never rely on
matching construction order.** (Lesson 1.) Two engines building "the same" object in different
field order is not a defect in either — sorting before comparison removes the false failure while
keeping array order (genuinely semantic) untouched.

**17 — A Python dataclass's snake_case field name becomes idiomatic camelCase in the TypeScript
port; rename it explicitly and only at the dataclass-attribute level in the parity
canonicalizer, never inside free-form data the descriptor carries verbatim.** (Lesson 2.)

---

## The parity harness

`scripts/ci/parity.sh` (`make parity`) + `scripts/ci/parity_run.py` +
`scripts-ts/bin/parityRun.mts`. Lands in commit 3; becomes a blocking CI step in commit 8.

**Leg 1 — unit parity (commits 3–7).** Each engine exposes a fixture runner speaking one JSON
protocol (module, function, args, optional files/symlinks workspace, optional captured output
files with sha256+mode). Fixtures live in `tests/testdata/parity/*.in.json`, sourced *verbatim*
from existing pytest corpora plus adversarial additions, run through both engines, byte-diffed on
stdout/stderr.

**Leg 2 — full-tree parity (commit 8+).** Both compilers render all 6 ecosystems into two temp
trees; `diff -r` for content **and** a `stat`-based comparison for mode.

Canonicalization (see Lessons 1–2): both runners sort object/dict keys before serializing: never
array order. Python dataclasses are walked via `dataclasses.fields()` with an explicit
snake_case→camelCase rename table, applied only at the dataclass-attribute level.

Failures print one block per fixture — module, fixture path, which engine diverged, the first
differing byte offset. Retired in commit 16 alongside the Python compiler; what survives is
`make ci-build`'s drift + determinism gates, now TS-backed.

---

## End state

```
hercules/
├── src/
│   ├── content/  ecosystems/     [unchanged]
│   └── hooks/                    [PYTHON — shipped byte-copied, stdlib-only]
├── scripts-ts/
│   ├── build/                    the compiler; descriptor.mts is the ONLY zod import
│   ├── bin/                      logic-free process entry points (mutationGate, parityRun, …)
│   ├── ci/                       smokeMatrix.mts  validatePackage.mts
│   └── metrics/  setVersion.mts  updateChangelog.mts  checkMutationGate.mts
├── scripts/
│   ├── check_mutation_gate.py    [PYTHON — island]
│   ├── mutation-gate.json        shared GATE=90/WARN=95, read by BOTH gate scripts
│   └── ci/*.sh                   [BASH — delegate to `make`]
├── tests-ts/                     Vitest + Stryker
├── tests-python/hooks/           pytest + mutmut  ← the island
├── dist/                         6 trees [COMMITTED, drift-gated]
├── package.json / package-lock.json     devDeps only, files: [dist/opencode], NO "type" field
├── pyproject.toml                pytest/mutmut scoped to the island (or version mirror post-14)
├── .npmrc                        ignore-scripts=true
└── Makefile                      test-py test-ts mutation-py mutation-ts parity build
```

Everything executable is TypeScript on Node 22 (ESM `.mts`→`.mjs`), except `src/hooks/`,
`tests-python/`, `scripts/check_mutation_gate.py`, and the `scripts/ci/*.sh` gate scripts.

---

## Verification (run at the end, and any time progress is checked)

1. `make build && git diff --stat dist/` prints nothing.
2. `make ci-build` exits 0; `build_gates.sh` contains no `python -m scripts.build` string.
3. `make test-ts` ≥90% branch over `scripts-ts/`; `make test-py` ≥90% branch over `src/hooks/`.
4. `make mutation-ts` and `make mutation-py` each exit 0 with a **real** kill rate ≥90%.
5. `grep -rn 'scripts\.build' tests-python/ tests-ts/ scripts/ .githooks/ .github/` → zero.
6. A deliberately malformed descriptor prints an error naming the offending key and allowed set.
7. A synthetic **seventh ecosystem** descriptor compiles end-to-end with zero `.mts` changes.
8. `npm ls --prod` zero runtime deps; `npm pack --dry-run` ships only `dist/opencode`; the
   release workflow's privileged job contains no `npm ci`.
9. A fresh clone runs `make install && make test-py && make test-ts && make parity-tokens &&
   make build` green on Node 22.

---

## Residual risks

| Sev | Risk | Mitigation | Status |
|---|---|---|---|
| **HIGH** | Node/Python tokenizer disagreement on `cl100k_base` | Commit 2 go/no-go spike | ✅ resolved — passed, no re-baseline needed |
| **HIGH** | Commits 9–10 are the largest; a ported test becomes decorative | Gate on `make mutation-ts` ≥90%, not coverage alone; inject/revert recorded per spec | ⬜ pending |
| **HIGH** | The version-flip (14) touches `release.yml`, no dry run, privileged token | Isolated commit; full release dry-run on a throwaway tag before merge | ⬜ pending |
| MED | Commit 15 flips the whole pipeline in one edit | Commit 16's grep gate run as a dry check before 15 lands | ⬜ pending |
| MED | Stryker's wall-clock unmeasured | Profiled in commit 1: ~9s isolated, ~80–90s for the full suite at commit 4's size — well inside the 40–50 min Python budget | ✅ resolved, comfortable margin |
| MED | The two cross-field rules can't be expressed by a discriminated union alone | Commit 5 names both ported tests as merge-gate items | ⬜ pending — commit 5 |
| LOW | V8 reorders integer-like string keys where Python's dict does not | Latent; commit 7 ships an adversarial fixture documenting behaviour | ⬜ pending — commit 7 |
| LOW | ~6 npm devDeps enter a zero-dependency repo | `ignore-scripts=true`, exact-pinned lockfile, dependabot npm entry, npm-pack guard | ✅ resolved |
| **NEW — MED** | Isolated Stryker `--mutate` runs can disagree with direct `vitest run` verification of the same mutant (Lesson 5) | Treat isolated-run "Survived" as a lead to verify, not fact; the full `make mutation-ts` run is authoritative | ⚠ open, root cause not fully characterized |
| **NEW — LOW** | A generated golden data table can silently encode the wrong tool version (Lesson 7) | `make pycompat-golden-check` in CI; apply the same discipline to any future generated table | ✅ resolved for pyCompat; watch for recurrence |

---

## What this sets up (so the next release is features, not cleanup)

Deliberately in scope now:
- **The seventh-ecosystem test** makes the CoC's "a target is one data file" keystone
  executable for the first time.
- **`descriptor.mts` is the only module importing zod** — makes `z.toJSONSchema()` a near-free
  future follow-up.
- **Chain definitions become data in commit 11** — a new loading chain stops being a code change.

Deliberately deferred, named so they are choices rather than oversights:
- **Tier-aware instruction ceilings** (needs commit 11's declarative chains first).
- **Chain ordering as a gate** (primacy bias — unmodelled today).
- **Trimming `build.md`** to retire the orchestrator instruction-budget waiver.
- **Cucumber/Gherkin E2E** — explicitly out of scope, not deferred.
