"""The Copilot CLI write-gate adapter (G1) — ``src/targets/copilot-cli/hooks/hercules_gate.py``.

Copilot's ``preToolUse`` hook is a real pre-write veto, so the adapter reads the event, extracts the
target path, and asks the CANONICAL guard (``frozen_tests.decide`` + its ``frozen_override`` policy —
the SAME one Claude Code, OpenCode, and Cursor read) whether it is a frozen test under an active build.
A frozen hit returns ``permissionDecision: "deny"``; everything else allows. Reads (``view``) are never
blocked (the doctrine locks edits, not reads).

These drive the real adapter in-process against a throwaway ``~/.hercules`` state tree, asserting the
emitted Copilot decision JSON. Deny/allow strings are HARDCODED literals (never read from the adapter's
own constants) so a mutated primitive is actually caught; the canonical block wording is pinned too.
"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

from scripts.build.cli import build_target

REPO_ROOT = Path(__file__).resolve().parents[2]
COPILOT_HOOKS = REPO_ROOT / "src" / "targets" / "copilot-cli" / "hooks"
CLAUDE_HOOKS = REPO_ROOT / "src" / "targets" / "claude-code" / "hooks"


def _load_gate():
    """Import the adapter in-process; both shared modules (they live in the claude-code tree in source)
    must be on sys.path because the adapter does ``from frozen_tests import decide`` off its own dir."""
    import sys
    for d in (str(CLAUDE_HOOKS), str(COPILOT_HOOKS)):
        if d not in sys.path:
            sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("copilot_hercules_gate", COPILOT_HOOKS / "hercules_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load_gate()


def _write_state(home: Path, proj: Path, session: dict, project_extra: dict | None = None):
    (home / ".hercules" / "state").mkdir(parents=True, exist_ok=True)
    (home / ".hercules" / "config.json").write_text(json.dumps({"projects": {
        "p": {"directory": str(proj), "state_file": "p.json", **(project_extra or {})}}}), encoding="utf-8")
    (home / ".hercules" / "state" / "p.json").write_text(
        json.dumps({"active_session": "s1", "sessions": {"s1": session}}), encoding="utf-8")


@pytest.fixture
def active_build(tmp_path):
    """A throwaway ~/.hercules with one active build freezing ``tests/test_frozen.py``. Returns (home, proj)."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "build", "current_spec": "spec-1.md",
                              "current_spec_round": 1, "frozen_test_files": ["tests/test_frozen.py"]})
    return home, proj


def _decide(evt: dict, home: Path, capsys) -> dict:
    gate.main(["hercules_gate.py", "preToolUse"], stdin_text=json.dumps(evt), home=str(home))
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else {}


def _frozen_abs(proj: Path) -> str:
    return str(proj / "tests" / "test_frozen.py")


# ── deny: an edit to a frozen test is blocked before it lands ────────────────────────────────
@pytest.mark.parametrize("tool", ["create", "edit", "str_replace_editor", "apply_patch"])
def test_pretooluse_denies_an_edit_to_a_frozen_test(tool, active_build, capsys):
    home, proj = active_build
    d = _decide({"toolName": tool, "toolArgs": {"path": _frozen_abs(proj)}, "cwd": str(proj)}, home, capsys)
    assert d["permissionDecision"] == "deny", f"{tool} on a frozen test must be denied"


def test_deny_carries_the_canonical_block_reason_with_the_escape_hatch(active_build, capsys):
    home, proj = active_build
    d = _decide({"toolName": "edit", "toolArgs": {"path": _frozen_abs(proj)}, "cwd": str(proj)}, home, capsys)
    assert "is a frozen test for spec-1.md (build round 1/3)" in d["permissionDecisionReason"]
    assert 'saying "change this test' in d["permissionDecisionReason"], "escape hatch must be named"


