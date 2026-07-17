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


def test_block_message_names_blocker_spec_and_both_exits(tmp_path, capsys):
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


def test_blocks_real_multiedit_shape_on_frozen_file(tmp_path):
    """Real MultiEdit carries ONE top-level file_path shared by all edits."""
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


def test_blocks_notebook_edit_to_a_frozen_notebook(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_flow.ipynb",))
    payload = json.dumps({
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": str(project / "tests/test_flow.ipynb")},
        "cwd": str(project),
    })
    assert main(payload, home=tmp_path) == 2


def test_blocks_write_tool_on_frozen_file(tmp_path):
    """Write can clobber a frozen test wholesale — it must be guarded like Edit."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    assert main(_payload(project, "tests/test_login.py", tool="Write"), home=tmp_path) == 2


def test_blocks_per_edit_file_path_shape(tmp_path):
    """The defensive per-edit `edits[].file_path` shape (no top-level file_path) is honoured."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    payload = json.dumps({
        "tool_name": "MultiEdit",
        "tool_input": {"edits": [{"file_path": str(project / "tests/test_login.py")}]},
        "cwd": str(project),
    })
    assert main(payload, home=tmp_path) == 2


def test_reason_falls_back_when_spec_fields_missing(tmp_path, capsys):
    """A build session without current_spec/current_spec_round still blocks, with readable
    fallbacks in the reason ('the current spec'; the round displays as 1 — a literal '?/3'
    in a red error box screenshots as a bug)."""
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
def test_every_allow_path_returns_no_reason(tmp_path, make_payload):
    # Given one of the ways the hook lets a write through
    import frozen_tests as ft
    project = tmp_path / "proj"
    payload = json.loads(make_payload(tmp_path, project))
    # Then decide allows it with EXACTLY (0, "") — an allow never carries a stray reason a
    # future caller could print
    assert ft.decide(payload, home=tmp_path) == (0, "")


def test_blocks_first_of_multiple_frozen_files(tmp_path):
    """Frozen candidates accumulate across ALL entries — a match on any earlier entry blocks
    (a last-entry-wins bug would let every other frozen file through)."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_a.py", "tests/test_b.py"))
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 2


def test_hook_runs_as_a_script_end_to_end(tmp_path):
    """The real deployment shape: `python3 frozen_tests.py` with a PreToolUse payload on stdin
    and HOME pointing at the state tree — frozen edit exits 2, non-frozen exits 0."""
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


def test_hook_imports_its_own_state_resolver_first(tmp_path, fresh_hook_over_decoy_state):
    """frozen_tests.py must front-load its OWN directory on sys.path — a same-named hercules_state
    earlier on the path must never shadow the real resolver (so a frozen edit still blocks)."""
    project = build_project(tmp_path)
    assert fresh_hook_over_decoy_state.main(_payload(project, FROZEN_TEST), home=tmp_path) == 2, \
        "the hook resolved the decoy hercules_state instead of its own"


def test_reason_displays_the_actual_round(tmp_path, capsys):
    """The round in the block reason must be the session's real counter — a lookup that
    silently falls back to 1 misinforms the user about how close the round limit is."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    state["sessions"]["s1"]["current_spec_round"] = 2
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2
    assert "(build round 2/3)" in capsys.readouterr().err
