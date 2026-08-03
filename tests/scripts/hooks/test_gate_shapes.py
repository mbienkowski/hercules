"""How a refusal reaches a tool, and where the file path sits in its request — the only two things
hosts differ on when they ask "may I write this file?". FLAT/NESTED/PATCH_AND_SHELL mirror shipped
shapes, so what is proven here is a real configuration rather than a synthetic one.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hercules_gate import main

ARG_KEYS = ["path", "file_path", "filePath"]

# A named-argument path and a top-level refusal: the shape copilot-cli declares.
FLAT = {
    "when": "before_write",
    "tools": {"edit": "Edit"},
    "paths": [{"from": "arg_keys", "keys": ARG_KEYS, "nested": ["edits"]}],
    "allow": {"permissionDecision": "allow"},
    "deny": {"permissionDecision": "deny"},
    "reason_at": ["permissionDecisionReason"],
}

# The same question, but this tool wraps its answer one level deeper — unique to this module.
NESTED = {
    **FLAT,
    "allow": {"hookSpecificOutput": {"permissionDecision": "allow"}},
    "deny": {"hookSpecificOutput": {"permissionDecision": "deny"}},
    "reason_at": ["hookSpecificOutput", "permissionDecisionReason"],
}

# This tool sends its edits as a patch body and runs shell commands — the shipped codex shape.
PATCH_AND_SHELL = {
    "when": "before_write",
    "tools": {"apply_patch": "Edit", "Bash": "Bash"},
    "paths": [
        {"from": "patch_body", "arg": "command",
         "pattern": r"^\*\*\* (?:Update|Add|Delete) File:\s*(.+?)\s*$", "as_tool": "Edit"},
        {"from": "shell_command", "arg": "command"},
    ],
    "allow": {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}},
    "deny": {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"}},
    "reason_at": ["hookSpecificOutput", "permissionDecisionReason"],
}

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGED_GATE = _REPO_ROOT / "dist" / "codex" / "hooks" / "hercules_gate.py"

@pytest.fixture()
def project(tmp_path: Path):
    """A project with one frozen test file, recorded in a machine-local state tree."""
    home = tmp_path / "home"
    proj = tmp_path / "project"
    frozen = proj / "tests" / "test_login.py"
    frozen.parent.mkdir(parents=True)
    frozen.write_text("def test_login():\n    assert True\n", encoding="utf-8")
    (home / ".hercules" / "state").mkdir(parents=True)
    (home / ".hercules" / "config.json").write_text(json.dumps({
        "schema_version": 1,
        "projects": {"proj": {"directory": str(proj), "state_file": "proj.json"}},
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
    return {"home": home, "dir": proj, "frozen": frozen}

def run(config, event, home) -> dict | None:
    """Run the gate over one event; returns what it printed, or None for silence."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert main(["hercules_gate.py"], stdin_text=json.dumps(event), home=home, config=config) == 0
    text = out.getvalue().strip()
    return json.loads(text) if text else None

def edit_event(project, path, tool="edit"):
    return {"tool_name": tool, "tool_input": {"file_path": str(path)}, "cwd": str(project["dir"])}

def test_the_flat_reply_shape_denies_a_frozen_write_and_allows_an_ordinary_one(project):
    ordinary = project["dir"] / "src" / "thing.py"
    ordinary.parent.mkdir(parents=True, exist_ok=True)
    ordinary.write_text("x = 1\n", encoding="utf-8")
    assert run(FLAT, edit_event(project, project["frozen"]), project["home"])["permissionDecision"] == "deny"
    assert run(FLAT, edit_event(project, ordinary), project["home"])["permissionDecision"] == "allow"

def test_a_write_to_a_frozen_test_is_refused_when_the_reply_wraps_a_level_deeper(project):
    out = run(NESTED, edit_event(project, project["frozen"]), project["home"])
    decision = out["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "frozen" in decision["permissionDecisionReason"].lower()

def test_apply_patch_denies_a_frozen_file_in_a_later_hunk(project):
    """A path inside a patch body is found even when it is not the first file the patch names."""
    patch = ("*** Begin Patch\n*** Update File: src/feature.py\n@@\n-x\n+y\n"
              f"*** Update File: {project['frozen'].relative_to(project['dir'])}\n@@\n-x\n+y\n"
              "*** End Patch\n")
    event = {"tool_name": "apply_patch", "tool_input": {"command": patch}, "cwd": str(project["dir"])}
    result = run(PATCH_AND_SHELL, event, project["home"])
    decision = result["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "frozen test" in decision["permissionDecisionReason"]

def test_a_patch_touching_nothing_frozen_is_allowed(project):
    event = {"tool_name": "apply_patch",
             "tool_input": {"command": "*** Begin Patch\n*** Update File: src/other.py\n"}, "cwd": str(project["dir"])}
    result = run(PATCH_AND_SHELL, event, project["home"])
    assert result["hookSpecificOutput"] == {"hookEventName": "PreToolUse", "permissionDecision": "allow"}

def test_a_shell_command_naming_a_frozen_file_is_denied(project):
    event = {"tool_name": "Bash", "tool_input": {"command": "rm tests/test_login.py"}, "cwd": str(project["dir"])}
    result = run(PATCH_AND_SHELL, event, project["home"])
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

@pytest.mark.parametrize("event_factory", [
    lambda p: {"tool_name": "edit", "tool_input": {"mystery": str(p["frozen"])}, "cwd": str(p["dir"])},
    lambda p: edit_event(p, p["frozen"], tool="some_other_tool"),
], ids=["no_path_the_gate_understands", "tool_not_covered_by_config"])
def test_a_request_the_configuration_cannot_place_a_frozen_path_in_is_allowed(project, event_factory):
    """A gate bug or an unknown tool must never brick unrelated work."""
    assert run(FLAT, event_factory(project), project["home"])["permissionDecision"] == "allow"

def test_the_packaged_codex_gate_denies_a_frozen_patch_file(project):
    """The shipped bytes, not just the in-process adapter: the on-disk command loads its own
    co-shipped configuration and honours an active Build freeze."""
    payload = {"tool_name": "apply_patch",
               "tool_input": {"command": "*** Begin Patch\n*** Add File: tests/test_login.py\n"},
               "cwd": str(project["dir"])}
    result = subprocess.run(
        [sys.executable, str(_PACKAGED_GATE), "codex_pre_tool"],
        input=json.dumps(payload), capture_output=True, text=True, cwd=project["dir"],
        env={**os.environ, "HOME": str(project["home"])}, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    decision = json.loads(result.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "frozen test" in decision["permissionDecisionReason"]
