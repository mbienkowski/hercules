"""Delivery commands — Build-phase TDD loop: freeze, retire, cross-check, cadence, gates."""

from __future__ import annotations

import pytest
from tests.conftest import (
    BUILD as _BUILD,
    section as _section,
)
from tests.commands.conftest import _RETIRE_STEP


# Each clause of build.md's execution contract, one row = one single-target case (predicate over
# the raw text `md` and its lowercase `lo`). Data, not logic — kept inline next to its test.
_BUILD_CONTRACT = [
    ("reads_business_requirements", lambda md, lo: "business-requirements.md" in md,
     "build command must read *-business-requirements.md"),
    ("no_design_md_artifact", lambda md, lo: "design.md" not in md,
     "build command must not read a *-design.md artifact (it no longer exists)"),
    ("iterates_over_specs", lambda md, lo: "spec" in lo,
     "build command must read and iterate over spec files"),
    ("writes_under_docs", lambda md, lo: "docs/" in md, "build writes artifacts under docs/"),
    ("reads_tier_from_state", lambda md, lo: "tier" in lo and "state" in lo,
     "build must read the tier from state (complexity is scored once in Discover)"),
    ("requires_coverage", lambda md, lo: "coverage" in lo, "build must require coverage"),
    ("requires_evidence", lambda md, lo: "evidence" in lo,
     "build command must require evidence for delivered specs"),
    ("enforces_tdd_failing_tests_first", lambda md, lo: "failing test" in lo,
     "build command must enforce TDD (failing tests first)"),
    ("enforces_scope_lock", lambda md, lo: "frozen" in lo or "scope lock" in lo,
     "build command must enforce scope lock after red tests"),
    ("references_write_test_scenarios", lambda md, lo: "write-test-scenarios" in md,
     "build command must reference write-test-scenarios skill"),
    ("invokes_cynical_reviewer", lambda md, lo: "cynical-reviewer" in md,
     "build command must invoke cynical-reviewer at medium+"),
    ("invokes_learnings", lambda md, lo: "learnings" in md,
     "build command must invoke learnings skill at every tier"),
    ("references_branch_coverage", lambda md, lo: "branch" in lo,
     "build must reference branch coverage as a gate"),
    ("defers_thresholds_to_coc", lambda md, lo: "code-of-conduct" in lo,
     "build must defer quality-gate thresholds to the project's code-of-conduct.md"),
    ("no_hardcoded_number", lambda md, lo: "90%" not in md,
     "build must not hardcode a coverage/mutation number — thresholds come from code-of-conduct.md"),
    ("requires_mutation", lambda md, lo: "mutation" in lo, "build must require mutation testing"),
    ("references_kill_rate", lambda md, lo: "kill rate" in lo or "kill-rate" in lo,
     "build must reference the mutation kill rate"),
    ("suggests_bdd_for_frontend", lambda md, lo: "frontend" in lo or "Gherkin" in md or "BDD" in md,
     "build must suggest BDD/Gherkin e2e for frontend scope"),
    ("deletes_specs_via_git_rm", lambda md, lo: "git rm" in md,
     "build must delete each spec file after delivery via git rm"),
    ("verifies_traceability", lambda md, lo: "traceab" in lo,
     "build close-out must verify requirement→spec→code/test traceability"),
    ("checks_reverse_drift", lambda md, lo: "drift" in lo,
     "build close-out must check for reverse scope-drift"),
    ("no_build_md_artifact", lambda md, lo: "-build.md" not in lo,
     "build must not produce a *-build.md artifact — code + tests + git history are the record"),
]


@pytest.mark.parametrize("predicate,reason", [(p, r) for _, p, r in _BUILD_CONTRACT],
                         ids=[i for i, _, _ in _BUILD_CONTRACT])
def test_build_step_declares_each_contract_clause(read_file, predicate, reason):
    md = read_file(_BUILD)
    assert predicate(md, md.lower()), reason


