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
    """Every phase — Discover, Design, Build, Workflow, and Ship — must require plan mode and gate
    its write/execution on approval. Build is included: it opens in plan mode like the rest."""
    for f in (_DISCOVER, _DESIGN, _BUILD, _WORKFLOW, _SHIP):
        lower = read_file(f).lower()
        assert "plan mode" in lower, f"{f} must require plan mode"
        assert "approv" in lower, f"{f} must gate writes/execution on approval"


def test_build_opens_in_plan_mode_then_executes(read_file):
    """Build opens in plan mode (presents a delivery plan, takes Plan approval), then auto-executes
    the per-spec TDD loop — every phase opens in plan mode, no exceptions."""
    lower = read_file(_BUILD).lower()
    assert "**plan mode — required" in lower, \
        "build must OPEN in plan mode like every other phase"
    assert "enterplanmode" in lower and "exitplanmode" in lower, \
        "build must call EnterPlanMode and ExitPlanMode around the delivery plan"
    assert "delivery plan" in lower, \
        "build's plan mode must present a delivery plan for approval"
    assert ("implement" in lower or "write the minimum code" in lower), \
        "build must still implement after Plan approval"


def test_workflow_chains_phases_in_order_with_approval_gates(read_file):
    """Workflow must present Discover→Design→Build→Ship in order, each gated on the user.
    Anchored on the phase headings — a summary-line mention must never satisfy the order
    check while the actual phase sections are swapped."""
    md = read_file(_WORKFLOW)
    heads = [md.index(f"## Phase {n} — {name}") for n, name in
             ((1, "Discover"), (2, "Design"), (3, "Build"), (4, "Ship"))]
    assert heads == sorted(heads), "the four phase sections must appear in workflow order"
    lower = md.lower()
    for gate in ("move to design", "move to build", "move to ship"):
        assert gate in lower, f"workflow must gate each transition on the user ({gate!r})"
    assert (lower.index("move to design") < lower.index("move to build")
            < lower.index("move to ship")), "the transition gates must appear in phase order"


def test_advisor_loop_is_human_first(read_file):
    """The methodology must state the main agent never spawns advisors silently (human-first)."""
    # The Sub-agent consent rule now lives in the loaded reference skill (plugin-root CLAUDE.md
    # is not loaded by Claude Code — see the conformance fixes).
    surface = read_file(_CLAUDE) + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md")
    assert "never spawns advisors silently" in surface, \
        "the loaded instruction surface must keep the human-first consent rule"


def test_complexity_scored_once_read_forward(read_file):
    """Complexity is scored once in Discover and read forward. Discover classifies and asks the user
    to confirm; Design and Build read the tier from state and must NOT re-classify (no
    'confirm or override' prompt) — the tier still governs every phase (depth scales, never skips)."""
    discover = read_file(_DISCOVER).lower()
    assert "complexity" in discover, "discover must classify complexity"
    assert "confirm or override" in discover, "discover must ask the user to confirm the classification"

    for f in (_DESIGN, _BUILD):
        lower = read_file(f).lower()
        assert "tier" in lower and "state" in lower, \
            f"{f} must read the tier from state (complexity scored once in Discover)"
        assert "confirm or override" not in lower, \
            f"{f} must NOT re-classify complexity (no 'confirm or override' prompt)"


def test_ship_requires_plan_mode(read_file):
    """Ship must actually call EnterPlanMode — 'plan mode' prose alone satisfied the old
    disjunction while every EnterPlanMode call was removed."""
    md = read_file(_SHIP)
    assert "EnterPlanMode" in md, "ship must call EnterPlanMode to draft its commit plan"
    assert "approved" in md.lower(), \
        "ship must gate execution on user approval of the commit plan"


def test_ship_requires_build_complete_before_proceeding(read_file):
    """Ship must refuse when build_complete is not true — pinned to the refusal sentence
    inside the precondition section ('complete' being a substring of 'build_complete'
    made the old any()-check a tautology)."""
    md = read_file(_SHIP)
    precondition = md[:md.index("## Plan proposal")]
    assert "build_complete" in precondition, \
        "ship must read build_complete from the per-project state as its precondition"
    assert "Local build is not complete. Finish `/hercules:build` first." in precondition, \
        "the refusal sentence IS the gate — it must live in the precondition section"


def test_exit_plan_mode_uses_auto_mode(read_file):
    """Every plan-mode exit requests `auto` — pinned as the literal call form, because a
    bare "auto" substring is satisfied by "automatically" while the mode argument is
    silently dropped."""
    for f in (_DISCOVER, _DESIGN, _BUILD, _SHIP, _WORKFLOW,
              "dist/claude-code/skills/code-of-conduct-generator/SKILL.md"):
        text = read_file(f)
        assert re.search(r"ExitPlanMode`?\s*\(`auto`\)", text), \
            f"{f} must call ExitPlanMode with the literal (`auto`) mode argument"
        assert "accept-edits" not in text.lower(), f"{f} must not use accept-edits"


def test_all_phases_use_uniform_plan_approval_gate(read_file):
    """Discover, Design, Build, and Ship end on one identically-named gate — 'Plan approval' — with the
    same user-facing sub-info, and each gates its write/execution on it."""
    phrase = "you approve the phase after reviewing the plan"
    for f in (_DISCOVER, _DESIGN, _BUILD, _SHIP):
        lower = read_file(f).lower()
        assert "plan approval" in lower, f"{f} must carry the uniform 'Plan approval' gate"
        assert phrase in lower, f"{f} must use the shared Plan-approval sub-info"


