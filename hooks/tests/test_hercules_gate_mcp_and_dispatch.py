"""Unit-level coverage for ``hercules_gate.py``'s MCP-payload probing (``_mcp_hits_frozen``) and the
``event_guards``/``main`` dispatch glue.

Several of these call the private functions DIRECTLY rather than through ``main()``: ``main``'s own
``except Exception`` clause fails open by re-deriving the exact same safe output an internal
exception would already have produced (e.g. ``_guards_allow(cfg)`` after a caught crash looks
IDENTICAL, on stdout, to the crash never happening) — so a full end-to-end decision can't observe
some of these bugs at all. Calling the function directly is the only way an errant exception (or a
silently wrong return value) actually fails the test.

Mirrors ``test_cursor_write_gate.py``'s ``_load_gate`` (own small copy — existing convention here).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_HOOKS = REPO_ROOT / "hooks"


def _load_gate():
    if str(SHARED_HOOKS) not in sys.path:
        sys.path.insert(0, str(SHARED_HOOKS))
    spec = importlib.util.spec_from_file_location("hercules_gate_generic", SHARED_HOOKS / "hercules_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load_gate()

_FROZEN = {"tests/test_frozen.py": {}}


def _write_state(home: Path, proj: Path, session: dict):
    (home / ".hercules" / "state").mkdir(parents=True, exist_ok=True)
    (home / ".hercules" / "config.json").write_text(json.dumps({"projects": {
        "p": {"directory": str(proj), "state_file": "p.json"}}}), encoding="utf-8")
    (home / ".hercules" / "state" / "p.json").write_text(
        json.dumps({"active_session": "s1", "sessions": {"s1": session}}), encoding="utf-8")


@pytest.fixture
def active_build_home(tmp_path):
    """A throwaway ~/.hercules with one active build freezing ``tests/test_frozen.py``. Returns
    ``(home, proj)`` — no file written to disk, `_event_guards_decide` never touches the filesystem
    for shell/mcp modes."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "build", "current_spec": "spec-1.md",
                              "current_spec_round": 1, "frozen_test_files": ["tests/test_frozen.py"]})
    return home, proj


# ── _mcp_hits_frozen: tool-name resolution — every alternate key, the string guard, first-wins ───

@pytest.mark.parametrize("key", ["toolName", "name", "tool", "method", "server_name", "serverName", "server"])
def test_mcp_hits_frozen_recognizes_the_tool_name_under_each_alternate_key(key):
    evt = {key: "git_commit", "arguments": {"path": "tests/test_frozen.py"}}
    assert gate._mcp_hits_frozen(evt, _FROZEN) == "tests/test_frozen.py"


def test_mcp_hits_frozen_ignores_a_non_string_truthy_tool_name():
    """A non-string tool-name value must never reach the write-hint regex (which requires a str) —
    the check is `isinstance(v, str) and v`, not merely `v` truthy."""
    assert gate._mcp_hits_frozen({"tool_name": 123}, _FROZEN) is None


def test_mcp_hits_frozen_uses_the_first_matching_name_key_not_the_last():
    """Once a name key matches, the scan must STOP — a later, coincidentally-present key must never
    override an already-resolved (and here, non-mutating) tool name."""
    evt = {"tool_name": "read_file", "name": "git_commit", "arguments": {"path": "tests/test_frozen.py"}}
    assert gate._mcp_hits_frozen(evt, _FROZEN) is None


def test_mcp_hits_frozen_defaults_the_tool_name_to_empty_string(monkeypatch):
    """The tool-name default (when no key matches at all) must be exactly the empty string — proven
    via a write-hint pattern that specifically matches the mutation-testing placeholder text, which
    only the WRONG default would satisfy."""
    monkeypatch.setattr(gate, "_MCP_WRITE_HINT", __import__("re").compile("XXXX"))
    evt = {"arguments": {"path": "tests/test_frozen.py"}}  # no name-key present at all
    assert gate._mcp_hits_frozen(evt, _FROZEN) is None


# ── _mcp_hits_frozen: argument-payload resolution — every alternate key, first-wins, defaults ────