def test_build_deletes_specs_after_the_traceability_check(read_file):
    """Spec deletion (git rm) must come after the traceability check, not before it."""
    lower = read_file(_BUILD).lower()
    assert lower.rindex("git rm") > lower.index("traceab")

def test_debate_round_counts_consistent(read_file):
    """The debate-consensus protocol and the a2a Core must agree on rounds per tier, and `low`
    must run exactly Round 1 (never reach Round 2)."""
    debate = read_file("dist/claude-code/protocols/debate-consensus-protocol.md").lower()
    a2a = read_file("dist/claude-code/protocols/a2a-communication-protocol.md").lower()
    # a2a Core: trivial=skip; low=R1 only; medium=R1+R2; high=R1+R2+R3; critical=...fresh-eyes
    assert "low=r1 only" in a2a, "a2a Core must state low=R1 only"
    assert "medium=r1+r2" in a2a, "a2a Core must state medium=R1+R2"
    # debate table mirrors it
    assert "round 1 only" in debate, "debate protocol must state 'Round 1 only' for low"
    assert "round 1 + 2" in debate, "debate protocol must state 'Round 1 + 2' for medium"
    # the Round-3 skip line must not claim low reaches Round 2
    assert "round 1 is its only round" in debate, \
        "debate protocol must say low's only round is Round 1 (not that Round 2 is its final round)"

def test_build_writes_current_phase_on_plan_approval(read_file):
    """Build must write current_phase: "build" at its own Plan-approval gate, otherwise Step 0's
    resume offer (which checks current_phase == "build") can never fire for a session that crashes
    before any spec has ever been retired — including silently hiding a handoff_note left for that
    session, since Step 0 gates both on the identical condition."""
    md = read_file(_BUILD)
    assert 'current_phase: "build"' in md, \
        "build must write current_phase: \"build\" somewhere in its own flow"
    lower = md.lower()
    assert lower.index("### plan approval") < lower.index('current_phase: "build"'.lower()), \
        "current_phase: \"build\" must be written at the Plan-approval gate, not only at retire"

def test_build_retire_advances_current_spec_to_next_pending(read_file):
    """Step 10's retire-time write must give current_spec an explicit value (the next pending spec,
    or unset) — the original text said 'set current_spec,' with no value at all, which would leave
    current_spec stale on every spec after the first."""
    retire_text = _section(read_file(_BUILD).lower(), *_RETIRE_STEP, label=_BUILD)
    assert "set `current_spec`," not in retire_text, \
        "retire must not leave current_spec's value unspecified"
    assert "set `current_spec` to" in retire_text, \
        "retire must set current_spec to an explicit value (next pending spec, or unset)"

def test_build_bash_path_convention_is_single_and_consistent(read_file):
    """build.md must state exactly one convention for multi-service Bash invocations — not both
    'cd {service-path} && {command}' and 'never a bare relative path' for the same Bash calls."""
    md = read_file(_BUILD)
    assert "cd {service-path}" not in md, \
        "build must not describe a 'cd into the service' Bash convention — it contradicts the " \
        "absolute-path-for-every-Bash-run rule stated later in the same file"
    assert "never a bare relative path" in md, \
        "build must keep the single absolute-path convention for Read/Write/Edit/Bash"

def test_build_references_only_real_spec_sections(read_file):
    """Design produces specs (no separate design file) and a spec's service lives in its
    ## Scope section. Build must not send agents hunting for a '## {service}' heading 'in the
    design' or a 'linked design section' — neither exists, so a multi-service build would
    stall or silently fall back to the home repo."""
    md = read_file(_BUILD)
    assert "in the design)" not in md and "linked design section" not in md, \
        "build must reference the spec's real sections, not a non-existent design artifact"
    i = md.index("For a spec scoped to a service")
    assert "## Scope" in md[i:i + 200], \
        "build's service-scoping rule must point at the spec's ## Scope section"

