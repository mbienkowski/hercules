"""Delivery commands — Build session lifecycle: resume, reconcile, start-fresh, handoff, discovery."""

from __future__ import annotations

import pytest
from tests.conftest import (
    BUILD as _BUILD,
    SHIP as _SHIP,
    section as _section,
)


def test_build_offers_to_resume_a_project_from_saved_state(read_file):
    """When a project has saved state, Build's instructions must reference that state and offer
    to resume the previous work by spec, rather than pointing at the old, removed
    docs/.context file."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "resume" in lower, "build must offer resume from the home-config project state"
    assert "~/.hercules/" in lower and "state" in lower, \
        "build must reference ~/.hercules/ (config.json + per-project state file) for resume"
    assert "docs/.context" not in lower, "build must not reference the removed docs/.context file"

def test_build_records_which_spec_is_active_and_which_are_done(read_file):
    """Build must track which spec is currently being worked (current_spec) and which specs
    have already been delivered (delivered_specs) in the project's saved state, so progress
    survives across sessions."""
    md = read_file(_BUILD)
    assert "current_spec" in md, \
        "build must track the in-progress spec via current_spec in the home-config entry"
    assert "delivered_specs" in md, \
        "build must maintain delivered_specs array in the home-config entry"

def test_close_out_asks_whether_to_leave_a_handoff_note(read_file):
    """When a work session ends, Build's close-out step must actively ask whether to record a
    note for whoever picks up the work next -- simply showing an old note at the start of a
    session does not satisfy this, since that only helps if a note was already written."""
    md = read_file(_BUILD)
    closeout = md[md.index("## Close-out"):]
    assert "anyone taking over" in closeout.lower(), \
        "the close-out must ask the handoff question, not merely read old notes"

def test_project_registry_is_documented_as_rebuildable_not_authoritative(read_file):
    """The documentation must describe the project registry as a regenerable index that can
    always be rebuilt from the per-project state files, making clear that the state files --
    not the registry -- are the source of truth."""
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md")).lower()
    assert "regenerable index" in md, "CLAUDE.md must describe the registry as a regenerable index"
    assert "rebuilt from" in md or "source of truth" in md, \
        "CLAUDE.md must state the state files are the source of truth (registry rebuildable)"

def test_starting_fresh_removes_a_stale_frozen_file_override(read_file):
    """'Start fresh' resets which spec and round are active, but an override that was only
    meant to apply to the previous spec and round would otherwise be left behind and could
    still take effect -- starting fresh must explicitly clear it too."""
    md = read_file(_BUILD)
    fresh = md[md.index("On 'start fresh':"):md.index("On resume, reconcile")]
    assert "frozen_override" in fresh, "'start fresh' must clear frozen_override too"

def test_resuming_drops_frozen_file_records_for_files_that_no_longer_exist(read_file):
    """If a test file was marked frozen (protected from being edited) but no longer exists on
    disk, resuming a session must drop that record -- otherwise the protection meant to guard
    the file would instead permanently block recreating it, deadlocking the session."""
    md = read_file(_BUILD)
    reconcile = md[md.index("On resume, reconcile"):md.index("### Step 1")]
    assert "frozen_test_files" in reconcile, \
        "resume reconcile must drop frozen_test_files entries with no file on disk"

def test_resuming_does_not_delete_spec_files_the_project_chose_to_keep(read_file):
    """When a project is configured to keep delivered spec files on disk, resuming a session
    must not delete them, even though the normal cleanup step removes delivered spec files --
    otherwise every resume would erase specs the user deliberately chose to keep."""
    md = read_file(_BUILD)
    reconcile = md[md.index("On resume, reconcile"):md.index("### Step 1")]
    assert "git rm" in reconcile, "reconcile still finishes an interrupted delete by default"
    assert "keep_specs" in reconcile, \
        "reconcile must skip the git rm when keep_specs keeps delivered specs on disk"

def test_a_handoff_note_written_at_close_out_is_visible_to_the_next_session(read_file):
    """A handoff note recorded when one session closes out must be surfaced somewhere the next
    session (Ship) actually looks, not left in a place that only appears while a spec is
    still marked in progress."""
    ship = read_file(_SHIP)
    assert "handoff_note" in ship or "handed_off_by" in ship, \
        "a close-out handoff must be surfaced somewhere a successor actually looks"

def test_resuming_a_session_still_requires_plan_approval_first(read_file):
    """Resuming a previous session must still go through the plan-approval step before any
    changes are made -- skipping it would leave the session stuck in read-only planning mode,
    unable to make any edits."""
    build = read_file(_BUILD)
    resume = build[build.index("On 'start fresh':"):build.index("On resume, reconcile")]
    assert "Plan approval" in resume, \
        "resume must pass the Plan-approval gate (which calls ExitPlanMode) before executing"

def test_starting_fresh_clears_old_progress_checkpoints(read_file):
    """'Start fresh' abandons the prior attempt entirely, so it must also clear the saved
    progress checkpoints from that attempt -- otherwise leftover checkpoints would be
    mistaken for a real record of delivered work."""
    build = read_file(_BUILD)
    fresh = build[build.index("On 'start fresh':"):build.index("On resume, reconcile")]
    assert "build_progress" in fresh, "'start fresh' must clear build_progress too"

def test_starting_fresh_keeps_the_delivery_record_for_specs_the_project_kept(read_file):
    """When a project keeps delivered spec files on disk, 'start fresh' must not erase the
    record that those specs were already delivered, nor their saved progress checkpoints --
    otherwise Build would try to redeliver work that is already done."""
    build = read_file(_BUILD)
    fresh = _section(build, "On 'start fresh':", "On resume, reconcile", label=_BUILD)
    assert "keep_specs" in fresh, \
        "'start fresh' must keep delivered_specs when keep_specs retains the files"
    assert "checkpoint" in fresh, \
        "kept delivered specs must keep their build_progress checkpoints (the cross-check's record)"

def test_resuming_after_an_interrupted_finish_completes_it_instead_of_redoing_it(read_file):
    """If a session is interrupted right after a spec's delivery was checkpointed but before
    that was recorded as done, a naive resume would try to redeliver the same spec from
    scratch -- which can never succeed against code that's already in place. Resuming must
    instead recognize the checkpoint and finish marking the spec as delivered."""
    build = read_file(_BUILD)
    reconcile = build[build.index("On resume, reconcile"):build.index("### Step 1")]
    assert "build_progress" in reconcile and "step 10" in reconcile, \
        "reconcile must finish retire for a checkpointed spec still listed as pending"

def test_a_handoff_note_is_shown_even_when_no_spec_is_currently_in_progress(read_file):
    """A handoff note is saved at the same moment the in-progress spec is cleared, so display
    logic that only shows the note while a spec is in progress would never show it -- the
    note must always be surfaced when one exists, regardless of that state."""
    build = read_file(_BUILD)
    step0 = build[build.index("### Step 0"):build.index("### Step 1")]
    handoff_at = step0.index("handed_off_by")
    gate_at = step0.index("`current_spec` is set")
    assert handoff_at < gate_at, \
        "the handoff display must not hide behind the current_spec resume gate"

def test_resuming_rebuilds_the_project_registry_if_it_was_lost(read_file):
    """If the project's index file is lost while its state file survives -- for example from
    an interrupted write -- resuming must rebuild the index instead of reporting no sessions
    found, so a half-delivered feature doesn't appear to have vanished entirely."""
    reconcile = _section(read_file(_BUILD), "On resume, reconcile", "### Step 1", label=_BUILD)
    assert "rebuild" in reconcile and "registry" in reconcile

def test_starting_fresh_clears_every_field_needed_for_a_true_restart(read_file):
    """'Start fresh' must clear every piece of saved state tied to the abandoned attempt --
    missing even one field, such as the round counter or the frozen-file list, would let
    stale progress leak into the new attempt, either stopping it early or leaving old
    protections wrongly still active."""
    fresh = _section(read_file(_BUILD), "On 'start fresh':", "On resume, reconcile", label=_BUILD)
    for field in ("`current_spec`", "`current_spec_round`", "`frozen_test_files`",
                  "`frozen_override`", "`pending_specs`", "`build_progress`"):
        assert field in fresh, f"'start fresh' must clear {field}"
