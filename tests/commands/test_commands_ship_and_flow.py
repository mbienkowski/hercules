"""Delivery commands — Ship phase, workflow orchestration, and cross-phase continuity."""

from __future__ import annotations

import re
from tests.conftest import (
    BUILD as _BUILD,
    DESIGN as _DESIGN,
    DISCOVER as _DISCOVER,
    SHIP as _SHIP,
    WORKFLOW as _WORKFLOW,
    section as _section,
)


def test_each_delivery_step_points_forward_to_the_next(read_file):
    """Each phase's instructions must tell the user which command to run next, so a person
    following Discover, then Design, then Build is never left wondering how to continue into
    the following phase."""
    # Given
    chain = [
        (_DISCOVER, "/hercules:design"),
        (_DESIGN,   "/hercules:build"),
        (_BUILD,    "/hercules:ship"),
    ]

    # When / Then
    for file, next_step in chain:
        md = read_file(file)
        assert next_step in md, f"{file} must point forward to the next step {next_step!r}"

def test_workflow_command_walks_the_user_through_every_phase_in_order(read_file):
    """Running the workflow command must guide the user through Discover, Design, Build, and
    Ship in that fixed order, always pausing in plan mode for the user's go-ahead (or letting
    them say 'not yet' to stay put) before moving on -- so nobody is swept into a later phase
    without agreeing to it first."""
    md = read_file(_WORKFLOW)
    heads = [md.index(f"## Phase {n} — {name}") for n, name in
             ((1, "Discover"), (2, "Design"), (3, "Build"), (4, "Ship"))]
    assert heads == sorted(heads), "the phase sections must appear in workflow order"
    lower = md.lower()
    assert "move to" in lower, "workflow must use 'move to [phase]' transition prompts"
    assert "plan mode" in lower, "workflow must enforce plan mode"
    assert "not yet" in lower, "workflow must offer 'not yet' to stay in the current phase"
    assert "move to ship" in lower, "workflow must gate the Build→Ship transition on the user"

def test_choosing_ship_now_mid_build_opens_a_full_review_not_a_quiet_commit(read_file):
    """Choosing "ship now" partway through Build must open the same full review Ship normally
    gives -- a plan shown to the user, refined if needed, and committed only once they accept --
    never a quiet inline commit performed on the spot. It also must not require every other
    piece of work in Build to be finished first, since "ship now" is meant to ship just the one
    piece that's ready."""
    md = read_file(_BUILD)
    lower = md.lower()
    i_advance = lower.index("**advance.**")
    i_next = lower.index("**write the checkpoint.**")
    advance_step = lower[i_advance:i_next]
    assert "ship now" in advance_step, "build must define the 'ship now' option inside Advance"
    assert "spec-scoped" in advance_step and "/hercules:ship" in advance_step, \
        "'ship now' must route into /hercules:ship's spec-scoped plan flow"
    assert "git add" not in advance_step and "git commit" not in advance_step, \
        "'ship now' must not perform an inline commit — Ship's plan flow owns the commit"
    assert "not retired" in advance_step, \
        "Advance must state a failed spec-scoped ship returns control here, spec not retired"
    assert "build_complete" not in advance_step, \
        "'ship now' must not reference/depend on build_complete — that's Ship's session-wide gate"

def test_shipping_one_piece_at_a_time_is_documented_consistently_everywhere(read_file):
    """The rule that work is shipped one piece at a time, not only once everything is finished,
    must be documented the same way in Build's instructions, Ship's instructions, and the
    workflow diagram -- so a reader of any one of them comes away with the same understanding."""
    for path in (_BUILD, _SHIP, "docs/workflow/workflow-diagram-detailed.html"):
        assert "spec-scoped" in read_file(path).lower(), \
            f"{path} must carry the spec-scoped ship contract (lock-step rule)"

