"""Delivery commands — Build-phase TDD loop: freeze, retire, cross-check, cadence, gates."""

from __future__ import annotations

from tests.conftest import (
    BUILD as _BUILD,
    section as _section,
)
from tests.commands.conftest import _RETIRE_STEP


def test_spec_files_are_deleted_only_after_traceability_is_confirmed(read_file):
    """Build only deletes a spec's files once the traceability check has confirmed everything
    in it was accounted for -- deletion is never allowed to happen first."""
    lower = read_file(_BUILD).lower()
    assert lower.rindex("git rm") > lower.index("traceab")

def test_build_records_its_phase_as_soon_as_the_plan_is_approved(read_file):
    """As soon as the delivery plan is approved, Build records that the project has entered the
    build phase -- it does not wait until the first piece of work is finished. Without this, a
    session that crashes early could never be recognized on resume as being in build, and any
    handoff note left for it would stay hidden."""
    md = read_file(_BUILD)
    assert 'current_phase: "build"' in md, \
        "build must write current_phase: \"build\" somewhere in its own flow"
    lower = md.lower()
    assert lower.index("### plan approval") < lower.index('current_phase: "build"'.lower()), \
        "current_phase: \"build\" must be written at the Plan-approval gate, not only at retire"

def test_build_gives_one_consistent_rule_for_running_commands_in_multi_service_projects(read_file):
    """Build's instructions must state exactly one rule for how to run commands in a project that
    spans multiple services, not two conflicting ones. Conflicting guidance here would leave it
    ambiguous which service's commands actually get run."""
    md = read_file(_BUILD)
    assert "cd {service-path}" not in md, \
        "build must not describe a 'cd into the service' Bash convention — it contradicts the " \
        "absolute-path-for-every-Bash-run rule stated later in the same file"
    assert "never a bare relative path" in md, \
        "build must keep the single absolute-path convention for Read/Write/Edit/Bash"

def test_build_points_agents_to_a_spec_section_that_actually_exists(read_file):
    """When Build tells an agent where to find which service a spec belongs to, it must point at
    the spec's real Scope section, not at a non-existent 'design' document. Pointing at something
    that doesn't exist would leave a multi-service build stuck searching for information it can
    never find, or silently falling back to the wrong project."""
    md = read_file(_BUILD)
    assert "in the design)" not in md and "linked design section" not in md, \
        "build must reference the spec's real sections, not a non-existent design artifact"
    i = md.index("For a spec scoped to a service")
    assert "## Scope" in md[i:i + 200], \
        "build's service-scoping rule must point at the spec's ## Scope section"

def test_delivery_plan_is_shown_to_the_user_before_they_approve_it(read_file):
    """Build must present its delivery plan, showing which requirement each planned piece of work
    satisfies, before asking the user to approve it. Showing the plan only after approval would
    defeat the point of asking for approval at all."""
    md = read_file(_BUILD)
    assert "satisfies" in md.lower(), \
        "the delivery plan must show which requirement each spec satisfies"
    assert md.index("### Step 4 — Present the delivery plan") < md.index("### Plan approval"), \
        "the delivery plan section must precede the Plan-approval gate"

def test_user_can_adjust_batching_and_delivery_cadence_before_approving(read_file):
    """Before approving the delivery plan, the user must be able to regroup the planned work into
    different batches and choose whether everything ships together or each piece ships
    separately, so they aren't locked into a plan they never actually agreed to."""
    lower = read_file(_BUILD).lower()
    assert "re-batch" in lower or "batch" in lower, "delivery plan must allow re-batching specs"
    assert "cadence" in lower, "delivery plan must let the user set the cadence"
    assert "deliver all" in lower and "ship each" in lower, \
        "cadence must offer deliver-all vs ship-each"

def test_tests_are_frozen_after_being_written_and_the_freeze_is_clearly_announced(read_file):
    """Once tests are written for a piece of work, they are locked so they can't be silently
    rewritten, and this lock is technically enforced, not just requested. The user is told about
    the freeze clearly, with the ways to unblock it listed as bullet points and a note that an
    override can be granted within the same conversation turn, plus there is a per-project
    setting to turn this behavior off -- so nobody gets stuck without knowing why or how to
    proceed."""
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

