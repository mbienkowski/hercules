"""Frozen-tests hook — core allow/block decisions and the block-message contract."""

from __future__ import annotations

import json
import os
import sys
import pytest

from tests.hooks.conftest import _HOOKS_DIR, FROZEN_TEST, SPEC, _grant, _payload, _setup, build_project, main, run_hook


def _allow_case_non_mutating_tool(tmp_path, project):
    _setup(tmp_path, project)
    return _payload(project, FROZEN_TEST, tool="Read")


def _allow_case_non_frozen_target(tmp_path, project):
    _setup(tmp_path, project)
    return _payload(project, "src/login.py")


def _allow_case_phase_not_build(tmp_path, project):
    _setup(tmp_path, project, phase="design")
    return _payload(project, FROZEN_TEST)


def _allow_case_empty_frozen_list(tmp_path, project):
    _setup(tmp_path, project, frozen=())
    return _payload(project, FROZEN_TEST)


def _allow_case_live_override_grant(tmp_path, project):
    _setup(tmp_path, project)
    _grant(tmp_path, files=[FROZEN_TEST])
    return _payload(project, FROZEN_TEST)


def _allow_case_project_opt_out(tmp_path, project):
    _setup(tmp_path, project)
    cfg_path = tmp_path / ".hercules" / "config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["projects"]["proj"]["frozen_hook"] = "off"
    cfg_path.write_text(json.dumps(cfg))
    return _payload(project, FROZEN_TEST)


def test_blocked_edit_message_tells_user_exactly_how_to_proceed(tmp_path, capsys):
    """When an edit to a frozen test is blocked, the message shown to the user must clearly say
    who blocked it, which spec is involved, the plain-language way a person can unblock it, the
    separate path for an agent's recorded override, and the per-project opt-out -- and it must
    never blur the safe 'fix the test' option together with the destructive 'start over' reset."""
    # Given a frozen test edited mid-Build
    project = build_project(tmp_path)
    # When the hook blocks the write
    assert run_hook(project, FROZEN_TEST, home=tmp_path) == 2
    reason = capsys.readouterr().err
    # Then the stderr message — the model's only feedback channel — carries the contract users and
    # the agent rely on: who blocked, which spec, the human's plain-sentence exit, the agent's
    # recorded-grant path, and the project opt-out. (Not every clause verbatim — that was bloat.)
    assert reason.startswith("Hercules: ")             # who blocked
    assert SPEC in reason                              # which spec
    assert 'User: saying "change this test' in reason  # the human's one plain sentence, first
    assert "frozen_override" in reason                 # the agent's recorded-grant path
    assert 'frozen_hook: "off"' in reason              # the per-project opt-out
    # …and it never fuses or invents a destructive exit (both settled deliberately):
    assert "start fresh" not in reason, \
        "'start fresh' is a destructive resume-time reset, not a routine unblock"
    assert 'correct the test" to re-enter' not in reason, \
        "correct-the-test (stay in Build) must not be fused with the design re-entry exit"


def test_editing_a_frozen_test_through_a_multi_part_change_is_blocked(tmp_path):
    """A single change that bundles several edits together, all aimed at one frozen test file,
    is still recognized and stopped -- so a frozen test can't be changed piecemeal by bundling
    edits instead of making one."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    payload = json.dumps({
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": str(project / "tests/test_login.py"),
            "edits": [{"old_string": "assert True", "new_string": "assert 1"}],
        },
        "cwd": str(project),
    })
    assert main(payload, home=tmp_path) == 2


def test_editing_a_frozen_notebook_is_blocked(tmp_path):
    """A notebook file that has been frozen as a test gets the same protection as a frozen
    script -- an attempt to edit it is stopped rather than silently allowed."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_flow.ipynb",))
    payload = json.dumps({
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": str(project / "tests/test_flow.ipynb")},
        "cwd": str(project),
    })
    assert main(payload, home=tmp_path) == 2