def test_build_opens_with_delivery_plan(read_file):
    """Build presents its delivery plan BEFORE Plan approval — anchored on the section
    headings (both tokens' first occurrences used to sit in the same preamble sentence,
    so reordering the sections stayed green)."""
    md = read_file(_BUILD)
    assert "satisfies" in md.lower(), \
        "the delivery plan must show which requirement each spec satisfies"
    assert md.index("### Step 4 — Present the delivery plan") < md.index("### Plan approval"), \
        "the delivery plan section must precede the Plan-approval gate"

def test_build_delivery_plan_allows_batching(read_file):
    """The delivery plan lets the user re-batch and set the cadence before approval."""
    lower = read_file(_BUILD).lower()
    assert "re-batch" in lower or "batch" in lower, "delivery plan must allow re-batching specs"
    assert "cadence" in lower, "delivery plan must let the user set the cadence"
    assert "deliver all" in lower and "ship each" in lower, \
        "cadence must offer deliver-all vs ship-each"

def test_build_freezes_and_diff_guards_tests(read_file):
    """Tests are frozen after they're written and machine-enforced with a git diff guard —
    and the freeze is announced with its exits, so the user is never surprised or stuck."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "frozen_test_files" in md, "build must record the frozen test files to state"
    assert "git diff" in lower, "build must git-diff-guard the frozen tests (machine-enforced)"
    assert "frozen" in lower, "build must state the tests are frozen"
    assert "announce the freeze" in lower and "bullets" in lower, \
        "build must announce the freeze verbosely, with the unblock options as bullets"
    assert "frozen_override" in md, \
        "build must offer the same-turn, user-granted frozen_override exit"
    assert "the same turn" in lower or "this turn" in lower, \
        "the freeze announcement must state the unblock happens in the same conversation turn"
    assert 'frozen_hook: "off"' in md, \
        "build must name the per-project opt-out (prompt-only discipline)"

def test_build_round_limit_persisted_with_user_decision(read_file):
    """The 3-round implementation limit is persisted in state and hands the user the decision."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "current_spec_round" in md, "build must persist the round counter in current_spec_round"
    assert "3 rounds" in lower or "round 3" in lower or "three rounds" in lower, \
        "build must cap implementation at 3 rounds"
    assert "user" in lower and ("decide" in lower or "decision" in lower), \
        "after the round limit, the user decides (no silent auto-advance)"

def test_build_writes_checkpoint_after_each_spec(read_file):
    """Build appends a build_progress checkpoint at spec retire (the durable cross-spec record)."""
    md = read_file(_BUILD)
    assert "build_progress" in md, "build must append a build_progress checkpoint entry"

