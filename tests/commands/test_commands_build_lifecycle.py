"""Delivery commands — Build session lifecycle: resume, reconcile, start-fresh, handoff, discovery."""

from __future__ import annotations

import pytest
from tests.conftest import (
    BUILD as _BUILD,
    SHIP as _SHIP,
    section as _section,
)


def test_build_offers_resume_from_home_config(read_file):
    """Build (not all commands) must read the home-config project state and offer to resume by spec."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "resume" in lower, "build must offer resume from the home-config project state"
    assert "~/.hercules/" in lower and "state" in lower, \
        "build must reference ~/.hercules/ (config.json + per-project state file) for resume"
    assert "docs/.context" not in lower, "build must not reference the removed docs/.context file"

def test_context_tracks_spec_progress(read_file):
    """Build must track spec delivery progress via current_spec and delivered_specs in the
    project's home-config entry."""
    md = read_file(_BUILD)
    assert "current_spec" in md, \
        "build must track the in-progress spec via current_spec in the home-config entry"
    assert "delivered_specs" in md, \
        "build must maintain delivered_specs array in the home-config entry"

def test_build_offers_handoff_prompt(read_file):
    """Build's close-out must OFFER to record a handoff — pinned to the prompt sentence in
    the Close-out section; Step 0's read-side surfacing of handoff_note must not satisfy
    the write-side feature."""
    md = read_file(_BUILD)
    closeout = md[md.index("## Close-out"):]
    assert "anyone taking over" in closeout.lower(), \
        "the close-out must ask the handoff question, not merely read old notes"

def test_config_registry_is_rebuildable_from_state(read_file):
    """CLAUDE.md must document the registry as a regenerable index rebuilt from the state files."""
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md")).lower()
    assert "regenerable index" in md, "CLAUDE.md must describe the registry as a regenerable index"
    assert "rebuilt from" in md or "source of truth" in md, \
        "CLAUDE.md must state the state files are the source of truth (registry rebuildable)"

def test_start_fresh_clears_frozen_override(read_file):
    """'start fresh' resets spec+round to the values a stale grant was minted against, so the
    hook's spec+round expiry cannot catch it — the clear list must include frozen_override."""
    md = read_file(_BUILD)
    fresh = md[md.index("On 'start fresh':"):md.index("On resume, reconcile")]
    assert "frozen_override" in fresh, "'start fresh' must clear frozen_override too"

def test_resume_reconciles_frozen_test_files(read_file):
    """A recorded frozen file with nothing on disk deadlocks a resume (the hook fail-closes on
    non-existent frozen paths, blocking the Write that would recreate it) — Step 0's reconcile
    must drop such entries."""
    md = read_file(_BUILD)
    reconcile = md[md.index("On resume, reconcile"):md.index("### Step 1")]
    assert "frozen_test_files" in reconcile, \
        "resume reconcile must drop frozen_test_files entries with no file on disk"

def test_resume_reconcile_does_not_delete_kept_specs(read_file):
    """Under keep_specs: true delivered spec files stay on disk by design — Step 0's
    'delivered spec whose file still exists → git rm it now' reconcile would delete every
    kept spec on every resume. The clause must carry a keep_specs carve-out."""
    md = read_file(_BUILD)
    reconcile = md[md.index("On resume, reconcile"):md.index("### Step 1")]
    assert "git rm" in reconcile, "reconcile still finishes an interrupted delete by default"
    assert "keep_specs" in reconcile, \
        "reconcile must skip the git rm when keep_specs keeps delivered specs on disk"

def test_handoff_note_is_readable_after_close_out(read_file):
    """Close-out writes the handoff alongside current_spec: null, but Build Step 0 shows it only
    when current_spec IS set — Ship (the successor's next command) must surface it."""
    ship = read_file(_SHIP)
    assert "handoff_note" in ship or "handed_off_by" in ship, \
        "a close-out handoff must be surfaced somewhere a successor actually looks"

def test_build_resume_goes_through_plan_approval(read_file):
    """The resume path must still exit plan mode via the Plan-approval gate — jumping
    straight to execution leaves the agent in read-only plan mode with every Write
    refused."""
    build = read_file(_BUILD)
    resume = build[build.index("On 'start fresh':"):build.index("On resume, reconcile")]
    assert "Plan approval" in resume, \
        "resume must pass the Plan-approval gate (which calls ExitPlanMode) before executing"

def test_start_fresh_clears_build_progress(read_file):
    """'start fresh' abandons the prior attempt; stale build_progress checkpoints would
    poison the cross-check, which reads them as the durable delivery record."""
    build = read_file(_BUILD)
    fresh = build[build.index("On 'start fresh':"):build.index("On resume, reconcile")]
    assert "build_progress" in fresh, "'start fresh' must clear build_progress too"

def test_start_fresh_keeps_delivered_specs_under_keep_specs(read_file):
    """With keep_specs the delivered files remain on disk; clearing delivered_specs on
    'start fresh' would make Build re-deliver already-shipped specs — and the cross-check
    reads delivered specs' build_progress checkpoints, so those must survive with them."""
    build = read_file(_BUILD)
    fresh = _section(build, "On 'start fresh':", "On resume, reconcile", label=_BUILD)
    assert "keep_specs" in fresh, \
        "'start fresh' must keep delivered_specs when keep_specs retains the files"
    assert "checkpoint" in fresh, \
        "kept delivered specs must keep their build_progress checkpoints (the cross-check's record)"

def test_reconcile_finishes_an_interrupted_retire(read_file):
    """Interruption after step 9 (checkpoint written) but before step 10's state write
    leaves a delivered spec in pending_specs; a naive resume re-runs the whole cycle and
    step 3's must-fail gate can never pass against existing code. The reconcile must
    detect the checkpoint and finish step 10's state updates instead."""
    build = read_file(_BUILD)
    reconcile = build[build.index("On resume, reconcile"):build.index("### Step 1")]
    assert "build_progress" in reconcile and "step 10" in reconcile, \
        "reconcile must finish retire for a checkpointed spec still listed as pending"

def test_step0_surfaces_handoff_for_closed_out_sessions(read_file):
    """Close-out writes the handoff together with current_spec: null — a Step 0 display
    gated on current_spec being set can never show it. The handoff must be surfaced
    whenever present."""
    build = read_file(_BUILD)
    step0 = build[build.index("### Step 0"):build.index("### Step 1")]
    handoff_at = step0.index("handed_off_by")
    gate_at = step0.index("`current_spec` is set")
    assert handoff_at < gate_at, \
        "the handoff display must not hide behind the current_spec resume gate"

def test_build_reconcile_rebuilds_missing_registry(read_file):
    """A torn two-file write (registry lost, state intact) must not strand a
    half-delivered feature behind 'no sessions found'."""
    reconcile = _section(read_file(_BUILD), "On resume, reconcile", "### Step 1", label=_BUILD)
    assert "rebuild" in reconcile and "registry" in reconcile

def test_start_fresh_clear_list_is_complete(read_file):
    """Dropping current_spec_round from the clear list inherits round 3 (instant stop);
    dropping frozen_test_files keeps the hook armed on abandoned tests."""
    fresh = _section(read_file(_BUILD), "On 'start fresh':", "On resume, reconcile", label=_BUILD)
    for field in ("`current_spec`", "`current_spec_round`", "`frozen_test_files`",
                  "`frozen_override`", "`pending_specs`", "`build_progress`"):
        assert field in fresh, f"'start fresh' must clear {field}"