def test_snake_case_payload_shape_is_also_honored(active_build, capsys):
    """The VS Code-compatible ``PreToolUse`` payload (tool_name/tool_input) denies identically."""
    home, proj = active_build
    d = _decide({"tool_name": "Edit", "tool_input": {"file_path": _frozen_abs(proj)}, "cwd": str(proj)}, home, capsys)
    assert d["permissionDecision"] == "deny"


def test_a_relative_path_is_resolved_against_the_event_cwd(active_build, capsys):
    home, proj = active_build
    d = _decide({"toolName": "edit", "toolArgs": {"file_path": "tests/test_frozen.py"}, "cwd": str(proj)}, home, capsys)
    assert d["permissionDecision"] == "deny"


def test_path_delivered_as_a_json_string_argument_is_parsed(active_build, capsys):
    """Copilot may hand ``tool_input`` as an unparsed JSON string — the adapter parses it and still denies."""
    home, proj = active_build
    d = _decide({"tool_name": "edit", "tool_input": json.dumps({"path": _frozen_abs(proj)}), "cwd": str(proj)}, home, capsys)
    assert d["permissionDecision"] == "deny"


def test_a_nested_edit_list_naming_the_frozen_test_is_denied(active_build, capsys):
    home, proj = active_build
    evt = {"toolName": "apply_patch", "toolArgs": {"edits": [{"file_path": _frozen_abs(proj)}]}, "cwd": str(proj)}
    assert _decide(evt, home, capsys)["permissionDecision"] == "deny"


# ── allow: reads, non-frozen edits, no build, unresolvable args ──────────────────────────────
def test_a_read_tool_on_a_frozen_test_is_allowed(active_build, capsys):
    """``view`` is not a write tool — reading a frozen test is allowed (the agent must read what it passes)."""
    home, proj = active_build
    d = _decide({"toolName": "view", "toolArgs": {"path": _frozen_abs(proj)}, "cwd": str(proj)}, home, capsys)
    assert d["permissionDecision"] == "allow"


def test_an_edit_to_an_unrelated_file_is_allowed(active_build, capsys):
    home, proj = active_build
    d = _decide({"toolName": "edit", "toolArgs": {"path": str(proj / "src" / "feature.py")}, "cwd": str(proj)}, home, capsys)
    assert d["permissionDecision"] == "allow"


def test_a_write_tool_with_no_resolvable_path_is_allowed(active_build, capsys):
    """No recognisable path key in the arguments → fail OPEN (allow), never a spurious block."""
    home, proj = active_build
    assert _decide({"toolName": "edit", "toolArgs": {"weird": 1}, "cwd": str(proj)}, home, capsys)["permissionDecision"] == "allow"


def test_a_non_json_string_argument_yields_allow(active_build, capsys):
    """``toolArgs`` that is a plain non-JSON string can't be parsed to a path → fail OPEN (allow)."""
    home, proj = active_build
    assert _decide({"toolName": "edit", "toolArgs": "just a sentence", "cwd": str(proj)}, home, capsys)["permissionDecision"] == "allow"


def test_a_json_string_that_is_not_an_object_yields_allow(active_build, capsys):
    """A JSON-string argument that decodes to a non-object (a list) carries no path key → allow."""
    home, proj = active_build
    assert _decide({"tool_name": "edit", "tool_input": "[1, 2, 3]", "cwd": str(proj)}, home, capsys)["permissionDecision"] == "allow"


def test_an_edit_list_whose_items_name_no_path_yields_allow(active_build, capsys):
    """A batched edit list whose entries carry no recognised path key resolves to nothing → allow."""
    home, proj = active_build
    evt = {"toolName": "apply_patch", "toolArgs": {"edits": [{"note": "x"}, {"note": "y"}]}, "cwd": str(proj)}
    assert _decide(evt, home, capsys)["permissionDecision"] == "allow"