def test_the_user_decides_what_happens_after_three_failed_implementation_attempts(read_file):
    """The number of attempts made to implement a piece of work is tracked and capped at three;
    once that cap is hit, it is the user who decides what happens next, rather than the process
    silently continuing on its own."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "current_spec_round" in md, "build must persist the round counter in current_spec_round"
    assert "3 rounds" in lower or "round 3" in lower or "three rounds" in lower, \
        "build must cap implementation at 3 rounds"
    assert "user" in lower and ("decide" in lower or "decision" in lower), \
        "after the round limit, the user decides (no silent auto-advance)"

def test_a_checkpoint_is_saved_after_each_piece_of_work_is_completed(read_file):
    """Every time a piece of planned work is finished, Build saves a durable checkpoint recording
    it. Later steps rely on these checkpoints to know what has actually been delivered."""
    md = read_file(_BUILD)
    assert "build_progress" in md, "build must append a build_progress checkpoint entry"

def test_test_quality_is_checked_while_the_work_is_still_in_progress_not_after(read_file):
    """The check that verifies tests are strong enough to actually catch bugs (not just pass
    trivially) runs before a piece of work is marked complete, and the final cross-project review
    runs only after all pieces of work are complete. This ordering ensures a weak test gets fixed
    while the related work is still open, not discovered too late to fix easily."""
    lower = read_file(_BUILD).lower()
    assert "mutation gate" in lower, "build must have a mutation gate"
    assert lower.index("mutation gate") < lower.index("retire the spec"), \
        "the mutation gate must run before the spec is retired"
    assert lower.index("retire the spec") < lower.index("## cross-check validation"), \
        "the cross-check validation is post-loop, after specs are retired"

def test_final_review_runs_after_all_work_is_done_and_before_wrap_up(read_file):
    """After every piece of planned work has been completed, Build runs a final review confirming
    the delivered result matches what was originally intended, and this review happens before the
    closing steps. That review reads from saved checkpoints so it stays accurate even after
    source files are gone."""
    lower = read_file(_BUILD).lower()
    assert "cross-check" in lower, "build must run a cross-check validation"
    assert lower.index("cross-check") < lower.index("## close-out"), \
        "cross-check must come before close-out"
    assert "match what we set out to build" in lower, \
        "cross-check must verify the delivery matches the original intent"
    assert "build_progress" in lower, \
        "build's cross-check must read from build_progress, matching cynical-reviewer's fallback " \
        "spec-sync write target for when no live spec file exists"

def test_finishing_a_piece_of_work_unlocks_its_previously_frozen_tests(read_file):
    """When a piece of work is marked complete, the lock placed on its tests must be lifted.
    Otherwise a user who never finishes shipping would stay permanently blocked from editing
    tests that were, in effect, already delivered."""
    retire = _section(read_file(_BUILD).lower(), *_RETIRE_STEP, label=_BUILD)
    assert "frozen_test_files" in retire, "retire must end the freeze (clear frozen_test_files)"

def test_a_project_that_opts_to_keep_its_spec_files_gets_them_updated_instead_of_deleted(read_file):
    """By default, a spec's files are deleted once the related work is delivered. But a project
    can opt to keep its specs via a recorded project convention, in which case Build instead
    refreshes the spec's files to reflect what actually shipped, rather than deleting them. This
    lets a company that already manages specs as living documents keep doing so."""
    md = read_file(_BUILD)
    lower = md.lower()
    retire = _section(lower, *_RETIRE_STEP, label=_BUILD)
    assert "git rm" in retire, "deletion must remain the default retire behaviour"
    assert "keep_specs" in retire, "retire must honour the keep_specs override"
    assert "match what shipped" in retire, \
        "kept specs must be refreshed to a present-tense snapshot of what shipped"
    assert "keep_specs" in lower[lower.index("### step 2"):lower.index("### step 3")], \
        "Step 2's CoC check must cache the keep-specs directive into the registry entry"

def test_final_review_relies_on_saved_checkpoints_even_when_spec_files_were_kept_not_deleted(read_file):
    """The explanation for why the final review reads from saved checkpoints must not assume the
    original spec files were deleted, since a project that opts to keep its specs still has those
    files sitting around. Checkpoints must be treated as the authoritative record either way."""
    md = read_file(_BUILD)
    section = md[md.index("## Cross-check validation"):md.index("## Capture learnings")]
    assert "build_progress" in section, "cross-check must read the build_progress checkpoints"
    assert "deleted files" not in section, \
        "the rationale must not claim the spec files were deleted (keep_specs keeps them)"

def test_build_leaves_planning_mode_before_saving_the_approved_plan(read_file):
    """While in planning mode, no changes can be saved. So when the delivery plan is approved,
    Build must leave planning mode first and only then save the approval to the project's
    records. Saving before leaving planning mode would silently fail."""
    build = read_file(_BUILD)
    para = build[build.index("### Plan approval"):build.index("## Execution")]
    assert para.index("ExitPlanMode") < para.index("current_phase"), \
        "state writes must come after ExitPlanMode, outside plan mode"

def test_the_delivery_cadence_the_user_approved_is_saved_for_later_steps_to_follow(read_file):
    """When the user approves the delivery plan, the cadence they chose -- deliver everything at
    once versus ship each piece separately -- must be saved to the project's records and
    documented in the reference guide. Later steps depend on honoring that choice, which is
    impossible if it was only agreed to verbally and never recorded."""
    build = read_file(_BUILD)
    para = build[build.index("### Plan approval"):build.index("## Execution")]
    assert "cadence" in para, "Plan approval must persist the approved cadence to state"
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md"))
    prose = md[md.index("Session object (in the state file):"):]
    assert "`cadence`" in prose, "CLAUDE.md session prose must document the cadence field"

def test_completing_work_does_not_fail_when_its_spec_file_was_never_saved_to_git(read_file):
    """Nothing in the workflow saves a spec's file to source control before Build finishes the
    related work, so trying to remove it as if it were already tracked would error out. Both
    finishing a piece of work and resuming an interrupted session must correctly handle removing
    a spec file that was never tracked in the first place."""
    build = read_file(_BUILD)
    retire = build[build.index("10. **Retire the spec.**"):build.index("For a spec scoped")]
    assert "if tracked" in retire or "never committed" in retire or "untracked" in retire, \
        "retire must handle a spec file that was never committed (git rm would error)"
    reconcile = build[build.index("On resume, reconcile"):build.index("### Step 1")]
    assert "if tracked" in reconcile or "untracked" in reconcile or "plain delete" in reconcile, \
        "the reconcile's finish-the-delete must handle untracked spec files too"

def test_the_attempt_counter_starts_at_one_the_moment_tests_are_frozen(read_file):
    """The count of implementation attempts for a piece of work must be set to its starting value
    at the same moment its tests are frozen. If nothing set this counter that early, a permission
    to edit frozen tests granted later in the same turn would have no starting point to compare
    against and could never actually take effect."""
    build = read_file(_BUILD)
    step3 = build[build.index("3. **Write failing tests.**"):build.index("4. **Implement.**")]
    assert "current_spec_round" in step3, \
        "the freeze write must initialize current_spec_round so overrides can bind to it"

def test_a_corrected_test_is_allowed_to_pass_immediately_instead_of_needing_to_fail_first(read_file):
    """When a test itself was wrong and gets corrected (for example, to expect a 404 instead of a
    200), it is accepted once it passes against the existing code -- it is not forced to fail
    first the way a brand-new test must. Requiring every corrected test to fail first would
    create a check that could never be satisfied."""
    build = read_file(_BUILD)
    step5 = build[build.index("5. **Quality gates.**"):build.index("6. **Mutation gate.**")]
    assert "re-pass the step-3 gate" not in step5, \
        "the correction path must not demand the failing-test gate against corrected tests"
    assert "green" in step5.lower(), \
        "the correction gate must state that green against existing code is the pass"
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md"))
    assert "re-passes the write-tests gate" not in md, \
        "CLAUDE.md's override clearing must match the corrected-test gate"

def test_a_one_time_permission_to_edit_frozen_tests_does_not_linger_past_its_intended_use(read_file):
    """A user-granted permission to edit frozen tests, given within a single turn, must be
    cleared both by the check that runs before moving to the next attempt and when the piece of
    work is finished. Without this, the permission would stay active far longer than intended --
    for the rest of the attempt."""
    build = read_file(_BUILD)
    retire = build[build.index("10. **Retire the spec.**"):build.index("For a spec scoped")]
    assert "frozen_override" in retire, "retire must clear any lingering frozen_override"

def test_the_test_freeze_is_described_as_a_safety_net_not_a_guaranteed_enforcement(read_file):
    """The instructions must not claim the pre-advance check on frozen tests is a guaranteed
    enforcement mechanism, since that check is carried out by the same AI model whose work it is
    checking. It is described accurately as a backstop, while the separate technical lock remains
    the actual enforcement."""
    build = read_file(_BUILD)
    assert "Enforced, not promised" not in build, \
        "prompt-side checks must not be presented as enforcement"
    assert "git diff" in build, "the pre-advance diff backstop itself must stay"

def test_the_saved_checkpoint_includes_every_field_the_final_review_needs(read_file):
    """The checkpoint written when a piece of work completes is the only record the final review
    can read afterward, so it must include which requirements were satisfied, which tests were
    written, coverage, mutation-testing results, and constraints. Dropping any of these fields
    would silently blind the final review to that information."""
    step9 = _section(read_file(_BUILD), "9. **Write the checkpoint.**",
                     "10. **Retire the spec.**", label=_BUILD)
    for token in ("satisfies:", "named tests", "coverage", "mutation", "constraints"):
        assert token in step9, f"checkpoint field lost: {token!r}"

def test_finishing_a_piece_of_work_resets_the_attempt_counter_for_the_next_one(read_file):
    """When a piece of work is marked complete, its implementation-attempt counter must be
    removed. Otherwise the next piece of work would inherit the previous one's attempt count,
    hitting the three-attempt cap too early and mismatching any later-granted permissions."""
    retire = _section(read_file(_BUILD), "10. **Retire the spec.**", "For a spec scoped",
                      label=_BUILD)
    assert "remove `current_spec_round`" in retire
    # B1: frozen_baseline is cleared at retire alongside its siblings — a stale baseline left behind
    # would make the next spec's acceptance backstop re-check retired paths and false-HALT.
    assert "clear `frozen_test_files`, `frozen_baseline`, and `frozen_override`" in retire

def test_a_new_tests_failure_must_be_a_real_failure_not_a_broken_test_file(read_file):
    """Before writing tests, the code must be confirmed to still compile, and a newly written
    test must fail for a genuine, correct reason rather than because of an error like a broken
    import. Otherwise a test that never even ran properly could be mistaken for having correctly
    caught a missing feature."""
    build = read_file(_BUILD)
    step2 = _section(build, "2. **Scaffold.**", "3. **Write failing tests.**", label=_BUILD)
    assert "compile" in step2, "the scaffold gate must demand compilation before tests"
    step3 = _section(build, "3. **Write failing tests.**", "4. **Implement.**", label=_BUILD)
    assert "fails for the right reason" in step3
    assert "forced failure" in step3
    assert "`current_spec_round: 1`" in step3, \
        "the freeze must literally initialize the round counter (mentions are not writes)"


def test_build_close_out_batches_every_state_mutation_into_one_atomic_write(read_file):
    """Build close-out must collect every end-of-Build state mutation (handed_off, current_spec,
    pending_specs, build_complete, last_updated) into ONE atomic temp + rename — never a sequence
    of separate edits. A mid-close-out interruption must leave a consistent state, not a
    half-advanced one. This was a real friction point: six separate edits left inconsistent state
    on interruption."""
    closeout = _section(read_file(_BUILD), "## Close-out", label=_BUILD)
    assert "all" in closeout.lower() or "**all**" in closeout, \
        "close-out must collect all end-of-Build mutations together"
    assert "one" in closeout.lower() or "**one**" in closeout, \
        "close-out must batch into ONE atomic write"
    assert "temp + rename" in closeout, "close-out must use the atomic temp + rename pattern"


def test_build_allows_merging_traceability_and_cross_check_for_single_spec_deliveries(read_file):
    """For a single-spec delivery, the Build phase may merge the per-spec traceability review
    (Step 7) and the post-all-specs cross-check into one cynical-reviewer pass — since both
    would otherwise re-verify the same single spec minutes apart with nearly identical
    instructions. For multi-spec deliveries, they stay separate (the cross-check needs every
    spec's checkpoint). This was a real duplicated-work friction point."""
    crosscheck = _section(read_file(_BUILD), "## Cross-check validation",
                          "## Capture learnings", label=_BUILD)
    assert "single-spec" in crosscheck, \
        "cross-check must mention the single-spec case"
    assert "merge" in crosscheck, \
        "cross-check must allow merging traceability + cross-check for single-spec deliveries"
    assert "both mandates" in crosscheck, \
        "merged reviewer must receive both mandates (traceability + cross-check)"


def test_build_classifies_change_type_and_skips_scaffold_for_annotation_only(read_file):
    """Build Step 1 must classify the change type (annotation-only, net-new, refactor, mixed).
    For annotation-only changes, the scaffold gate is satisfied by existing code — the step
    should skip directly to writing tests. This eliminates a no-op scaffold phase for changes
    where every file already exists and compiles."""
    build = read_file(_BUILD)
    step1 = _section(build, "1. **Read the spec.**", "2. **Scaffold.**", label=_BUILD)
    assert "annotation-only" in step1, \
        "Step 1 must classify annotation-only as a change type"
    assert "skip to Step 3" in step1 or "skip to Step 3" in step1.lower(), \
        "annotation-only must skip the scaffold gate (existing code already compiles)"
    assert "refactor" in step1, "Step 1 must also name refactor as a change type"


def test_build_step_3_makes_write_test_scenarios_mandatory(read_file):
    """Build Step 3 must say 'Mandatory' when invoking write-test-scenarios — not just
    'Invoke'. Without the mandatory wording, the skill was skipped and all tests were written
    manually, which is exactly the churn the skill is designed to prevent."""
    step3 = _section(read_file(_BUILD), "3. **Write failing tests.**", "4. **Implement.**",
                     label=_BUILD)
    assert "Mandatory" in step3 or "mandatory" in step3.lower(), \
        "Step 3 must mark the write-test-scenarios invocation as mandatory"


def test_build_step_4_checks_guard_reachability_before_freezing(read_file):
    """Before freezing tests, Build Step 4 must confirm each new guard/assertion can actually
    fail against realistic input. If an upstream normalization (constructor default, setter,
    interceptor) makes the annotation unreachable, it should be surfaced as a warning — not
    discovered after the test breaks."""
    step4 = _section(read_file(_BUILD), "4. **Implement.**", "5. **Quality gates.**",
                     label=_BUILD)
    assert "before freezing" in step4.lower(), \
        "Step 4 must check guard reachability before the freeze"
    assert "unreachable" in step4.lower(), \
        "Step 4 must warn about unreachable guards (upstream normalization)"


def test_build_step_4_runs_test_compile_on_constructor_changes(read_file):
    """When the implementation changes a constructor or signature of a class with existing tests,
    Build Step 4 must run test-compile before the full check — not discover the breakage at the
    full check phase. This catches 8+ test file breakages upfront."""
    step4 = _section(read_file(_BUILD), "4. **Implement.**", "5. **Quality gates.**",
                     label=_BUILD)
    assert "test-compile" in step4.lower(), \
        "Step 4 must run test-compile after constructor/signature changes"
    assert "constructor" in step4.lower() or "signature" in step4.lower(), \
        "Step 4 must name constructor/signature changes as the trigger"


def test_build_step_5_verifies_coverage_per_touched_file_not_aggregate(read_file):
    """Build Step 5 must verify coverage thresholds per touched file (every file in the spec's
    ## Affected code), not just aggregate project coverage. The aggregate number can hide a file
    below the threshold — the gate must extract and verify at the file level."""
    step5 = _section(read_file(_BUILD), "5. **Quality gates.**", "6. **Mutation gate.**",
                     label=_BUILD)
    assert "per touched file" in step5.lower(), \
        "Step 5 must verify coverage per touched file, not just aggregate"
    assert "affected code" in step5.lower(), \
        "Step 5 must reference the spec's ## Affected code section as the file list"