def test_design_validates_before_plan_approval(read_file):
    """Design runs the implementability and coverage gates BEFORE Plan approval, so the user approves
    an already-validated plan; the spec write comes last."""
    lower = read_file(_DESIGN).lower()
    i7 = lower.index("## step 7")
    i8 = lower.index("## step 8 — plan approval")
    i9 = lower.index("## step 9")
    assert i7 < i8 < i9, \
        "design order must be validation gates (Step 7) → Plan approval (Step 8) → write specs (Step 9)"
    assert i7 < lower.index("implementability check") < i8, \
        "the implementability check must sit in the Step 7 validation gates, before Plan approval"


def test_discover_persists_tier_only_at_the_output_step(read_file):
    """Discover's Step 3 confirms the tier but must not write machine state mid-plan-mode:
    plan mode blocks writes, and the session slug doesn't exist until Step 7 — an early write
    either fails or creates an orphan session keyed differently than Step 7's init. The tier
    is recorded in-conversation and persisted by the Step 7 session-init write."""
    md = read_file(_DISCOVER)
    step3 = md[md.index("## Step 3"):md.index("## Step 4")]
    assert "~/.hercules/state" not in step3, \
        "Step 3 must not write the state file — plan mode is active and no session slug exists yet"
    step7 = md[md.index("## Step 7"):]
    assert "tier" in step7 and "~/.hercules/" in step7, \
        "Step 7's session-init write must persist the Step 3 tier"


def test_build_closeout_points_to_ship_without_running_it(read_file):
    """Build's close-out hands control back: the user reviews the diff, then runs Ship —
    workflow.md gates the transition on 'move to Ship' and the README promises a review pause.
    An auto-run close-out contradicts both and bounces the user into a commit plan unasked."""
    md = read_file(_BUILD)
    closeout = md[md.lower().index("## close-out"):]
    assert not re.search(r"Then run `/hercules:ship`", closeout), \
        "close-out must point to Ship, never invoke it — the user reviews the diff first"
    assert "/hercules:ship" in closeout, "close-out must still point forward to Ship"
    assert "review" in closeout.lower() and "ready" in closeout.lower(), \
        "close-out must hand the user the review-then-ship decision"


def test_every_nonterminal_index_status_has_a_writer(repo_root):
    """CLAUDE.md's INDEX Status set depicts workflow-written values — each must actually be
    written by some command, or the INDEX silently lies for a whole phase (e.g. a multi-day
    Build whose row still says 'design'). 'abandoned' is user-manual."""
    commands = [p.read_text() for p in (repo_root / "dist" / "claude-code" / "commands").glob("*.md")]
    for status in ("discover", "design", "build", "delivered"):
        assert any(
            "INDEX.md" in para and f"`{status}`" in para
            for text in commands
            for para in text.split("\n\n")
        ), f"no command writes INDEX status `{status}` — CLAUDE.md documents it as a live value"


def test_lock_language_is_consistent_between_wrapper_and_phases(read_file):
    """discover.md/design.md declare the artifact locked at its save; workflow.md must not
    tell the user it locks later ('once we move to X') — that invites post-lock edit requests
    no command defines a path for. Changes after the save go through the sanctioned re-runs."""
    wf = read_file(_WORKFLOW)
    assert not re.search(r"once (?:we|you) move to \w+, the (?:requirements|specs) are locked", wf), \
        "workflow.md must not promise a later lock — artifacts lock at their phase's save"
    assert re.search(r"fresh Discover pass|through `/hercules:design`", wf), \
        "workflow.md must state the sanctioned change path after a phase's save"


def test_orchestrator_has_a_protocol_aligned_fallback_rule(read_file):
    """When something breaks mid-workflow, the orchestrator must fall back to the safest action
    consistent with the workflow protocol and tell the user — never improvise outside it."""
    md = read_file(_CLAUDE)
    assert "fall back to the safest action" in md and "never improvise" in md, \
        "CLAUDE.md must carry the protocol-aligned fallback rule"


def test_workflow_continues_phases_by_reading_files_not_skill_invocation(read_file):
    """Phase commands carry disable-model-invocation (auto-fire protection), so the model
    cannot load them as skills — the guided workflow must instruct continuing by READING
    each phase's command file, or an agent dead-ends into 'please type /hercules:design',
    breaking the automatic flow."""
    md = read_file(_WORKFLOW)
    assert "reading its file" in md or "read its file" in md, \
        "workflow must say phases continue by reading the command file inline"
    assert "same directory as this file" in md, \
        "…and locate the phase files generically (beside this file), not via a path variable"
    assert "${CLAUDE_PLUGIN_ROOT}" not in md and "${CLAUDE_SKILL_DIR}" not in md, \
        "the guided flow must not depend on a path variable substituting"
    assert "never ask the user to type" in md, \
        "the guided flow must not push invocation back onto the user"


def test_workflow_announces_every_phase_entry(read_file):
    """The user experiences transitions as 'Entering the {Phase} phase' announcements —
    they were never pinned, so a rewrite could silently drop them."""
    md = read_file(_WORKFLOW)
    for phase in ("Discover", "Design", "Build", "Ship"):
        assert f"Entering the **{phase}** phase" in md, \
            f"the {phase} entry announcement must survive"