def test_ship_shows_the_user_a_complete_plan_before_committing_anything(read_file):
    """Before touching the repository, Ship must draft a full plan -- which files to stage, a
    Conventional-Commits-style message, and a push step -- and wait for the user's approval
    before running it. It must never suggest a forced or unverified push and must never add
    AI-authorship notes to the commit, and it records the resulting commit for later reference."""
    md = read_file(_SHIP)
    lower = md.lower()
    assert "/hercules:ship" in md, "ship must contain its own trigger phrase"
    assert "plan mode" in lower, "ship must enter plan mode to draft the commit plan"
    assert "build_complete" in md, "ship must gate on build_complete from hercules-config"
    assert "index.md" in lower, "ship must include INDEX.md in the default staged set"
    assert "commit message" in lower, "ship must propose a commit message"
    assert "approved" in lower, "ship must wait for approval before executing"
    assert ("conventional" in lower or "feat(" in md or "fix(" in md), \
        "ship must format the suggested message in Conventional Commits format"
    assert "push" in lower, "ship must include a push step in the plan"
    assert "--no-verify" not in md, "ship must never suggest --no-verify"
    assert "--force" not in md, "ship must never suggest --force"
    assert "--force-with-lease" not in md, "ship must never suggest --force-with-lease"
    assert "co-authored" not in lower and "generated with" not in lower, \
        "ship must not add AI attribution to commit messages"
    assert "shipped_commit" in md, "ship must record the commit SHA in hercules-config"

def test_ships_default_commit_includes_the_real_shared_index_file(read_file):
    """The project index lives in one shared file, not a separate copy per work session. Ship's
    default list of files to commit must point at that real, shared location -- if it pointed at
    a per-session path instead, the "delivered" status Build just wrote would silently be left
    out of the commit the user approves."""
    md = read_file(_SHIP)
    assert "docs/{session}/INDEX.md" not in md, \
        "ship must not stage a per-session INDEX path — the INDEX lives at the artifact root"
    assert not re.search(r"docs/\d{4}-\d{2}-\d{2}-[\w-]+/INDEX\.md", md), \
        "ship's plan example must not show a dated per-session INDEX path"
    assert "docs/INDEX.md" in md, "ship's staged set must include the artifact-root docs/INDEX.md"

def test_shipping_never_creates_a_new_documentation_file_of_its_own(read_file):
    """Ship's job is to commit and push work that earlier phases already produced -- it must
    never generate a new document (such as a ship-summary file) as a side effect of shipping."""
    md = read_file(_SHIP)
    assert "-ship.md" not in md.lower(), "ship must not produce a *-ship.md artifact"
    writing_to_docs = any(
        "docs/" in line and ("write" in line.lower() or "create" in line.lower())
        for line in md.splitlines()
        if "index.md" not in line.lower()
    )
    assert not writing_to_docs, "ship must not create new docs/ artifacts (Build owns those)"

def test_pull_request_creation_only_happens_when_github_access_is_confirmed(read_file):
    """Ship must check that the user is logged into GitHub before offering to open a pull
    request -- it never assumes GitHub access is available. It must also detect an
    already-open pull request so it doesn't create a duplicate, must record the pull request's
    web address for later reference, and must never add AI-authorship notes to the pull
    request text."""
    md = read_file(_SHIP)
    lower = md.lower()
    assert "gh pr" in lower, \
        "ship must reference gh pr create for optional PR creation"
    assert "auth" in lower, \
        "ship must check gh auth status before proposing PR creation"
    assert "shipped_pr" in md, \
        "ship must record the PR URL in hercules-config"
    assert "co-authored" not in lower, \
        "ship must not add AI attribution to PR bodies"
    assert "generated with" not in lower, \
        "ship must not add AI attribution to PR bodies"
    assert "existing" in lower or "already" in lower, \
        "ship must detect and handle an existing open PR to avoid duplicates"

def test_re_running_ship_after_success_reports_it_was_already_shipped(read_file):
    """Once a piece of work has already been shipped, running Ship again must tell the user it
    was already shipped, and at which commit -- not tell them to go finish Build first. This
    matters because, right after a successful ship, the flag Ship would otherwise check for
    ("Build is complete") has already been reset for the next round of work, and checking that
    flag first would produce a confusing, wrong refusal."""
    ship = read_file(_SHIP)
    assert ship.index('`current_phase` is `"shipped"`') < ship.index("Local build is not complete"), \
        "the already-shipped report must precede the build_complete refusal"

def test_ship_recovers_gracefully_if_interrupted_right_after_committing(read_file):
    """If Ship is interrupted after it has committed but before it finishes recording that the
    ship happened, simply running Ship again must notice the tree is already clean, recognize
    the unfinished ship, and complete the remaining recording step -- rather than exiting
    silently and leaving the session stuck in an inconsistent, unrecoverable state."""
    ship = read_file(_SHIP)
    proposal = _section(ship, "## Plan proposal", "\n## ", label=_SHIP)
    clean = _section(proposal, "working tree is clean", "\n\n", label=_SHIP)
    assert "build_complete" in clean, \
        "the clean-tree branch must check for an interrupted, unrecorded ship"
    assert "step" in clean.lower(), "recovery must resume the remaining execution steps"

