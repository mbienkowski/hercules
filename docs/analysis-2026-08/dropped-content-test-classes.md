# Text-test diet (2026-08-02) — dropped classes

> **How to read this record.** It is a historical account, kept verbatim as it was written on
> 2026-08-02, and it is cited by the header of every test file whose coverage it explains. The tree
> has been restructured since: tests moved out of `src/**/tests/` into a top-level `tests/` tree that
> mirrors the sources, so a path below such as `src/content/tests/workflowPromises.spec.ts` now lives
> at `tests/content/workflowAndProtocols/workflowPromises.spec.ts`. The reasoning is unchanged and
> nothing in the body has been edited — a record that gets corrected after the fact stops being
> evidence of what was actually decided.

Owner-approved criterion: text tests (assertions on LLM instruction files, `src/content/tests/`) are
the least-valuable class — keep only MAIN DECISIONS and FLOW. Tool tests (`src/tools/tests/`) are
CODE tests — real return, coverage kept high; only ceremony was consolidated there, no assertion was
deleted. Format: file -> what changed, then the classes of behaviour no longer independently tested.

## CONTENT (src/content/tests/): 1800 -> 1300 lines

Kept, byte-identical (DO NOT TOUCH list honoured): `promptBudgets.spec.ts`,
`workflowAndProtocols/stateKeysAgreeWithTheGuard.spec.ts`, `docsAndPlugin/theProcedureStillWorks.spec.ts`,
`skillsAndAgents/fileShapeMatchesItsFolder.spec.ts`, `workflowAndProtocols/editions.spec.ts` (verified
`git diff` on each is empty).

### workflowAndProtocols/workflowPromises.spec.ts (343 -> 256 lines)

Kept at full strength: the guardrail registry + PreToolUse hook wiring, the delegation packet field
order + ATTACHMENT-label + no-echo rules, the build-phase step-order cross-check, all 11 debate
whole-sentence pins (DEBATE_RULES) unchanged, the settlement/closure whole-sentence pins, the
judgement-gate's per-edition sweep (`it.each(TREES)`, kept exactly as before — the one per-edition
loop whose header documents a real cross-edition bug), and gate 2's consent-flow check.

Dropped:
- `independent review is judged by a fresh reviewer, never the author` (spawns cynical-reviewer +
  forbids self-review verbs on Design/Build) — did not map onto order/gate/prohibition/debate/numbers
  cleanly enough to survive the budget; no replacement.
- Six of the seven `cross-surface consistency` sweeps narrowed from `it.each(TREES)` (six editions) to
  claude-code only — no documented cross-edition failure justified keeping them multi-edition once the
  judgement gate was the one sanctioned exception. The surviving three (numbers-single-source sweep,
  roster-consent-gate, forbidden-claims sweep) still run, single-edition.
- `names the same risk-floor tier everywhere`, `labels carried material with exactly one convention
  (+never-echo-back)`, `never offers the coverage-gate reviewer as a default advisor`, `says the
  binding slice is carried, not fetched` (the per-edition PERSONA_PER_TREE variant) — dropped
  entirely; the "never pick cynical-reviewer as an advisor" pin survives folded into the
  forbidden-claims test. `ECHO_BACK`, `KNOWN_AGENTS`, `namesASource()` helpers removed as now-dead code.

### commands/commandPromises.spec.ts (268 -> 167 lines)