def test_everything_is_allowed_when_no_build_is_active(tmp_path, capsys):
    home = tmp_path / "empty"
    home.mkdir()
    evt = {"toolName": "edit", "toolArgs": {"path": str(tmp_path / "tests" / "test_frozen.py")}, "cwd": str(tmp_path)}
    assert _decide(evt, home, capsys)["permissionDecision"] == "allow"


def test_the_frozen_override_lifts_the_gate(tmp_path, capsys):
    """A user-granted ``frozen_override`` covering the file allows the edit — the canonical policy, verbatim."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "build", "current_spec": "spec-1.md", "current_spec_round": 1,
                              "frozen_test_files": ["tests/test_frozen.py"],
                              "frozen_override": {"files": ["tests/test_frozen.py"], "spec": "spec-1.md",
                                                  "round": 1, "reason": "user: 'fix the expected status'"}})
    d = _decide({"toolName": "edit", "toolArgs": {"path": _frozen_abs(proj)}, "cwd": str(proj)}, home, capsys)
    assert d["permissionDecision"] == "allow"


# ── fail-open discipline ─────────────────────────────────────────────────────────────────────
def test_fails_open_on_malformed_stdin(tmp_path, capsys):
    """Garbage on stdin must still yield allow — a gate bug never bricks an edit."""
    home = tmp_path / "home"
    home.mkdir()
    gate.main(["hercules_gate.py", "preToolUse"], stdin_text="{not json", home=str(home))
    assert json.loads(capsys.readouterr().out.strip())["permissionDecision"] == "allow"


def test_empty_stdin_allows(tmp_path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    gate.main(["hercules_gate.py", "preToolUse"], stdin_text="", home=str(home))
    assert json.loads(capsys.readouterr().out.strip())["permissionDecision"] == "allow"


def test_reads_from_real_stdin_when_no_text_is_passed(active_build, capsys, monkeypatch):
    """With no ``stdin_text`` the adapter reads ``sys.stdin`` — a frozen edit there is still denied."""
    home, proj = active_build
    evt = {"toolName": "edit", "toolArgs": {"path": _frozen_abs(proj)}, "cwd": str(proj)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(evt)))
    gate.main(["hercules_gate.py", "preToolUse"], home=str(home))
    assert json.loads(capsys.readouterr().out.strip())["permissionDecision"] == "deny"


# ── the shipped gate carries the canonical guard files ───────────────────────────────────────
def test_copilot_ships_the_gate_and_canonical_guard_files(tmp_path):
    out = tmp_path / "copilot-cli"
    build_target("copilot-cli", out)
    for name in ("hercules_gate.py", "hooks.json", "hercules_state.py", "frozen_tests.py"):
        assert (out / "hooks" / name).is_file(), f"dist/copilot-cli/hooks/{name} must ship"
    for name in ("hercules_state.py", "frozen_tests.py"):
        assert (out / "hooks" / name).read_bytes() == (CLAUDE_HOOKS / name).read_bytes(), \
            f"{name} must not diverge across dists"


def test_hook_command_invokes_the_gate_by_plugin_root_path(tmp_path):
    """Lock the exact preToolUse wiring: the matcher covers Copilot's edit tools and the command invokes
    the adapter under ``$PLUGIN_ROOT`` (a plugin hook runs with cwd = project root, so the variable is how
    it locates its own bundled script). The ``|| exit 0`` / ``; exit 0`` guard keeps a missing python3
    fail-OPEN (Copilot fails a preToolUse hook CLOSED on a non-zero exit)."""
    out = tmp_path / "copilot-cli"
    build_target("copilot-cli", out)
    hooks = json.loads((out / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    entry = hooks["hooks"]["preToolUse"][0]
    assert entry["matcher"] == "create|edit|str_replace_editor|apply_patch"
    assert entry["bash"] == 'python3 "$PLUGIN_ROOT/hooks/hercules_gate.py" preToolUse || exit 0'
    assert entry["powershell"] == 'python3 "$env:PLUGIN_ROOT/hooks/hercules_gate.py" preToolUse; exit 0'
