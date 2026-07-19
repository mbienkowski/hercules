"""The Cursor write-gate adapter (G1) — ``src/targets/cursor/hooks/hercules_gate.py``.

Cursor has no pre-file-edit veto, so the adapter enforces what Cursor's hooks CAN, all keyed off the
SAME frozen-test state Claude Code and OpenCode read (``hercules_state``):

- ``shell`` (``beforeShellExecution``): DENY a command that writes/commits a frozen test during a build.
- ``read`` (``beforeReadFile``): DENY reads of a frozen test during a build.
- ``after_edit`` (``afterFileEdit``): notification-only — REVERT a frozen edit after the fact.

These drive the real adapter in-process (its ``main``/``decide`` on a synthetic Cursor event) against a
throwaway ``~/.hercules`` state tree, asserting the emitted Cursor decision JSON. The build fixtures
prove the SHIPPED gate is byte-identical to source and shares one ``hercules_state`` with the others.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.build.cli import build_target

REPO_ROOT = Path(__file__).resolve().parents[2]
CURSOR_HOOKS = REPO_ROOT / "src" / "targets" / "cursor" / "hooks"
CLAUDE_HOOKS = REPO_ROOT / "src" / "targets" / "claude-code" / "hooks"


def _load_gate():
    """Import the adapter in-process. It does ``from hercules_state import …`` off its own dir, so the
    shared state module (which lives in the claude-code tree in source) must be reachable on sys.path."""
    import sys
    for d in (str(CLAUDE_HOOKS), str(CURSOR_HOOKS)):
        if d not in sys.path:
            sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("hercules_gate", CURSOR_HOOKS / "hercules_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load_gate()


@pytest.fixture
def active_build(tmp_path):
    """A throwaway ~/.hercules with one active build session freezing ``tests/test_frozen.py`` under a
    project rooted at *proj*. Returns ``(home, proj)``."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    (home / ".hercules" / "state").mkdir(parents=True)
    (home / ".hercules" / "config.json").write_text(
        json.dumps({"projects": {"p": {"directory": str(proj), "state_file": "p.json"}}}), encoding="utf-8")
    (home / ".hercules" / "state" / "p.json").write_text(
        json.dumps({"active_session": "s1", "sessions": {
            "s1": {"current_phase": "build", "frozen_test_files": ["tests/test_frozen.py"]}}}), encoding="utf-8")
    return home, proj


def _decide(mode: str, evt: dict, home: Path, capsys) -> dict:
    """Run the adapter's ``main`` for *mode*/*evt* and return the parsed Cursor decision (or {} if the
    adapter emitted nothing — the after_edit-on-clean case)."""
    gate.main(["hercules_gate.py", mode], stdin_text=json.dumps(evt), home=str(home))
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else {}


# ── shell (beforeShellExecution) — the real hard block on the shell write-path ──────────────
def test_shell_denies_a_write_to_a_frozen_test_during_a_build(active_build, capsys):
    home, proj = active_build
    evt = {"command": "git add tests/test_frozen.py", "workspace_roots": [str(proj)]}
    d = _decide("shell", evt, home, capsys)
    assert d["permission"] == "deny"
    assert "frozen" in (d.get("agentMessage", "") + d.get("userMessage", "")).lower()


