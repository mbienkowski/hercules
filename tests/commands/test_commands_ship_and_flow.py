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
    """Each command in the workflow chain must reference the next step so the user can follow the flow."""
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

def test_workflow_command_runs_all_phases_in_sequence(read_file):
    """The workflow command must orchestrate all phases with guided transitions — anchored
    on the phase section headings, so a body swap cannot hide behind a summary-line
    mention of the phase names."""
    md = read_file(_WORKFLOW)
    heads = [md.index(f"## Phase {n} — {name}") for n, name in
             ((1, "Discover"), (2, "Design"), (3, "Build"), (4, "Ship"))]
    assert heads == sorted(heads), "the phase sections must appear in workflow order"
    lower = md.lower()
    assert "move to" in lower, "workflow must use 'move to [phase]' transition prompts"
    assert "plan mode" in lower, "workflow must enforce plan mode"
    assert "not yet" in lower, "workflow must offer 'not yet' to stay in the current phase"
    assert "move to ship" in lower, "workflow must gate the Build→Ship transition on the user"

def test_build_ship_now_routes_into_spec_scoped_ship(read_file):
    """"Ship now" in the per-spec cadence routes into Ship's plan flow (default plan presented,
    refined in rounds, executed on acceptance) as a spec-scoped invocation — never an ad-hoc
    inline commit, and never dependent on Ship's session-wide build_complete gate (set true only
    at Build's close-out, after ALL specs are retired)."""
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

def test_ship_build_and_diagram_agree_on_spec_scoped(read_file):
    """The spec-scoped contract is one decision expressed in three places — build.md's Advance,
    ship.md's section, and the detailed workflow diagram. All three must carry it (lock-step)."""
    for path in (_BUILD, _SHIP, "docs/workflow/workflow-diagram-detailed.html"):
        assert "spec-scoped" in read_file(path).lower(), \
            f"{path} must carry the spec-scoped ship contract (lock-step rule)"

def test_ship_step_defines_its_execution_contract(read_file):
    """Ship must draft a complete plan in plan mode, wait for approval, then execute automatically."""
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

def test_ship_stages_the_index_at_the_artifact_root(read_file):
    """Every INDEX.md writer uses docs/INDEX.md (one table for all sessions — CLAUDE.md §
    INDEX.md format). Ship's default staged set must look there too: a per-session
    docs/{session}/INDEX.md path matches nothing on disk, so Build's just-written 'delivered'
    status silently falls out of the close-out commit the user approves."""
    md = read_file(_SHIP)
    assert "docs/{session}/INDEX.md" not in md, \
        "ship must not stage a per-session INDEX path — the INDEX lives at the artifact root"
    assert not re.search(r"docs/\d{4}-\d{2}-\d{2}-[\w-]+/INDEX\.md", md), \
        "ship's plan example must not show a dated per-session INDEX path"
    assert "docs/INDEX.md" in md, "ship's staged set must include the artifact-root docs/INDEX.md"

def test_ship_does_not_write_docs_artifacts(read_file):
    """Ship produces git history — it must not write any new docs/ artifact."""
    md = read_file(_SHIP)
    assert "-ship.md" not in md.lower(), "ship must not produce a *-ship.md artifact"
    writing_to_docs = any(
        "docs/" in line and ("write" in line.lower() or "create" in line.lower())
        for line in md.splitlines()
        if "index.md" not in line.lower()
    )
    assert not writing_to_docs, "ship must not create new docs/ artifacts (Build owns those)"

def test_ship_pr_creation_is_conditional_on_gh(read_file):
    """Ship must make PR creation conditional on gh detection — never unconditional."""
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

def test_ship_reports_already_shipped_before_build_complete_refusal(read_file):
    """After a successful ship, build_complete is false and current_phase is 'shipped' —
    a re-run must say 'shipped at SHA', not 'finish /hercules:build first'. The shipped
    check must therefore run before the build_complete refusal."""
    ship = read_file(_SHIP)
    assert ship.index('`current_phase` is `"shipped"`') < ship.index("Local build is not complete"), \
        "the already-shipped report must precede the build_complete refusal"

def test_ship_clean_tree_recovers_a_committed_but_unrecorded_ship(read_file):
    """Ship can be interrupted between commit (step 2) and Record (step 4); the documented
    recovery is re-running /hercules:ship — but a clean tree then exits before Record,
    stranding the session (build_complete true, shipped_commit unset) forever. The
    clean-tree branch must detect and finish the interrupted ship."""
    ship = read_file(_SHIP)
    proposal = _section(ship, "## Plan proposal", "\n## ", label=_SHIP)
    clean = _section(proposal, "working tree is clean", "\n\n", label=_SHIP)
    assert "build_complete" in clean, \
        "the clean-tree branch must check for an interrupted, unrecorded ship"
    assert "step" in clean.lower(), "recovery must resume the remaining execution steps"

def test_ship_precondition_never_writes_shipped_pr(read_file):
    """shipped_pr is documented as 'written by Ship' after a real ship; the silent
    eligibility probe runs before any approval and must keep its finding
    conversation-local, not persist it to state."""
    ship = read_file(_SHIP)
    precondition = ship[:ship.index("## Plan proposal")]
    assert "record as `shipped_pr`" not in precondition, \
        "the precondition probe must not write shipped_pr before anything shipped"
    assert "_existing_pr" in precondition, "the probe still captures the URL for the plan"

def test_build_closeout_writes_the_ship_gate(read_file):
    """Ship's precondition reads build_complete (pinned) — but nothing pinned the WRITER.
    Drop the close-out write and every ship refuses forever with the suite green."""
    closeout = _section(read_file(_BUILD), "## Close-out", label=_BUILD)
    assert "`build_complete: true`" in closeout, "close-out must write the ship gate"
    assert "`current_spec: null`" in closeout, "close-out must clear the current spec"

def test_ship_stages_per_file_never_bulk(read_file):
    """git add -A would sweep unapproved working-tree files into the user-approved
    commit — the exact failure the 'Not included' plan line exists to prevent."""
    step1 = _section(read_file(_SHIP), "**1. Stage.**", "**2. Commit.**", label=_SHIP)
    assert "`git add <file>` per approved file" in step1
    assert "never `git add -A` or `git add .`" in step1

def test_ship_refuses_detached_head_and_non_repo(read_file):
    """Shipping onto a detached HEAD records a SHA no branch points at — orphaned on the
    next checkout. Nothing pinned either git-safety stop."""
    precondition = _section(read_file(_SHIP), "## Precondition check", "## Plan proposal",
                            label=_SHIP)
    assert "detached" in precondition.lower(), "ship must refuse a detached HEAD"
    assert "not a git repository" in precondition, "ship must stop outside a git repo"

def test_ship_commit_message_contract_details(read_file):
    """Scope stripping, the 72-char cap, and the BREAKING CHANGE proposal are user-facing
    output contracts — losing them yields feat(2026-06-28-user-auth): and silent breaking
    changes in history."""
    msg = _section(read_file(_SHIP), "**Commit message.**", "**Push target.**", label=_SHIP)
    assert "strip the date prefix" in msg
    assert "72" in msg
    assert "BREAKING CHANGE" in msg