def test_a_silent_pre_check_for_an_existing_pull_request_is_never_recorded_as_a_real_ship(read_file):
    """Before showing the user a plan, Ship quietly checks whether a pull request already
    exists so it can mention that in the proposal -- but this background check must never
    itself be recorded as though a pull request was actually created, since nothing has been
    shipped yet at that point."""
    ship = read_file(_SHIP)
    precondition = ship[:ship.index("## Plan proposal")]
    assert "record as `shipped_pr`" not in precondition, \
        "the precondition probe must not write shipped_pr before anything shipped"
    assert "_existing_pr" in precondition, "the probe still captures the URL for the plan"

def test_finishing_build_flips_the_switch_that_lets_shipping_begin(read_file):
    """When Build finishes all of its work, its close-out step must mark the project as ready
    to ship and clear the marker for which piece of work was in progress -- otherwise Ship,
    which checks for that ready marker before doing anything, would refuse to run even though
    there is genuinely nothing left to build."""
    closeout = _section(read_file(_BUILD), "## Close-out", label=_BUILD)
    assert "`build_complete: true`" in closeout, "close-out must write the ship gate"
    assert "`current_spec: null`" in closeout, "close-out must clear the current spec"

def test_ship_only_commits_the_files_the_user_explicitly_approved(read_file):
    """Ship must add files to the commit one at a time, by name, and must never use a bulk
    "add everything" command -- a bulk add could sweep unrelated, unapproved changes sitting in
    the working tree into the commit along with what the user actually approved."""
    step1 = _section(read_file(_SHIP), "**1. Stage.**", "**2. Commit.**", label=_SHIP)
    assert "`git add <file>` per approved file" in step1
    assert "never `git add -A` or `git add .`" in step1

def test_ship_refuses_to_run_outside_a_repository_or_on_a_disconnected_checkout(read_file):
    """Ship must stop with a clear message if it isn't run inside a git repository, and
    likewise if the checkout isn't attached to any branch. Committing in that disconnected
    state would record a commit that no branch points to, so it would be silently lost the next
    time the user switches branches."""
    precondition = _section(read_file(_SHIP), "## Precondition check", "## Plan proposal",
                            label=_SHIP)
    assert "detached" in precondition.lower(), "ship must refuse a detached HEAD"
    assert "not a git repository" in precondition, "ship must stop outside a git repo"

def test_ships_proposed_commit_message_follows_the_teams_formatting_rules(read_file):
    """The commit message Ship proposes must strip any date prefix from the work item's name,
    keep its summary line within 72 characters, and call out any breaking change explicitly --
    getting any of these wrong would leave messy or misleading text permanently in the
    project's commit history."""
    msg = _section(read_file(_SHIP), "**Commit message.**", "**Push target.**", label=_SHIP)
    assert "strip the date prefix" in msg
    assert "72" in msg
    assert "BREAKING CHANGE" in msg

def test_ship_surfaces_prior_session_uncommitted_changes_before_plan_mode(read_file):
    """Ship's precondition must surface uncommitted files that didn't come from this session
    (likely left over from a prior session) and ask before proceeding — rather than barreling
    into a push that the dirty tree will reject mid-Ship. A `git push` rejection mid-phase is
    the failure mode this guard prevents."""
    precondition = _section(read_file(_SHIP), "## Precondition check", "## Plan proposal",
                            label=_SHIP)
    assert "git status --porcelain" in precondition, \
        "ship must classify `git status --porcelain` entries before plan mode"
    assert "in-session" in precondition and "external" in precondition, \
        "ship must classify entries as in-session vs external (prior session)"
    assert "ask before plan mode" in precondition, \
        "ship must ask about external entries before entering plan mode (not proceed silently)"

def test_ship_asks_once_on_code_of_conduct_conflict_never_silently_edits(read_file):
    """When a code-of-conduct.md rule blocks an explicit user request (commit, push, PR), Ship
    must ask once before acting — never silently edit the project's CoC. A casual aside like
    'deleted that, hercules can push' is NOT consent to edit the standards file."""
    precondition = _section(read_file(_SHIP), "## Precondition check", "## Plan proposal",
                            label=_SHIP)
    assert "ask once" in precondition, "ship must ask once on a CoC conflict"
    assert "never edit the CoC unprompted" in precondition, \
        "ship must never edit the CoC without explicit confirmation"
    persona = read_file("dist/claude-code/CLAUDE.md")
    assert "asked about once" in persona, \
        "persona.md must carry the ask-once principle (pinned here so a future edit can't drop it)"