def test_shell_allows_a_read_only_command_touching_a_frozen_test(active_build, capsys):
    """The path is named but no write primitive is present — inspecting a frozen test is fine."""
    home, proj = active_build
    evt = {"command": "cat tests/test_frozen.py", "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_shell_allows_a_write_to_an_unrelated_file(active_build, capsys):
    home, proj = active_build
    evt = {"command": "git add src/feature.py", "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_shell_allows_everything_when_no_build_is_active(tmp_path, capsys):
    """No config/state at all → the frozen set is empty → the gate must never interfere."""
    home = tmp_path / "empty-home"
    home.mkdir()
    evt = {"command": "git add tests/test_frozen.py", "workspace_roots": [str(tmp_path)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def _write_state(home: Path, proj: Path, session: dict, project_extra: dict | None = None):
    (home / ".hercules" / "state").mkdir(parents=True, exist_ok=True)
    (home / ".hercules" / "config.json").write_text(json.dumps({"projects": {
        "p": {"directory": str(proj), "state_file": "p.json", **(project_extra or {})}}}), encoding="utf-8")
    (home / ".hercules" / "state" / "p.json").write_text(
        json.dumps({"active_session": "s1", "sessions": {"s1": session}}), encoding="utf-8")


def test_shell_ignores_a_frozen_file_when_the_phase_is_not_build(tmp_path, capsys):
    """The freeze only bites during ``build`` — the same file in ``design`` is fair game."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "design", "frozen_test_files": ["tests/test_frozen.py"]})
    evt = {"command": "git add tests/test_frozen.py", "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_shell_respects_the_frozen_hook_off_opt_out(tmp_path, capsys):
    """A project that sets ``frozen_hook: off`` disables the guard even mid-build."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "build", "frozen_test_files": ["tests/test_frozen.py"]},
                 project_extra={"frozen_hook": "off"})
    evt = {"command": "git add tests/test_frozen.py", "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


@pytest.mark.parametrize("primitive", gate._WRITE_PRIMITIVES)
def test_shell_denies_every_write_primitive_that_touches_a_frozen_test(primitive, active_build, capsys):
    """Each write/commit primitive the gate guards must deny when it targets a frozen test — read
    from the gate's own tuple so this test can never fall out of sync with the guarded set."""
    home, proj = active_build
    evt = {"command": f"{primitive.strip()} tests/test_frozen.py", "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "deny", \
        f"a {primitive!r} command on a frozen test must be denied"


def test_shell_resolves_cwd_from_the_event_when_no_workspace_roots(active_build, capsys):
    """With no ``workspace_roots`` the gate falls back to the event ``cwd`` — the freeze must still
    bite, so the fallback resolves the same build context."""
    home, proj = active_build
    evt = {"command": "git add tests/test_frozen.py", "cwd": str(proj)}
    assert _decide("shell", evt, home, capsys)["permission"] == "deny"


def test_read_fails_open_on_malformed_event(tmp_path, capsys):
    """Garbage on stdin for a read decision must also allow — fail-open covers read, not just shell."""
    home = tmp_path / "home"
    home.mkdir()
    gate.main(["hercules_gate.py", "read"], stdin_text="{not json", home=str(home))
    assert json.loads(capsys.readouterr().out.strip())["permission"] == "allow"


def test_after_edit_is_silent_when_no_build_is_active(tmp_path, capsys):
    """No active build → empty frozen set → after_edit emits nothing (it neither allows nor reverts)."""
    home = tmp_path / "empty"
    home.mkdir()
    evt = {"file_path": str(tmp_path / "tests" / "test_frozen.py"), "workspace_roots": [str(tmp_path)]}
    assert _decide("after_edit", evt, home, capsys) == {}


# ── read (beforeReadFile) ───────────────────────────────────────────────────────────────────
def test_read_denies_a_frozen_test_during_a_build(active_build, capsys):
    home, proj = active_build
    evt = {"file_path": str(proj / "tests" / "test_frozen.py"), "workspace_roots": [str(proj)]}
    assert _decide("read", evt, home, capsys)["permission"] == "deny"


def test_read_allows_a_non_frozen_file(active_build, capsys):
    home, proj = active_build
    evt = {"file_path": str(proj / "src" / "feature.py"), "workspace_roots": [str(proj)]}
    assert _decide("read", evt, home, capsys)["permission"] == "allow"


# ── after_edit (afterFileEdit) — notification-only, so revert as a backstop ──────────────────
def test_after_edit_reverts_a_frozen_test_edit(active_build, capsys):
    """afterFileEdit cannot veto, so the adapter must ``git checkout`` the frozen file back and warn."""
    home, proj = active_build
    frozen = proj / "tests" / "test_frozen.py"
    frozen.write_text("original\n", encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(proj), *cmd], check=True, env=env, capture_output=True)
    frozen.write_text("tampered\n", encoding="utf-8")  # a Composer edit slips through

    evt = {"file_path": str(frozen), "workspace_roots": [str(proj)]}
    d = _decide("after_edit", evt, home, capsys)
    assert "reverted" in d.get("agentMessage", "").lower()
    assert frozen.read_text(encoding="utf-8") == "original\n", "the frozen test must be restored"


def test_after_edit_is_silent_for_a_non_frozen_file(active_build, capsys):
    home, proj = active_build
    evt = {"file_path": str(proj / "src" / "feature.py"), "workspace_roots": [str(proj)]}
    assert _decide("after_edit", evt, home, capsys) == {}


# ── fail-open discipline: a resolvable-state error must never brick a command ────────────────
def test_shell_fails_open_on_malformed_event(tmp_path, capsys):
    """Garbage on stdin must still yield allow for shell/read — a gate bug never bricks a command."""
    home = tmp_path / "home"
    home.mkdir()
    gate.main(["hercules_gate.py", "shell"], stdin_text="{not json", home=str(home))
    assert json.loads(capsys.readouterr().out.strip())["permission"] == "allow"


# ── the shipped gate is the SAME state reader the other ecosystems use ───────────────────────
def test_cursor_ships_the_gate_and_the_canonical_state_reader(tmp_path):
    """dist/cursor/hooks/ must ship the adapter + hooks.json, and hercules_state.py byte-identical to
    the copy Claude Code uses — one source of truth for the frozen-guard state across all ecosystems."""
    out = tmp_path / "cursor"
    build_target("cursor", out)
    for name in ("hercules_gate.py", "hooks.json", "hercules_state.py"):
        assert (out / "hooks" / name).is_file(), f"dist/cursor/hooks/{name} must ship"
    assert (out / "hooks" / "hercules_state.py").read_bytes() == \
        (CLAUDE_HOOKS / "hercules_state.py").read_bytes(), "state reader must not diverge across dists"