def test_overwriting_a_frozen_file_entirely_is_blocked(tmp_path):
    """A frozen test can be replaced wholesale, not just partially edited -- this scenario
    confirms a full-file rewrite of a frozen test is stopped exactly like a smaller edit would
    be, so a wholesale overwrite can't be used to sneak around the protection."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    assert main(_payload(project, "tests/test_login.py", tool="Write"), home=tmp_path) == 2


def test_editing_a_frozen_test_is_blocked_even_without_a_shared_file_location(tmp_path):
    """Some edit requests list the target location separately for each individual change instead
    of once for the whole request. This scenario confirms a frozen test is still recognized and
    the edit is still blocked in that case."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    payload = json.dumps({
        "tool_name": "MultiEdit",
        "tool_input": {"edits": [{"file_path": str(project / "tests/test_login.py")}]},
        "cwd": str(project),
    })
    assert main(payload, home=tmp_path) == 2


def test_block_message_stays_readable_when_spec_details_are_missing(tmp_path, capsys):
    """If the current session has no recorded spec name or round number, the block message still
    reads cleanly -- it names 'the current spec' and shows round 1 -- instead of showing a
    broken placeholder like '?/3' that would look like a bug to the person seeing it."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    session = state["sessions"]["s1"]
    del session["current_spec"], session["current_spec_round"]
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2
    err = capsys.readouterr().err
    # Boundary-anchored: the fallback must sit exactly where the spec name would ("for {spec} (")
    assert "is a frozen test for the current spec (build round 1/3)" in err


@pytest.mark.parametrize("make_payload", [
    _allow_case_non_mutating_tool,
    _allow_case_non_frozen_target,
    _allow_case_phase_not_build,
    _allow_case_empty_frozen_list,
    _allow_case_live_override_grant,
    _allow_case_project_opt_out,
], ids=lambda f: f.__name__.removeprefix("_allow_case_"))
def test_every_situation_that_permits_the_edit_gives_no_leftover_block_reason(tmp_path, make_payload):
    """Across every scenario where the edit is expected to go through -- an unrelated tool, a
    file that isn't frozen, a phase other than Build, no frozen tests configured, an agent's
    recorded override, or a project opt-out -- the edit is allowed with no stray block reason
    attached that a future caller could mistakenly print."""
    # Given one of the ways the hook lets a write through
    import frozen_tests as ft
    project = tmp_path / "proj"
    payload = json.loads(make_payload(tmp_path, project))
    # Then decide allows it with EXACTLY (0, "") — an allow never carries a stray reason a
    # future caller could print
    assert ft.decide(payload, home=tmp_path) == (0, "")


def test_any_frozen_file_in_a_list_triggers_a_block(tmp_path):
    """When several test files are frozen, editing any one of them blocks the edit, not just the
    last one checked -- a bug that only checked the last entry would let every other frozen file
    be edited freely."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_a.py", "tests/test_b.py"))
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 2


def test_the_guard_works_when_run_as_the_real_deployed_program(tmp_path):
    """Running the guard exactly the way Hercules deploys it -- as a standalone program fed the
    real tool-use request and pointed at the project's saved state -- still blocks edits to
    frozen tests and allows edits to everything else."""
    import subprocess

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    script = _HOOKS_DIR / "frozen_tests.py"
    env = {**os.environ, "HOME": str(tmp_path)}
    blocked = subprocess.run(
        [sys.executable, str(script)], input=_payload(project, "tests/test_login.py"),
        capture_output=True, text=True, env=env,
    )
    assert blocked.returncode == 2 and "Hercules:" in blocked.stderr
    allowed = subprocess.run(
        [sys.executable, str(script)], input=_payload(project, "src/login.py"),
        capture_output=True, text=True, env=env,
    )
    assert allowed.returncode == 0


def test_guard_still_blocks_a_frozen_edit_even_when_a_conflicting_helper_could_shadow_it(tmp_path, fresh_hook_over_decoy_state):
    """If another, unrelated piece of code with the same internal name could be picked up first,
    the guard must still use its own correct logic for finding the project's saved state -- not
    the wrong one -- so a frozen test's edit is still blocked rather than silently let through."""
    project = build_project(tmp_path)
    assert fresh_hook_over_decoy_state.main(_payload(project, FROZEN_TEST), home=tmp_path) == 2, \
        "the hook resolved the decoy hercules_state instead of its own"


def test_block_message_shows_the_true_current_round_number(tmp_path, capsys):
    """The build round shown in a block message must match the session's actual recorded round
    -- if it silently defaulted to round 1 instead, the user would misjudge how close they are
    to the round limit."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    state["sessions"]["s1"]["current_spec_round"] = 2
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2
    assert "(build round 2/3)" in capsys.readouterr().err