Kept per command: step order, the decision gates that pause for a person, and prohibitions that would
hurt someone if silently dropped (build's frozen-test protection, ship's `--force`/`--no-verify`/
AI-authorship bans and unprompted-CoC-edit ban, project-reset's irreversible-action warnings).

Dropped:
- The top-level `every command` test (trigger phrase, frontmatter fence, `disable-model-invocation:
  true`, ISO-date literal, CLAUDE.md doc-sync) — pure phrase-presence/existence checks, none of the
  five kept classes.
- discover: `resolves where project documents get saved... only writes once wizard finishes`, `offers
  to generate a missing code-of-conduct` — order/section-heading detail beyond the confirm-or-override
  gate and the machine-local-session prohibition.
- build: `the user decides what happens after three failed implementation rounds`, `resumes a saved
  session, offers a handoff note...` — state-mechanics detail, not order/gate/prohibition. `points
  forward to Ship` folded into the retire test instead of standing alone.
- ship: `re-running after a real success reports it was already shipped` (idempotency fact, not a
  gate/prohibition), `only opens a pull request once GitHub access is confirmed` narrowed — the
  AI-authorship/no-`--force`/no-`--no-verify` prohibitions absorbed into the first test; the
  auth-before-PR phrase check itself dropped. The staging test and the CoC-conflict test merged into
  one (`only stages files... and never edits the CoC unprompted`) since both read the same
  Precondition-check section.
- workflow: `advances by reading its file inline, never by asking the user to type a command...` —
  UX-flavoured prohibition, not the irreversible/overwrite/approval kind the keep-list names.
- project-reset: `reports what went, what stayed, and what could not be removed` (close-out shape
  check) — dropped; the warning, choice-gate, contract/no-fallback, and no-guessing-at-state
  prohibitions survive.
- `commands/support.ts`: removed now-dead exports (`ALL_COMMANDS`, `readPersona`, `BAD_DATE_RE`,
  `ISO_DATE_RE`, `LETTER_STEP_RE`, `pluginMarkdownFiles`) — none were referenced by any surviving test.

### skillsAndAgents/skillPromises.spec.ts (235 -> 129 lines)

Kept: no-stack-literal/no-Hercules-internal-literal sweep over every agent (critical prohibition —
reusability), QA-never-writes-test-code + reviewer-treats-inline-content-as-spec (critical
prohibitions), the packet's carried-slice-supersedes-self-read rule, the per-advisor
carried-slice-not-unconditional-read sweep (narrowed to claude-code only, folding in the lead-agent
contrast fact as extra assertions in the same test rather than a fifth test), the
code-of-conduct-generator's plan-before-scanning/never-silently-overwrite promise and its
documented-step-order check.

Dropped:
- `the agent roster` describe's two existence/shape tests (`ships every advisor and the orchestrator
  once...`, `gives every agent an identity, a project-rules reference, and the A2A reply shape`) —
  roster completeness is proven by `src/builder/tests/guards/rosterSync.spec.ts` (agent-only) and
  `settings.json`'s own artifact tests; the per-agent frontmatter-shape check has no replacement.
- `the skill roster` describe entirely (`ships exactly the documented skills, and the shipped manifest
  agrees`; `every skill states when to use it, an active one declares a hard-stop, and none hardcodes
  a stack`) — the precondition/hard-stop guarantee for `learnings` and `write-test-scenarios` (not
  `code-of-conduct-generator`, whose own step-order test survives) has no replacement; this is the
  single largest real protection lost in this file.
- `write-test-scenarios captures the real count before freezing a test` and the coverage-map's
  `a rule only counts as covered when a cited, dry-run-tried mechanical check exists` — already
  dropped in the prior amendment / dropped again here for budget respectively; no replacement.

### docsAndPlugin/docsAndPluginPromises.spec.ts (153 -> 50 lines)

Kept: the four user-typeable install/update/uninstall commands (`/plugin marketplace add`, `/plugin
install`, `claude plugin update hercules`, `/plugin uninstall`), the review/architecture-agent
no-edit-permission prohibition (security-critical, kept as-is), and the version/license
single-source-of-truth match between `pyproject.toml` and `plugin.json`.

Dropped (all README wording beyond the four commands, all structural/manifest shape checks that
weren't order/gate/prohibition/numbers-single-source):
- "never implies updates happen automatically" + opt-in wording, "explains how to fully uninstall, and
  names what survives it" (`.hercules`, `code-of-conduct.md` wording), the onboarding-disclosure test
  (Python-version/Windows warning, INDEX.md, learnings mention), the "Plugin permissions" disclosure
  test (hook/PreToolUse/read-only/fail-open/no-network/no-credentials/home-write wording, default
  model wording), `code-of-conduct resolution rules` (both tests: "names the workflow protocol as the
  source of truth" and "CLAUDE.md gives one consistent way to find the CoC"), "shipped file names are
  always lowercase, and the marketplace listing resolves" (structural, not README wording — dropped
  for budget, no replacement), "the installed plugin manifest declares a non-empty agent/advisors/
  skills/commands..." (shape/completeness check — dropped, no replacement).
- `docsAndPlugin/support.ts`: removed now-dead exports (`ALL_COMMANDS`, `section`) since the tests that
  used them are gone; kept only `PluginManifest`.

### workflowAndProtocols/statusTable.spec.ts (62 -> 17 lines, per the explicit two-test allowance)

Kept exactly two tests: `counts only the data entries of a status table` (parses) and `refuses a
document with no status table, or one with different column headers` (refuses, merged from two
separate refusal cases into one test body since both assert the same `-1` sentinel).

Dropped: the seven other structural edge-case tests (indented header, prose mentioning the header
words without a leading pipe, trailing-pipe-without-leading-pipe, per-keyword-swap parametrised sweep,
indented data rows, stops-at-a-second-table, stops-at-a-malformed-row) — `countStatusTableRows` itself
is unchanged; only its own regression coverage shrank to the two cases the owner named.

## TOOLS (src/tools/tests/): 988 -> 800 lines — ceremony only, zero assertions dropped

Every consolidation below is either (a) a shared-setup fixture replacing a one-line `fx =
build_home(tmp_path)` repeated in ~48 tests, or (b) same-shape cases merged via `pytest.mark.parametrize`
that were previously separate test functions asserting the identical shape against different inputs,
or (c) docstring compression (multi-line rationale tightened to the 1–2-line house style, content
preserved). No safety rule, refusal case, or mutation-guard assertion was removed — `python -m pytest
src/commons/repo/ src/hooks/tests/ src/tools/tests/ --cov=src/tools --cov-branch` still reports 95%
coverage (unchanged from baseline), and every case the pre-diet suite exercised still runs (as a
parametrize id) or is asserted inline in a merged test body.

- `conftest.py`: added the `fx` pytest fixture (`build_home(tmp_path)` with no variant) — collapses the
  single most repeated line in the whole package.
- `test_contract.py`: merged `test_each_outcome_carries_its_own_exit_code` and
  `test_every_outcome_replies_in_the_one_shape` (identical `argv` parametrize list, run twice) into one
  parametrized test asserting both facts per case.
- `test_deletion.py`: merged the "removes it" and "leaves the code untouched" tests (same `apply(fx,
  "--documents")` call, two assertions); merged "choosing one feature" and "choosing every feature"
  into one parametrized test; merged the two "settings" tests (same `apply(fx, "--settings")` call).
- `test_refusals.py`: the five identically-shaped safety rules (blank path, filesystem root, home
  directory, hercules-home, project directory — each: retarget, apply, assert code 1 + rule + survivor
  exists) collapsed into one `pytest.mark.parametrize` test; all five rule ids still run as distinct
  cases.
- `test_resolution.py`: the three "identifies the project from wherever you stand" tests (code
  directory, docs directory, a directory deep inside) merged into one parametrized test; the
  "two-projects-nest" and "naming settles which one" tests merged into one parametrized test over the
  same fixture shape (unnamed -> ambiguous, named -> resolved).
- `test_state.py`: merged the two "clears/keeps the pointer" tests into one parametrized test; folded
  "reports verified" into the adjacent permissions/schema-marker test (same `apply` call).
- `test_mutation_guards.py`: merged the three `verify_removed` cases (key survived / neighbour altered
  / real match) into one parametrized test.
- `test_tool_hygiene.py`, `test_mutation_guards.py`, `test_refusals.py`, `conftest.py`: docstring/module
  -comment compression throughout (rationale kept, restated in 1–2 lines per the code-of-conduct's own
  comment-style rule) — the single largest source of remaining line reduction once ceremony was
  consolidated.

## Summary

| Estate | Before | After | Gate |
|---|---|---|---|
| `src/content/tests/` | 1800 lines / 10 files | 1300 lines / 10 files | ≤1300 target — met exactly |
| `src/tools/tests/` | 988 lines / 10 files | 800 lines / 10 files | ≤800 target, ≥90% coverage — both met (95%) |

`npx vitest run` (content scope): 10 files, 111 tests, green. Full repo `npx vitest run`: 51 files, 549
tests, green (other domains' concurrent trimming by peer agents, outside this task's scope, verified
not broken). `python -m pytest src/commons/repo/ src/hooks/tests/ src/tools/tests/ --cov=src/tools
--cov-branch`: 250 passed, 1 skipped, `src/tools/project_reset.py` at 95% line/branch coverage.
`git status --porcelain dist/`: empty. Nothing committed.
