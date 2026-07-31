"""Codex's native PreToolUse adapter.

The Codex hook receives an ``apply_patch`` payload containing the patch text in
``tool_input.command`` and must return the nested ``hookSpecificOutput`` envelope.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from hercules_gate import main


CONFIG = {
    "protocol": "codex_pre_tool",
    "tools": {"apply_patch": "Edit", "Bash": "Bash"},
    "path_keys": ["path"],
    "nested_keys": [],
    "allow": {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}},
    "deny": {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"}},
    "reason_key": "permissionDecisionReason",
}

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGED_GATE = _REPO_ROOT / "dist" / "codex" / "hooks" / "hercules_gate.py"


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    project = tmp_path / "project"
    frozen = project / "tests" / "test_login.py"
    frozen.parent.mkdir(parents=True)
    frozen.write_text("def test_login():\n    assert True\n", encoding="utf-8")
    (home / ".hercules" / "state").mkdir(parents=True)
    (home / ".hercules" / "config.json").write_text(json.dumps({
        "schema_version": 1,
        "projects": {"proj": {"directory": str(project), "state_file": "proj.json"}},
    }), encoding="utf-8")
    (home / ".hercules" / "state" / "proj.json").write_text(json.dumps({
        "schema_version": 1,
        "active_session": "s1",
        "sessions": {"s1": {
            "current_phase": "build",
            "current_spec": "spec-02-login.md",
            "current_spec_round": 1,
            "frozen_test_files": ["tests/test_login.py"],
        }},
    }), encoding="utf-8")
    return home, project


def _run(home: Path, project: Path, tool: str, command: str) -> dict:
    payload = {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(project)}
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert main(["hercules_gate.py", "codex_pre_tool"],
                    stdin_text=json.dumps(payload), home=home, config=CONFIG) == 0
    return json.loads(out.getvalue())


def test_apply_patch_denies_a_frozen_file_in_a_later_hunk(tmp_path: Path):
    home, project = _setup(tmp_path)
    patch = ("*** Begin Patch\n"
             "*** Update File: src/feature.py\n@@\n-x\n+y\n"
             "*** Update File: tests/test_login.py\n@@\n-x\n+y\n"
             "*** End Patch\n")
    result = _run(home, project, "apply_patch", patch)
    decision = result["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "frozen test" in decision["permissionDecisionReason"]


def test_bash_write_denies_a_frozen_file(tmp_path: Path):
    home, project = _setup(tmp_path)
    result = _run(home, project, "Bash", "rm tests/test_login.py")
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_non_frozen_patch_is_allowed(tmp_path: Path):
    home, project = _setup(tmp_path)
    result = _run(home, project, "apply_patch", "*** Begin Patch\n*** Update File: src/feature.py\n")
    assert result["hookSpecificOutput"] == {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
    }


@pytest.mark.parametrize("operation", ("Add", "Delete"))
def test_packaged_hook_denies_a_frozen_patch_file(tmp_path: Path, operation: str):
    """The emitted command must load its co-shipped config and honour an active Build freeze."""
    home, project = _setup(tmp_path)
    payload = {
        "tool_name": "apply_patch",
        "tool_input": {"command": f"*** Begin Patch\n*** {operation} File: tests/test_login.py\n"},
        "cwd": str(project),
    }
    result = subprocess.run(
        [sys.executable, str(_PACKAGED_GATE), "codex_pre_tool"],
        input=json.dumps(payload), capture_output=True, text=True, cwd=project,
        env={**os.environ, "HOME": str(home)}, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    decision = json.loads(result.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "frozen test" in decision["permissionDecisionReason"]
