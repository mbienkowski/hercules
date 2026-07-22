"""The write-gate on Gemini CLI — the ONE generic adapter driven by gemini-cli's ``gate`` config.

Gemini's ``BeforeTool`` event vetoes a tool BEFORE it touches disk (Claude's ``PreToolUse`` shape), so
the gate is a real pre-write block: the descriptor's ``pre_tool`` config maps Gemini's ``write_file``/
``replace`` to the canonical guard's tool names and the adapter delegates to ``frozen_tests.decide`` —
the SAME frozen state and ``frozen_override`` policy every ecosystem reads. On a frozen-test edit
during a build it emits Gemini's deny decision; otherwise nothing (Gemini proceeds — the config has no
``allow`` shape). Reads are never blocked. Fails OPEN on any error/missing state.

These drive the real shared adapter (``src/hooks/hercules_gate.py``) in-process with the REAL
gemini-cli descriptor gate config, against a throwaway ``~/.hercules`` tree, asserting the emitted
Gemini decision JSON. The deny value is a HARDCODED literal in the assertions (never read from the
config) so drift in either the adapter or the descriptor data is caught; the canonical reason text is
pinned for the same reason.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from scripts.build.descriptor import discover

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_HOOKS = REPO_ROOT / "src" / "hooks"
GATE_CONFIG = discover()["gemini-cli"].gate


def _load_gate():
    """Import the shared adapter in-process. It does ``from frozen_tests import decide`` off its own
    dir — src/hooks/, where the guard modules live alongside it."""
    if str(SHARED_HOOKS) not in sys.path:
        sys.path.insert(0, str(SHARED_HOOKS))
    spec = importlib.util.spec_from_file_location("hercules_gate_generic", SHARED_HOOKS / "hercules_gate.py")
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
    """A throwaway ~/.hercules with one active build session freezing ``tests/test_frozen.py`` under
    *proj*, and that frozen file written to disk. Returns ``(home, proj, frozen_path)``."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    frozen = proj / "tests" / "test_frozen.py"
    frozen.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _write_state(home, proj, {"current_phase": "build", "current_spec": "spec-1.md",
                              "current_spec_round": 1, "frozen_test_files": ["tests/test_frozen.py"]})
    return home, proj, frozen


def _decide(evt: dict, home: Path, capsys) -> dict:
    """Run the adapter's ``main`` for *evt* under the gemini-cli gate config; return the parsed
    Gemini decision (or {} when it emitted nothing — the allow case)."""
    gate.main(stdin_text=json.dumps(evt), home=str(home), config=GATE_CONFIG)
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else {}


@pytest.mark.parametrize("tool", ["write_file", "replace"])
def test_before_tool_blocks_a_frozen_edit_and_never_touches_the_file(tool, active_build, capsys):
    """Both of Gemini's file-mutating tools targeting a frozen test during a build are DENIED (the
    hardcoded ``"deny"`` decision) with the canonical reason + escape hatch — and the adapter, being a
    pre-write veto, leaves the file on disk exactly as it was."""
    home, proj, frozen = active_build
    before = frozen.read_text(encoding="utf-8")
    evt = {"tool_name": tool, "tool_input": {"file_path": str(frozen)}, "cwd": str(proj)}
    d = _decide(evt, home, capsys)
    assert d["decision"] == "deny", f"{tool} on a frozen test must be denied"
    assert "is a frozen test for spec-1.md (build round 1/3)" in d["reason"]
    assert 'saying "change this test' in d["reason"], "the escape hatch must be named in the block"
    assert frozen.read_text(encoding="utf-8") == before, "the veto must not mutate the file"


def test_before_tool_allows_a_write_to_a_non_frozen_file(active_build, capsys):
    home, proj, _ = active_build
    evt = {"tool_name": "write_file", "tool_input": {"file_path": str(proj / "src" / "feature.py")},
           "cwd": str(proj)}
    assert _decide(evt, home, capsys) == {}, "a non-frozen write must be allowed (no decision emitted)"


def test_before_tool_allows_a_read_of_a_frozen_file(active_build, capsys):
    """The doctrine ALLOWS reading a frozen test — a non-mutating tool naming it is never blocked."""
    home, proj, frozen = active_build
    evt = {"tool_name": "read_file", "tool_input": {"file_path": str(frozen)}, "cwd": str(proj)}
    assert _decide(evt, home, capsys) == {}