def test_build_quality_gates_are_coc_driven(read_file):
    """Quality-gate thresholds come from the project's code-of-conduct.md — build carries no numbers,
    and the inverted per-tier mutation table is gone."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "code-of-conduct" in lower, "build must defer quality gates to code-of-conduct.md"
    assert "90%" not in md and "88%" not in md and "85%" not in md, \
        "build must not hardcode coverage/mutation thresholds (they live in the CoC)"

def test_build_mutation_gate_runs_in_loop_before_retire(read_file):
    """The mutation gate runs inside the per-spec loop, before the spec is retired — not post-loop —
    so a weak test is fixed while the spec is still live."""
    lower = read_file(_BUILD).lower()
    assert "mutation gate" in lower, "build must have a mutation gate"
    assert lower.index("mutation gate") < lower.index("retire the spec"), \
        "the mutation gate must run before the spec is retired"
    assert lower.index("retire the spec") < lower.index("## cross-check validation"), \
        "the cross-check validation is post-loop, after specs are retired"

def test_build_cross_check_validation_is_post_loop(read_file):
    """Cross-check validation runs after the per-spec loop and before close-out."""
    lower = read_file(_BUILD).lower()
    assert "cross-check" in lower, "build must run a cross-check validation"
    assert lower.index("cross-check") < lower.index("## close-out"), \
        "cross-check must come before close-out"
    assert "match what we set out to build" in lower, \
        "cross-check must verify the delivery matches the original intent"
    assert "build_progress" in lower, \
        "build's cross-check must read from build_progress, matching cynical-reviewer's fallback " \
        "spec-sync write target for when no live spec file exists"

def test_freeze_ends_at_spec_retire(read_file):
    """G1 scopes the freeze 'span → retire spec' — retire must clear frozen_test_files, or a
    user who never ships stays hook-blocked on delivered tests forever (phase stays 'build')."""
    retire = _section(read_file(_BUILD).lower(), *_RETIRE_STEP, label=_BUILD)
    assert "frozen_test_files" in retire, "retire must end the freeze (clear frozen_test_files)"

def test_retire_honors_a_keep_specs_coc_override(read_file):
    """Companies with their own spec practice can keep delivered specs: a code-of-conduct.md
    directive (cached as keep_specs in the registry) switches retire from git rm to
    keep-and-refresh (a present-tense update to match what shipped). Deletion stays default."""
    md = read_file(_BUILD)
    lower = md.lower()
    retire = _section(lower, *_RETIRE_STEP, label=_BUILD)
    assert "git rm" in retire, "deletion must remain the default retire behaviour"
    assert "keep_specs" in retire, "retire must honour the keep_specs override"
    assert "match what shipped" in retire, \
        "kept specs must be refreshed to a present-tense snapshot of what shipped"
    assert "keep_specs" in lower[lower.index("### step 2"):lower.index("### step 3")], \
        "Step 2's CoC check must cache the keep-specs directive into the registry entry"

def test_cross_check_reads_checkpoints_regardless_of_retire_mode(read_file):
    """The cross-check's rationale ('reads checkpoints, not the deleted files') must not assume
    deletion — under keep_specs the files exist; checkpoints stay canonical either way."""
    md = read_file(_BUILD)
    section = md[md.index("## Cross-check validation"):md.index("## Capture learnings")]
    assert "build_progress" in section, "cross-check must read the build_progress checkpoints"
    assert "deleted files" not in section, \
        "the rationale must not claim the spec files were deleted (keep_specs keeps them)"

def test_build_plan_approval_exits_plan_mode_before_writing(read_file):
    """Plan mode blocks writes; every other phase orders 'ExitPlanMode, then write'.
    Build's approval paragraph must call ExitPlanMode before the state and INDEX writes."""
    build = read_file(_BUILD)
    para = build[build.index("### Plan approval"):build.index("## Execution")]
    assert para.index("ExitPlanMode") < para.index("current_phase"), \
        "state writes must come after ExitPlanMode, outside plan mode"

def test_build_persists_the_approved_cadence(read_file):
    """'Honour the cadence approved in plan mode' (step 8) is impossible after a resume
    unless the cadence was persisted at approval; the schema must document it."""
    build = read_file(_BUILD)
    para = build[build.index("### Plan approval"):build.index("## Execution")]
    assert "cadence" in para, "Plan approval must persist the approved cadence to state"
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md"))
    prose = md[md.index("Session object (in the state file):"):]
    assert "`cadence`" in prose, "CLAUDE.md session prose must document the cadence field"

def test_retire_handles_never_committed_spec_files(read_file):
    """Nothing in the workflow commits spec files before Build retires them (Ship runs
    after), so `git rm` alone exits 128 on the first vanilla run. Retire and the resume
    reconcile must fall back to a plain delete for untracked files."""
    build = read_file(_BUILD)
    retire = build[build.index("10. **Retire the spec.**"):build.index("For a spec scoped")]
    assert "if tracked" in retire or "never committed" in retire or "untracked" in retire, \
        "retire must handle a spec file that was never committed (git rm would error)"
    reconcile = build[build.index("On resume, reconcile"):build.index("### Step 1")]
    assert "if tracked" in reconcile or "untracked" in reconcile or "plain delete" in reconcile, \
        "the reconcile's finish-the-delete must handle untracked spec files too"

