"""The workflow's phase/mode orchestration is explicit and human-first (Effort 2, AC7/AC8a).

Static gates only: Claude Code's internal permission-mode state cannot be inspected from the plugin,
so we assert the *directives* the commands must carry (construction). The effect (artifacts actually
written per phase) is an opt-in manual/e2e smoke documented in CODE_OF_CONDUCT.md.
"""

from __future__ import annotations

import re

from tests.conftest import (  # shared so a command rename updates one place, not two modules
    BUILD as _BUILD,
    DESIGN as _DESIGN,
    DISCOVER as _DISCOVER,
    SHIP as _SHIP,
    WORKFLOW as _WORKFLOW,
)

_CLAUDE = "dist/claude-code/CLAUDE.md"


def test_workflow_opens_and_closes_plan_mode_at_each_phase(read_file):
    """The workflow command must formally enter plan mode to open a phase and formally exit plan
    mode at the approval gate, so every phase has an explicit, checkable boundary rather than an
    assumed one."""
    md = read_file(_WORKFLOW)
    assert "EnterPlanMode" in md, "workflow must call EnterPlanMode to open each plan-mode phase"
    assert "ExitPlanMode" in md, "workflow must call ExitPlanMode at the approval gate"


def test_every_phase_requires_plan_mode_and_blocks_writes_until_approved(read_file):
    """Every phase -- Discover, Design, Build, Workflow, and Ship -- must open in plan mode and
    hold off writing or executing anything until the user approves. Build is included: it follows
    the same rule as every other phase."""
    for f in (_DISCOVER, _DESIGN, _BUILD, _WORKFLOW, _SHIP):
        lower = read_file(f).lower()
        assert "plan mode" in lower, f"{f} must require plan mode"
        assert "approv" in lower, f"{f} must gate writes/execution on approval"


def test_build_presents_a_delivery_plan_before_writing_any_code(read_file):
    """Build must first present a delivery plan and get the user's approval, then automatically
    carry out the implementation -- so code is never written before the user has agreed to the
    plan, the same rule every other phase follows."""
    lower = read_file(_BUILD).lower()
    assert "**plan mode — required" in lower, \
        "build must OPEN in plan mode like every other phase"
    assert "enterplanmode" in lower and "exitplanmode" in lower, \
        "build must call EnterPlanMode and ExitPlanMode around the delivery plan"
    assert "delivery plan" in lower, \
        "build's plan mode must present a delivery plan for approval"
    assert ("implement" in lower or "write the minimum code" in lower), \
        "build must still implement after Plan approval"


def test_workflow_walks_through_phases_in_a_fixed_order_with_a_gate_between_each(read_file):
    """The workflow must present Discover, Design, Build, and Ship in that fixed order, requiring
    the user's approval before moving from one to the next. This is checked against the actual
    phase sections, not a summary sentence, so the real sections could not be silently reordered
    while a stale summary still reads correctly."""
    md = read_file(_WORKFLOW)
    heads = [md.index(f"## Phase {n} — {name}") for n, name in
             ((1, "Discover"), (2, "Design"), (3, "Build"), (4, "Ship"))]
    assert heads == sorted(heads), "the four phase sections must appear in workflow order"
    lower = md.lower()
    for gate in ("move to design", "move to build", "move to ship"):
        assert gate in lower, f"workflow must gate each transition on the user ({gate!r})"
    assert (lower.index("move to design") < lower.index("move to build")
            < lower.index("move to ship")), "the transition gates must appear in phase order"


def test_advisors_are_never_brought_in_without_the_user_being_told(read_file):
    """The documented methodology must state that the main agent never spawns advisor helpers
    silently, so a user is never surprised by extra agents working on their behalf without their
    knowledge."""
    # The Sub-agent consent rule now lives in the loaded reference skill (plugin-root CLAUDE.md
    # is not loaded by Claude Code — see the conformance fixes).
    surface = read_file(_CLAUDE) + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md")
    assert "never spawns advisors silently" in surface, \
        "the loaded instruction surface must keep the human-first consent rule"


def test_project_complexity_is_judged_once_and_reused_by_later_phases(read_file):
    """Discover classifies a project's complexity a single time and asks the user to confirm it;
    Design and Build must reuse that same tier from saved state rather than asking the user to
    reclassify it, so a project isn't judged differently as it moves from phase to phase."""
    discover = read_file(_DISCOVER).lower()
    assert "complexity" in discover, "discover must classify complexity"
    assert "confirm or override" in discover, "discover must ask the user to confirm the classification"

    for f in (_DESIGN, _BUILD):
        lower = read_file(f).lower()
        assert "tier" in lower and "state" in lower, \
            f"{f} must read the tier from state (complexity scored once in Discover)"
        assert "confirm or override" not in lower, \
            f"{f} must NOT re-classify complexity (no 'confirm or override' prompt)"


def test_ship_drafts_a_commit_plan_and_waits_for_approval(read_file):
    """Ship must actually open plan mode to draft its commit plan, not merely mention "plan mode"
    in passing text -- prose alone could pass even if the real plan-mode step were removed -- and
    it must not commit anything until the user has approved that plan."""
    md = read_file(_SHIP)
    assert "EnterPlanMode" in md, "ship must call EnterPlanMode to draft its commit plan"
    assert "approved" in md.lower(), \
        "ship must gate execution on user approval of the commit plan"