@pytest.mark.parametrize("key", ["tool_input", "toolInput", "input", "params", "args"])
def test_mcp_hits_frozen_recognizes_the_frozen_path_under_each_alternate_args_key(key):
    evt = {"tool_name": "git_commit", key: {"path": "tests/test_frozen.py"}}
    assert gate._mcp_hits_frozen(evt, _FROZEN) == "tests/test_frozen.py"


def test_mcp_hits_frozen_uses_the_first_matching_args_key_not_the_last():
    """``tool_input`` is checked before ``arguments`` — once matched, the scan must stop rather than
    letting a later key's (frozen-naming) payload override an earlier, innocuous one."""
    evt = {"tool_name": "git_commit", "tool_input": {"note": "nothing frozen here"},
           "arguments": {"path": "tests/test_frozen.py"}}
    assert gate._mcp_hits_frozen(evt, _FROZEN) is None


def test_mcp_hits_frozen_defaults_args_to_none_when_no_args_key_is_present():
    """The args default (no args-key present at all) must be exactly ``None``, proven via a
    contrived frozen "path" whose basename only a stray empty-string serialization would match."""
    evt = {"tool_name": "git_commit"}  # write-ish name, but no args-key at all
    frozen = {'"': {}}  # basename is a bare double-quote char
    assert gate._mcp_hits_frozen(evt, frozen) is None


def test_mcp_hits_frozen_serializes_a_missing_payload_as_an_empty_blob():
    evt = {"tool_name": "git_commit"}
    frozen = {"XXXX": {}}  # a basename equal to the mutation-testing placeholder text
    assert gate._mcp_hits_frozen(evt, frozen) is None


def test_mcp_hits_frozen_falls_back_to_str_when_the_payload_is_not_json_serializable():
    circular = []
    circular.append(circular)
    evt = {"tool_name": "git_commit", "arguments": circular}
    assert gate._mcp_hits_frozen(evt, _FROZEN) is None


# ── _event_guards_decide: the "allow" path prints the HOST's cfg, never a bare/None fallback ─────
# (a bug here is MASKED by main()'s own except clause when driven through main — it re-derives the
# same "allow cfg" output on a caught crash — so these call `_event_guards_decide` directly.)

_CFG = {"allow": {"permission": "allow"}, "deny": {"permission": "deny"},
        "user_key": "userMessage", "agent_key": "agentMessage"}


def test_event_guards_decide_shell_allows_with_the_hosts_cfg_when_no_build_is_active(tmp_path, capsys):
    home = tmp_path / "empty-home"
    home.mkdir()
    gate._event_guards_decide(_CFG, "shell", {"cwd": str(tmp_path)}, home=str(home))
    assert json.loads(capsys.readouterr().out.strip()) == _CFG["allow"]


def test_event_guards_decide_shell_allows_with_the_hosts_cfg_when_the_command_does_not_write(
        active_build_home, capsys):
    home, proj = active_build_home
    evt = {"command": "cat tests/test_frozen.py", "workspace_roots": [str(proj)]}
    gate._event_guards_decide(_CFG, "shell", evt, home=str(home))
    assert json.loads(capsys.readouterr().out.strip()) == _CFG["allow"]


def test_event_guards_decide_mcp_allows_with_the_hosts_cfg_when_the_call_is_read_ish(
        active_build_home, capsys):
    home, proj = active_build_home
    evt = {"tool_name": "read_file", "arguments": {"path": "tests/test_frozen.py"},
           "workspace_roots": [str(proj)]}
    gate._event_guards_decide(_CFG, "mcp", evt, home=str(home))
    assert json.loads(capsys.readouterr().out.strip()) == _CFG["allow"]


def test_event_guards_decide_shell_defaults_the_command_to_empty_string_when_absent(
        active_build_home, monkeypatch):
    home, proj = active_build_home
    captured = {}

    def fake_writes_frozen(cmd, frozen):
        captured["cmd"] = cmd
        return None

    monkeypatch.setattr(gate, "_writes_frozen", fake_writes_frozen)
    gate._event_guards_decide(_CFG, "shell", {"workspace_roots": [str(proj)]}, home=str(home))
    assert captured["cmd"] == ""


