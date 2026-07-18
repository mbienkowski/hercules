"""Frozen-tests hook — fail-open resilience under malformed state and bad stdin."""

from __future__ import annotations

import json
import os
import sys

from tests.hooks.conftest import _HOOKS_DIR, FROZEN_TEST, _payload, _setup, build_project, main


def test_editing_is_allowed_when_no_hercules_state_exists(tmp_path):
    """If Hercules has never recorded any project state on this machine (no ~/.hercules
    directory at all), an edit request must simply be allowed rather than blocked or errored."""
    project = tmp_path / "proj"
    project.mkdir()
    # no ~/.hercules at all
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_guard_does_nothing_outside_a_hercules_project(tmp_path):
    """When Hercules is invoked from a directory that isn't a Hercules-managed project, the
    safety guard steps aside instead of blocking unrelated work."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    other = tmp_path / "elsewhere"
    other.mkdir()
    payload = _payload(other, other / "tests/test_login.py", cwd=other)
    assert main(payload, home=tmp_path) == 0


def test_corrupted_hercules_state_does_not_block_editing(tmp_path):
    """If the project's saved Hercules state on disk is corrupted or unparseable, the hook
    must not crash or block the edit -- a damaged local record should never itself become an
    outage that stops the user from working."""
    project = tmp_path / "proj"
    project.mkdir()
    hh = tmp_path / ".hercules"
    (hh / "state").mkdir(parents=True)
    (hh / "config.json").write_text("{ this is not json")
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_no_input_at_all_is_allowed(tmp_path):
    """If the hook receives an entirely empty request with no details about the edit, it must
    default to allowing the action rather than blocking on missing information."""
    assert main("", home=tmp_path) == 0


def test_unreadable_request_data_is_allowed_through(tmp_path):
    """If the incoming request describing the edit is not valid data the hook can understand,
    the edit is allowed rather than blocked -- a malformed request must never be treated as a
    reason to stop the user's work."""
    assert main("this is not json {", home=tmp_path) == 0


def test_an_internal_error_while_checking_frozen_files_still_allows_the_edit(tmp_path, monkeypatch):
    """Even for an edit that would normally be blocked because it touches a frozen test, an
    unexpected internal failure while checking which files are frozen must still result in the
    edit being allowed, with no error surfaced to the user."""
    # Given a frozen edit that would normally block, but a resolver that explodes
    import frozen_tests as ft

    def _boom(*_a, **_k):
        raise RuntimeError("resolver exploded")

    project = build_project(tmp_path)
    payload = json.loads(_payload(project, FROZEN_TEST))
    monkeypatch.setattr(ft, "resolve_build_contexts", _boom)
    # Then decide swallows the error and allows with no reason
    assert ft.decide(payload, home=tmp_path) == (0, "")


def test_garbled_input_never_crashes_or_blocks_the_users_work(tmp_path):
    """If the data Hercules receives is corrupted or unreadable, it must not crash or
    accidentally block the user's edit -- it fails safely and lets work continue."""
    import subprocess

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    env = {**os.environ, "HOME": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    run = subprocess.run(
        [sys.executable, str(_HOOKS_DIR / "frozen_tests.py")],
        input=b"\xff\xfe{bad", capture_output=True, env=env,
    )
    assert run.returncode == 0
    assert b"Traceback" not in run.stderr


def test_loading_the_hook_as_a_library_does_not_trigger_its_blocking_behavior(tmp_path):
    """Simply loading the frozen-tests hook code for reuse elsewhere must not itself run the
    check-and-block logic. If it did, any other tool that imports this hook would be aborted
    immediately instead of continuing to run normally."""
    import subprocess

    run = subprocess.run(
        [sys.executable, "-c", "import frozen_tests; print('IMPORT_OK')"],
        cwd=str(_HOOKS_DIR), input="", capture_output=True, text=True,
    )
    assert run.returncode == 0
    assert "IMPORT_OK" in run.stdout, "import must reach the end of the probe — no exit in between"