def test_leaving_plan_mode_always_switches_to_auto_mode(read_file):
    """Every phase that leaves plan mode must switch specifically into auto mode, and must never
    fall back to accept-edits mode. This is checked against the precise call form, since a loose
    text search for "auto" would be fooled by an unrelated word like "automatically" while the
    real mode switch was missing."""
    for f in (_DISCOVER, _DESIGN, _BUILD, _SHIP, _WORKFLOW,
              "dist/claude-code/skills/code-of-conduct-generator/SKILL.md"):
        text = read_file(f)
        assert re.search(r"ExitPlanMode`?\s*\(`auto`\)", text), \
            f"{f} must call ExitPlanMode with the literal (`auto`) mode argument"
        assert "accept-edits" not in text.lower(), f"{f} must not use accept-edits"


def test_design_checks_the_plan_is_sound_before_asking_for_approval(read_file):
    """Design must run its implementability and coverage checks before asking the user to approve
    the plan, and only save the spec files afterward -- so the user is never asked to sign off on,
    or left with saved specs from, a plan that has not yet been validated."""
    lower = read_file(_DESIGN).lower()
    i7 = lower.index("## step 7")
    i8 = lower.index("## step 8 — plan approval")
    i9 = lower.index("## step 9")
    assert i7 < i8 < i9, \
        "design order must be validation gates (Step 7) → Plan approval (Step 8) → write specs (Step 9)"
    assert i7 < lower.index("implementability check") < i8, \
        "the implementability check must sit in the Step 7 validation gates, before Plan approval"


def test_discover_does_not_save_the_complexity_tier_before_the_session_exists(read_file):
    """Discover confirms the project's complexity tier early in the conversation but must not save
    it to disk at that point, since the session it would belong to doesn't exist yet -- an early
    save would either fail outright or create an orphaned record disconnected from the real
    session created later in the phase."""
    md = read_file(_DISCOVER)
    step3 = md[md.index("## Step 3"):md.index("## Step 4")]
    assert "~/.hercules/state" not in step3, \
        "Step 3 must not write the state file — plan mode is active and no session slug exists yet"
    step7 = md[md.index("## Step 7"):]
    assert "tier" in step7 and "~/.hercules/" in step7, \
        "Step 7's session-init write must persist the Step 3 tier"


def test_finishing_a_build_tells_the_user_to_review_before_shipping_not_ship_automatically(read_file):
    """When Build finishes, it must point the user toward running Ship next but never launch Ship
    on its own -- the user is meant to review the resulting changes and decide when they're ready,
    not get carried straight into a commit plan without being asked."""
    md = read_file(_BUILD)
    closeout = md[md.lower().index("## close-out"):]
    assert not re.search(r"Then run `/hercules:ship`", closeout), \
        "close-out must point to Ship, never invoke it — the user reviews the diff first"
    assert "/hercules:ship" in closeout, "close-out must still point forward to Ship"
    assert "review" in closeout.lower() and "ready" in closeout.lower(), \
        "close-out must hand the user the review-then-ship decision"


def test_every_project_status_shown_to_users_is_actually_set_by_some_command(repo_root):
    """Every status value the project index promises to show (discover, design, build,
    delivered) must actually be written by at least one command; otherwise a project's listed
    status could stay stuck on an old phase name -- for example, still saying "design" days into
    a Build -- misleading anyone checking on its progress. The user-set "abandoned" status is
    exempt, since a person sets that one by hand."""
    commands = [p.read_text() for p in (repo_root / "dist" / "claude-code" / "commands").glob("*.md")]
    for status in ("discover", "design", "build", "delivered"):
        assert any(
            "INDEX.md" in para and f"`{status}`" in para
            for text in commands
            for para in text.split("\n\n")
        ), f"no command writes INDEX status `{status}` — CLAUDE.md documents it as a live value"


def test_workflow_never_promises_a_later_lock_that_contradicts_the_real_lock_point(read_file):
    """Each phase locks its own artifact the moment it's saved, so the overall workflow guide must
    not tell users their requirements or specs will lock at some later point -- that would invite
    edit requests after the real lock has already happened, which no command knows how to handle.
    It must instead point users to the proper, sanctioned way to make changes afterward."""
    wf = read_file(_WORKFLOW)
    assert not re.search(r"once (?:we|you) move to \w+, the (?:requirements|specs) are locked", wf), \
        "workflow.md must not promise a later lock — artifacts lock at their phase's save"
    assert re.search(r"fresh Discover pass|through `/hercules:design`", wf), \
        "workflow.md must state the sanctioned change path after a phase's save"


def test_orchestrator_falls_back_to_a_safe_documented_action_when_something_breaks(read_file):
    """If something goes wrong partway through the workflow, the top-level instructions must
    direct the orchestrator to fall back to the safest action allowed by the workflow's own rules
    and inform the user, rather than improvising a workaround that isn't documented anywhere."""
    md = read_file(_CLAUDE)
    assert "fall back to the safest action" in md and "never improvise" in md, \
        "CLAUDE.md must carry the protocol-aligned fallback rule"


def test_workflow_advances_to_the_next_phase_automatically_instead_of_asking_the_user_to_type_a_command(read_file):
    """Each phase is protected from being auto-triggered as a shortcut, so the guided workflow
    must instruct moving to the next phase by reading that phase's instructions directly from the
    file sitting next to the current one. Without this, the guided flow would dead-end by asking
    the user to manually type the next command, breaking the promise of a hands-off, guided run."""
    md = read_file(_WORKFLOW)
    assert "reading its file" in md or "read its file" in md, \
        "workflow must say phases continue by reading the command file inline"
    assert "same directory as this file" in md, \
        "…and locate the phase files generically (beside this file), not via a path variable"
    assert "${CLAUDE_PLUGIN_ROOT}" not in md and "${CLAUDE_SKILL_DIR}" not in md, \
        "the guided flow must not depend on a path variable substituting"
    assert "never ask the user to type" in md, \
        "the guided flow must not push invocation back onto the user"
