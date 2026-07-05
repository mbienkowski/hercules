"""Frozen-tests hook — fail-open resilience under malformed state and bad stdin."""

from __future__ import annotations

import json
import os
import sys

from tests.hooks.conftest import _HOOKS_DIR, FROZEN_TEST, _payload, _setup, build_project, main


def test_fails_open_when_no_state(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    # no ~/.hercules at all
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_fails_open_on_unrelated_cwd(tmp_path):
    """Dogfooding / unrelated repo: cwd matches no project → pure passthrough."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    other = tmp_path / "elsewhere"
    other.mkdir()
    payload = _payload(other, other / "tests/test_login.py", cwd=other)
    assert main(payload, home=tmp_path) == 0


def test_never_crashes_on_malformed_state(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    hh = tmp_path / ".hercules"
    (hh / "state").mkdir(parents=True)
    (hh / "config.json").write_text("{ this is not json")
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_empty_stdin_allows(tmp_path):
    assert main("", home=tmp_path) == 0


def test_main_fails_open_on_malformed_stdin(tmp_path):
    assert main("this is not json {", home=tmp_path) == 0


def test_a_resolver_exception_also_allows_with_no_reason(tmp_path, monkeypatch):
    """The fail-open path is a (0, "") allow too — kept separate because it must monkeypatch the
    resolver to make it raise."""
    # Given a frozen edit that would normally block, but a resolver that explodes
    import frozen_tests as ft

    def _boom(*_a, **_k):
        raise RuntimeError("resolver exploded")

    project = build_project(tmp_path)
    payload = json.loads(_payload(project, FROZEN_TEST))
    monkeypatch.setattr(ft, "resolve_build_contexts", _boom)
    # Then decide swallows the error and allows with no reason
    assert ft.decide(payload, home=tmp_path) == (0, "")


def test_whitespace_stdin_is_never_parsed_as_json(tmp_path, monkeypatch):
    """Blank stdin short-circuits before json.loads — the parser must not see whitespace."""
    import frozen_tests as ft

    calls = []

    def _spy(raw):
        calls.append(raw)
        raise ValueError("should not be reached")

    monkeypatch.setattr(ft.json, "loads", _spy)
    assert ft.main("   \n", home=tmp_path) == 0
    assert calls == [], "whitespace-only stdin must never reach json.loads"


def test_decide_fails_open_if_resolver_raises(tmp_path, monkeypatch):
    """Last-resort guard: even if the resolver blows up, never block a user's edit."""
    import frozen_tests as ft

    def _boom(*_a, **_k):
        raise RuntimeError("resolver exploded")

    monkeypatch.setattr(ft, "resolve_build_contexts", _boom)
    payload = json.dumps({
        "tool_name": "Edit",
        "tool_input": {"file_path": "/x/tests/test_login.py"},
        "cwd": "/x",
    })
    assert ft.main(payload, home=tmp_path) == 0


def test_undecodable_stdin_fails_open_without_a_traceback(tmp_path):
    """Invalid UTF-8 on stdin must exit 0 with no traceback — 'never raises' includes the read."""
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


def test_importing_the_hook_module_has_no_side_effects(tmp_path):
    """Importing frozen_tests must never run main() — the __main__ guard is load-bearing:
    a module-level sys.exit would abort any tool that imports the hook for reuse."""
    import subprocess

    run = subprocess.run(
        [sys.executable, "-c", "import frozen_tests; print('IMPORT_OK')"],
        cwd=str(_HOOKS_DIR), input="", capture_output=True, text=True,
    )
    assert run.returncode == 0
    assert "IMPORT_OK" in run.stdout, "import must reach the end of the probe — no exit in between"