# ── _event_guards_decide: after_edit/headless — the exact wording of BOTH notes (a user/agent
# reads this — content matters, same reasoning as _ide_advisory's exact-message pin) ─────────────

def test_event_guards_decide_after_edit_headless_restore_success_note_is_pinned_exactly(
        active_build_home, monkeypatch, capsys):
    home, proj = active_build_home
    monkeypatch.setenv("HERCULES_RUNTIME_MODE", "headless")
    monkeypatch.setattr(gate, "_restore", lambda cwd, fp: True)
    fp = str(proj / "tests" / "test_frozen.py")
    gate._event_guards_decide(_CFG, "after_edit", {"file_path": fp, "workspace_roots": [str(proj)]}, home=str(home))
    out = json.loads(capsys.readouterr().out.strip())
    assert out[_CFG["user_key"]].endswith(
        " (No human was present, so Hercules restored the file from git.)")


def test_event_guards_decide_after_edit_headless_restore_failure_note_is_pinned_exactly(
        active_build_home, monkeypatch, capsys):
    home, proj = active_build_home
    monkeypatch.setenv("HERCULES_RUNTIME_MODE", "headless")
    monkeypatch.setattr(gate, "_restore", lambda cwd, fp: False)
    fp = str(proj / "tests" / "test_frozen.py")
    gate._event_guards_decide(_CFG, "after_edit", {"file_path": fp, "workspace_roots": [str(proj)]}, home=str(home))
    out = json.loads(capsys.readouterr().out.strip())
    assert out[_CFG["user_key"]].endswith(
        " (Hercules could NOT auto-restore it — not a git repo, or the test is "
        "untracked. Revert it manually before continuing.)")


# ── main(): return code, mode default, and the except-clause's protocol/mode gate ────────────────

def test_main_returns_zero_when_no_readable_host_config_exists(tmp_path):
    """`main` fails OPEN with exit code 0 (never a nonzero "error") when `_read_config` can't find a
    `gate.json` beside the script — the shipped template location, which never carries one."""
    home = tmp_path / "home"
    home.mkdir()
    assert gate.main(["hercules_gate.py"], stdin_text="{}", home=str(home), config=None) == 0


def test_main_defaults_the_event_guards_mode_to_empty_string_when_argv_has_no_mode(monkeypatch, tmp_path):
    captured = {}

    def fake_decide(cfg, mode, evt, home=None):
        captured["mode"] = mode

    monkeypatch.setattr(gate, "_event_guards_decide", fake_decide)
    home = tmp_path / "home"
    home.mkdir()
    gate.main(["hercules_gate.py"], stdin_text="{}", home=str(home), config={"protocol": "event_guards"})
    assert captured["mode"] == ""


def test_main_evaluates_whitespace_only_stdin_the_same_as_empty_stdin(monkeypatch, tmp_path):
    """Whitespace-only stdin (truthy as a string, but empty once stripped) must take the SAME `{}`
    path as genuinely empty stdin — never attempt to `json.loads` it (which would raise)."""
    calls = []
    monkeypatch.setattr(gate.json, "loads", lambda s: calls.append(s) or {})
    home = tmp_path / "home"
    home.mkdir()
    gate.main(["hercules_gate.py", "after_edit"], stdin_text="   ",
              home=str(home), config={"protocol": "event_guards"})
    assert calls == [], "whitespace-only stdin must never reach json.loads"


def test_main_stays_silent_for_after_edit_mode_on_malformed_stdin(tmp_path, capsys):
    """The except-clause's fail-open auto-allow is scoped to shell/mcp modes ONLY — after_edit is
    notification-only, so a caught crash there must print NOTHING, not a stray allow."""
    home = tmp_path / "home"
    home.mkdir()
    gate.main(["hercules_gate.py", "after_edit"], stdin_text="{not json",
              home=str(home), config={"protocol": "event_guards", **_CFG})
    assert capsys.readouterr().out.strip() == ""
