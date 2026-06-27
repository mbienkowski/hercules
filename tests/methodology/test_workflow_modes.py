"""The workflow's phase/mode orchestration is explicit and human-first (Effort 2, AC7/AC8a).

Static gates only: the harness's internal permission-mode state cannot be inspected from the plugin,
so we assert the *directives* the commands must carry (construction). The effect (artifacts actually
written per phase) is an opt-in manual/e2e smoke documented in CODE_OF_CONDUCT.md.
"""

from __future__ import annotations

_DISCOVER = "plugin/commands/discover.md"
_DESIGN = "plugin/commands/design.md"
_BUILD = "plugin/commands/build.md"
_WORKFLOW = "plugin/commands/workflow.md"
_CLAUDE = "plugin/CLAUDE.md"


def test_workflow_emits_enter_and_exit_plan_mode(read_file):
    """The workflow command must call EnterPlanMode to open a phase and ExitPlanMode at the gate."""
    md = read_file(_WORKFLOW)
    assert "EnterPlanMode" in md, "workflow must call EnterPlanMode to open each plan-mode phase"
    assert "ExitPlanMode" in md, "workflow must call ExitPlanMode at the approval gate"


def test_methodology_documents_the_plan_mode_mechanism(read_file):
    """CLAUDE.md must document the EnterPlanMode/ExitPlanMode phase mechanism (not just prose)."""
    md = read_file(_CLAUDE)
    assert "EnterPlanMode" in md and "ExitPlanMode" in md, \
        "CLAUDE.md must document the EnterPlanMode/ExitPlanMode phase mechanism"


def test_plan_phases_require_plan_mode_and_gate_writes(read_file):
    """Discover, Design, and Workflow must require plan mode and gate writes on approval."""
    for f in (_DISCOVER, _DESIGN, _WORKFLOW):
        lower = read_file(f).lower()
        assert "plan mode" in lower, f"{f} must require plan mode"
        assert "approved" in lower, f"{f} must gate writes on approval"


def test_build_is_the_edit_phase_not_plan_mode(read_file):
    """Build is the edit/execute phase — it must not be in plan mode and must implement."""
    lower = read_file(_BUILD).lower()
    assert "**plan mode — required" not in lower, \
        "build must not OPEN in plan mode (it's the edit/execute phase); it may still mention the concept"
    assert ("implement" in lower or "write the minimum code" in lower), \
        "build must contain an implement/write action"


def test_workflow_chains_phases_in_order_with_approval_gates(read_file):
    """Workflow must present Discover→Design→Build in order, each gated on the user."""
    lower = read_file(_WORKFLOW).lower()
    assert lower.index("discover") < lower.index("design") < lower.index("build"), \
        "workflow must present the three phases in order"
    assert "move to design" in lower and "move to build" in lower, \
        "workflow must gate each phase transition on the user"
    assert lower.index("move to design") < lower.index("move to build"), \
        "the Design gate must precede the Build gate"


def test_advisor_loop_is_human_first(read_file):
    """The methodology must state the main agent never spawns advisors silently (human-first)."""
    assert "never spawns advisors silently" in read_file(_CLAUDE), \
        "CLAUDE.md must keep the human-first consent rule"


def test_no_phase_skips_complexity_classification(read_file):
    """Each phase must classify complexity and ask the user to confirm — depth scales, never skips."""
    for f in (_DISCOVER, _DESIGN, _BUILD):
        lower = read_file(f).lower()
        assert "complexity" in lower, f"{f} must classify complexity"
        assert "confirm or override" in lower, f"{f} must ask the user to confirm the classification"
