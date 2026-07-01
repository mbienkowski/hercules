"""Behavioural tests for the G1 frozen-tests PreToolUse hook (plugin/hooks/frozen_tests.py).

These are *executable* guard tests (the hook actually runs), not prose-pins: a frozen-path
edit during a build must return exit code 2; everything else must return 0 and never raise.
The hook takes an explicit `home` so we point it at a throwaway ~/.hercules tree per test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parents[2] / "plugin" / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))
from frozen_tests import main  # noqa: E402


def _setup(home: Path, project: Path, *, phase="build", frozen=("tests/test_login.py",),
           repositories=None, slug="proj", create=True):
    """Write a registry + state tree under `home/.hercules` for one project/session."""
    hh = home / ".hercules"
    (hh / "state").mkdir(parents=True, exist_ok=True)
    entry = {"directory": str(project), "docs_root": "docs", "state_file": f"{slug}.json"}
    if repositories:
        entry["repositories"] = {k: str(v) for k, v in repositories.items()}
    (hh / "config.json").write_text(json.dumps({"schema_version": 1, "projects": {slug: entry}}))
    session = {
        "current_phase": phase,
        "current_spec": "spec-02-login.md",
        "current_spec_round": 1,
        "frozen_test_files": list(frozen),
    }
    (hh / "state" / f"{slug}.json").write_text(
        json.dumps({"schema_version": 1, "active_session": "s1", "sessions": {"s1": session}})
    )
    if create:
        for f in frozen:
            p = project / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("def test_x():\n    assert True\n")


def _payload(project: Path, rel_or_abs, tool="Edit", cwd=None):
    fp = str(rel_or_abs if Path(str(rel_or_abs)).is_absolute() else project / rel_or_abs)
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": fp},
        "cwd": str(cwd or project),
    })


def test_blocks_edit_to_frozen_test_during_build(tmp_path, capsys):
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    code = main(_payload(project, "tests/test_login.py"), home=tmp_path)
    assert code == 2
    err = capsys.readouterr().err
    assert "frozen test" in err and "start fresh" in err  # stderr names the sanctioned path


def test_allows_edit_to_non_frozen_file(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    assert main(_payload(project, "src/login.py"), home=tmp_path) == 0


def test_allows_when_phase_is_not_build(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project, phase="design")
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_allows_non_mutating_tool(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    assert main(_payload(project, "tests/test_login.py", tool="Read"), home=tmp_path) == 0


def test_blocks_multiedit_targeting_a_frozen_file(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    payload = json.dumps({
        "tool_name": "MultiEdit",
        "tool_input": {"edits": [
            {"file_path": str(project / "src/login.py")},
            {"file_path": str(project / "tests/test_login.py")},
        ]},
        "cwd": str(project),
    })
    assert main(payload, home=tmp_path) == 2


def test_multi_service_frozen_path_is_matched(tmp_path):
    """A frozen test living under a `repositories.*` path is caught even when cwd differs."""
    project = tmp_path / "home"
    svc = tmp_path / "svc-auth"
    _setup(tmp_path, project, frozen=("tests/test_token.py",), repositories={"svc-auth": svc})
    (svc / "tests").mkdir(parents=True, exist_ok=True)
    (svc / "tests/test_token.py").write_text("def test_t():\n    assert True\n")
    payload = _payload(svc, svc / "tests/test_token.py", cwd=svc)
    assert main(payload, home=tmp_path) == 2


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