def test_before_tool_allows_a_frozen_edit_the_user_sanctioned_via_override(tmp_path, capsys):
    """A live ``frozen_override`` covering the file lifts the gate — the documented 'change test X'
    grant works on Gemini exactly as on the other ecosystems (same canonical override policy)."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "build", "current_spec": "spec-1.md", "current_spec_round": 1,
                              "frozen_test_files": ["tests/test_frozen.py"],
                              "frozen_override": {"files": ["tests/test_frozen.py"], "spec": "spec-1.md",
                                                  "round": 1, "reason": "user: 'fix the expected status'"}})
    evt = {"tool_name": "write_file", "tool_input": {"file_path": str(proj / "tests" / "test_frozen.py")},
           "cwd": str(proj)}
    assert _decide(evt, home, capsys) == {}


def test_before_tool_allows_everything_when_no_build_is_active(tmp_path, capsys):
    """No config/state at all → empty frozen set → the gate must never interfere (fail-open on absence)."""
    home = tmp_path / "empty"
    home.mkdir()
    evt = {"tool_name": "write_file", "tool_input": {"file_path": str(tmp_path / "tests" / "test_frozen.py")},
           "cwd": str(tmp_path)}
    assert _decide(evt, home, capsys) == {}


def test_fails_open_on_malformed_stdin(tmp_path, capsys):
    """Garbage on stdin must yield no decision (allow) and exit 0 — a gate bug never bricks an edit."""
    home = tmp_path / "home"
    home.mkdir()
    assert gate.main(stdin_text="{not json", home=str(home), config=GATE_CONFIG) == 0
    assert capsys.readouterr().out.strip() == ""


def test_fails_open_on_a_non_dict_payload(tmp_path, capsys):
    """A well-formed but non-object payload (e.g. a bare JSON number) must fail open, not raise."""
    home = tmp_path / "home"
    home.mkdir()
    assert gate.main(stdin_text="123", home=str(home), config=GATE_CONFIG) == 0
    assert capsys.readouterr().out.strip() == ""


def test_before_tool_blocks_a_frozen_edit_delivered_in_camelcase(active_build, capsys):
    """Gemini is a JS host; a camelCase payload (``toolName``/``toolArgs``) must be understood exactly
    like the snake_case shape — a casing difference must never silently no-op the veto."""
    home, proj, frozen = active_build
    evt = {"toolName": "replace", "toolArgs": {"file_path": str(frozen)}, "cwd": str(proj)}
    assert _decide(evt, home, capsys)["decision"] == "deny"


def test_before_tool_blocks_a_frozen_edit_when_args_arrive_as_a_json_string(active_build, capsys):
    """A ``tool_input`` delivered as an unparsed JSON string (and under an alternate ``filePath`` key)
    is still parsed and the frozen path found — the edit is denied."""
    home, proj, frozen = active_build
    evt = {"tool_name": "write_file", "tool_input": json.dumps({"filePath": str(frozen)}), "cwd": str(proj)}
    assert _decide(evt, home, capsys)["decision"] == "deny"


def test_before_tool_allows_a_mutating_tool_with_no_resolvable_path(active_build, capsys):
    """A write tool whose arguments carry no recognizable path key fails OPEN (no path → allow), never a
    crash or a spurious block."""
    home, proj, _ = active_build
    evt = {"tool_name": "write_file", "tool_input": {"unknown_key": "x"}, "cwd": str(proj)}
    assert _decide(evt, home, capsys) == {}


def test_before_tool_fails_open_on_a_malformed_json_string_arg(active_build, capsys):
    """A ``tool_input`` delivered as a non-JSON string must fail OPEN (unparseable → no path → allow),
    never crash — the ``_extract_path`` parse-guard."""
    home, proj, _ = active_build
    evt = {"tool_name": "write_file", "tool_input": "{not json", "cwd": str(proj)}
    assert _decide(evt, home, capsys) == {}


def test_before_tool_fails_open_when_json_string_arg_is_not_an_object(active_build, capsys):
    """A ``tool_input`` string that parses to a JSON scalar (``"123"``), not an object, yields no path
    → allow — the non-dict branch of ``_extract_path``."""
    home, proj, _ = active_build
    evt = {"tool_name": "replace", "tool_input": "123", "cwd": str(proj)}
    assert _decide(evt, home, capsys) == {}