def test_freeze_initializes_the_round_counter(read_file):
    """The hook's override check demands round equality against current_spec_round, but
    nothing wrote the counter before step 5 — the same-turn grant path dead-ends in
    rounds 1 frames. The step-3 freeze must set current_spec_round: 1 atomically."""
    build = read_file(_BUILD)
    step3 = build[build.index("3. **Write failing tests.**"):build.index("4. **Implement.**")]
    assert "current_spec_round" in step3, \
        "the freeze write must initialize current_spec_round so overrides can bind to it"

def test_correction_gate_expects_green(read_file):
    """A corrected test (e.g. now expecting 404) goes green against existing code — the
    old instruction to 're-pass the step-3 gate' (which demands red) could never be
    satisfied. The correction gate must accept green as the pass condition."""
    build = read_file(_BUILD)
    step5 = build[build.index("5. **Quality gates.**"):build.index("6. **Mutation gate.**")]
    assert "re-pass the step-3 gate" not in step5, \
        "the correction path must not demand the failing-test gate against corrected tests"
    assert "green" in step5.lower(), \
        "the correction gate must state that green against existing code is the pass"
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md"))
    assert "re-passes the write-tests gate" not in md, \
        "CLAUDE.md's override clearing must match the corrected-test gate"

def test_frozen_override_is_cleared_at_advance_and_retire(read_file):
    """The step-3 same-turn grant path has no clearer — the grant stays live for the rest
    of the round, wider than the single quoted instruction. The pre-advance diff gate and
    step 10's atomic write must both clear it."""
    build = read_file(_BUILD)
    retire = build[build.index("10. **Retire the spec.**"):build.index("For a spec scoped")]
    assert "frozen_override" in retire, "retire must clear any lingering frozen_override"

def test_backstop_wording_is_honest(read_file):
    """The pre-advance git diff is executed by the same model it polices — calling it
    'Enforced, not promised' overclaims. The hook enforces; the diff backstops."""
    build = read_file(_BUILD)
    assert "Enforced, not promised" not in build, \
        "prompt-side checks must not be presented as enforcement"
    assert "git diff" in build, "the pre-advance diff backstop itself must stay"

def test_build_checkpoint_carries_cross_check_fields(read_file):
    """The checkpoint is the ONLY record the cross-check reads after specs retire —
    dropping a field quietly blinds post-retire traceability."""
    step9 = _section(read_file(_BUILD), "9. **Write the checkpoint.**",
                     "10. **Retire the spec.**", label=_BUILD)
    for token in ("satisfies:", "named tests", "coverage", "mutation", "constraints"):
        assert token in step9, f"checkpoint field lost: {token!r}"

def test_retire_removes_the_round_counter(read_file):
    """CLAUDE.md promises 'removed at retire'; without it the NEXT spec starts at the
    previous spec's round — tripping the 3-round stop early and mis-binding overrides."""
    retire = _section(read_file(_BUILD), "10. **Retire the spec.**", "For a spec scoped",
                      label=_BUILD)
    assert "remove `current_spec_round`" in retire
    assert "clear `frozen_test_files` and `frozen_override`" in retire

def test_build_red_gate_demands_right_reason_failures(read_file):
    """The TDD red phase degrades to fake-red (import errors counted as failures) if the
    compile gate or right-reason clause is dropped — pinned only in the diagram before."""
    build = read_file(_BUILD)
    step2 = _section(build, "2. **Scaffold.**", "3. **Write failing tests.**", label=_BUILD)
    assert "compile" in step2, "the scaffold gate must demand compilation before tests"
    step3 = _section(build, "3. **Write failing tests.**", "4. **Implement.**", label=_BUILD)
    assert "fails for the right reason" in step3
    assert "forced failure" in step3
    assert "`current_spec_round: 1`" in step3, \
        "the freeze must literally initialize the round counter (mentions are not writes)"
