"""The universal ``pre_tool`` write-gate suite — one behavior body per case, every gated ecosystem.

Drives the ONE shared adapter (``src/hooks/hercules_gate.py``) in-process with each ecosystem's REAL
descriptor gate config, against a throwaway ``~/.hercules`` tree. The expected decision JSON per
ecosystem is a HARDCODED literal in ``PRE_TOOL_EXPECTATIONS`` — never read from the config — so
drift in either the adapter or the descriptor data is caught (pin both ends). A gated ``pre_tool``
ecosystem missing its expectations entry FAILS (fail-closed completeness, GATE_EXPECTATIONS style).

Behavioral cases preserved verbatim from the per-ecosystem suites this replaces: deny on every write
tool (file bytes untouched), canonical reason + escape hatch, both payload casings, JSON-string and
nested-edit arguments, reads/non-frozen/no-build/override allows, and full fail-open discipline.
"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

from scripts.build.descriptor import discover

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_HOOKS = REPO_ROOT / "src" / "hooks"

# HAND-AUTHORED expectations (flat literals only). `allow` is the EXACT decision object an allow
# must print — or None for hosts whose silence means allow. `deny` is the exact deny object minus
# the reason entry; `reason_key` is where the canonical reason must land.
PRE_TOOL_EXPECTATIONS: dict = {
    "gemini-cli": {
        "write_tools": ("write_file", "replace"),
        "read_tool": "read_file",
        "allow": None,
        "deny": {"decision": "deny"},
        "reason_key": "reason",
        "nested_edits": False,
    },
    "copilot-cli": {
        "write_tools": ("create", "edit", "str_replace_editor", "apply_patch"),
        "read_tool": "view",
        "allow": {"permissionDecision": "allow"},
        "deny": {"permissionDecision": "deny"},
        "reason_key": "permissionDecisionReason",
        "nested_edits": True,
    },
}

ECOS = sorted(PRE_TOOL_EXPECTATIONS)


def _load_gate():
    import sys
    if str(SHARED_HOOKS) not in sys.path:
        sys.path.insert(0, str(SHARED_HOOKS))
    spec = importlib.util.spec_from_file_location("hercules_gate_generic", SHARED_HOOKS / "hercules_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load_gate()


def test_every_pre_tool_gated_ecosystem_declares_its_expectations():
    """Fail-closed completeness: every descriptor wiring the pre_tool protocol must have a
    hand-authored expectations entry here, and no entry may outlive its descriptor."""
    gated = sorted(name for name, d in discover().items()
                   if d.gate is not None and d.gate.get("protocol") == "pre_tool")
    assert gated == ECOS, "PRE_TOOL_EXPECTATIONS must cover exactly the pre_tool-gated ecosystems"


def _config(eco: str) -> dict:
    return discover()[eco].gate


def _write_state(home: Path, proj: Path, session: dict):
    (home / ".hercules" / "state").mkdir(parents=True, exist_ok=True)
    (home / ".hercules" / "config.json").write_text(json.dumps({"projects": {
        "p": {"directory": str(proj), "state_file": "p.json"}}}), encoding="utf-8")
    (home / ".hercules" / "state" / "p.json").write_text(
        json.dumps({"active_session": "s1", "sessions": {"s1": session}}), encoding="utf-8")


@pytest.fixture
def active_build(tmp_path):
    """A throwaway ~/.hercules with one active build freezing ``tests/test_frozen.py`` (written to
    disk). Returns ``(home, proj, frozen_path)``."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    frozen = proj / "tests" / "test_frozen.py"
    frozen.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _write_state(home, proj, {"current_phase": "build", "current_spec": "spec-1.md",
                              "current_spec_round": 1, "frozen_test_files": ["tests/test_frozen.py"]})
    return home, proj, frozen


def _decide(eco: str, evt: dict, home: Path, capsys) -> dict:
    gate.main(["hercules_gate.py", "preToolUse"], stdin_text=json.dumps(evt), home=str(home),
              config=_config(eco))
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else {}


def _assert_allow(eco: str, decision: dict):
    expected = PRE_TOOL_EXPECTATIONS[eco]["allow"]
    assert decision == ({} if expected is None else expected), f"{eco}: expected an allow decision"


def _assert_deny(eco: str, decision: dict) -> str:
    exp = PRE_TOOL_EXPECTATIONS[eco]
    reason = decision.pop(exp["reason_key"], None)
    assert decision == exp["deny"], f"{eco}: deny decision shape drifted"
    assert reason, f"{eco}: deny must carry a reason under {exp['reason_key']!r}"
    return reason


def _cases_write_tools():
    return [(eco, tool) for eco in ECOS for tool in PRE_TOOL_EXPECTATIONS[eco]["write_tools"]]


@pytest.mark.parametrize("eco,tool", _cases_write_tools(), ids=lambda p: p if isinstance(p, str) else p)
def test_every_write_tool_on_a_frozen_test_is_denied_and_never_touches_the_file(eco, tool, active_build, capsys):
    home, proj, frozen = active_build
    before = frozen.read_text(encoding="utf-8")
    d = _decide(eco, {"toolName": tool, "toolArgs": {"file_path": str(frozen)}, "cwd": str(proj)}, home, capsys)
    reason = _assert_deny(eco, d)
    assert "is a frozen test for spec-1.md (build round 1/3)" in reason
    assert 'saying "change this test' in reason, "the escape hatch must be named in the block"
    assert frozen.read_text(encoding="utf-8") == before, "the veto must not mutate the file"


@pytest.mark.parametrize("eco", ECOS)
def test_snake_case_payload_shape_is_honored_identically(eco, active_build, capsys):
    home, proj, frozen = active_build
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][0]
    d = _decide(eco, {"tool_name": tool, "tool_input": {"file_path": str(frozen)}, "cwd": str(proj)},
                home, capsys)
    _assert_deny(eco, d)


@pytest.mark.parametrize("eco", ECOS)
def test_a_json_string_argument_is_parsed_and_still_denied(eco, active_build, capsys):
    home, proj, frozen = active_build
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][0]
    evt = {"tool_name": tool, "tool_input": json.dumps({"filePath": str(frozen)}), "cwd": str(proj)}
    _assert_deny(eco, _decide(eco, evt, home, capsys))


@pytest.mark.parametrize("eco", ECOS)
def test_a_read_tool_on_a_frozen_test_is_allowed(eco, active_build, capsys):
    """The doctrine locks frozen tests against EDITS, not reads — the agent must read the very
    test it makes pass."""
    home, proj, frozen = active_build
    evt = {"toolName": PRE_TOOL_EXPECTATIONS[eco]["read_tool"],
           "toolArgs": {"file_path": str(frozen)}, "cwd": str(proj)}
    _assert_allow(eco, _decide(eco, evt, home, capsys))


@pytest.mark.parametrize("eco", ECOS)
def test_a_write_to_a_non_frozen_file_is_allowed(eco, active_build, capsys):
    home, proj, _ = active_build
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][0]
    evt = {"toolName": tool, "toolArgs": {"file_path": str(proj / "src" / "feature.py")}, "cwd": str(proj)}
    _assert_allow(eco, _decide(eco, evt, home, capsys))


@pytest.mark.parametrize("eco", ECOS)
def test_a_write_tool_with_no_resolvable_path_fails_open(eco, active_build, capsys):
    home, proj, _ = active_build
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][0]
    _assert_allow(eco, _decide(eco, {"toolName": tool, "toolArgs": {"weird": 1}, "cwd": str(proj)}, home, capsys))


@pytest.mark.parametrize("eco", ECOS)
def test_a_malformed_json_string_argument_fails_open(eco, active_build, capsys):
    home, proj, _ = active_build
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][0]
    _assert_allow(eco, _decide(eco, {"tool_name": tool, "tool_input": "{not json", "cwd": str(proj)}, home, capsys))


@pytest.mark.parametrize("eco", ECOS)
def test_a_json_scalar_argument_fails_open(eco, active_build, capsys):
    home, proj, _ = active_build
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][0]
    _assert_allow(eco, _decide(eco, {"tool_name": tool, "tool_input": "123", "cwd": str(proj)}, home, capsys))


@pytest.mark.parametrize("eco", ECOS)
def test_everything_is_allowed_when_no_build_is_active(eco, tmp_path, capsys):
    home = tmp_path / "empty"
    home.mkdir()
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][0]
    evt = {"toolName": tool, "toolArgs": {"file_path": str(tmp_path / "tests" / "test_frozen.py")},
           "cwd": str(tmp_path)}
    _assert_allow(eco, _decide(eco, evt, home, capsys))


@pytest.mark.parametrize("eco", ECOS)
def test_a_user_granted_frozen_override_lifts_the_gate(eco, tmp_path, capsys):
    """The documented 'change test X' grant works identically on every pre_tool ecosystem — the
    same canonical override policy, never a re-implementation."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "build", "current_spec": "spec-1.md", "current_spec_round": 1,
                              "frozen_test_files": ["tests/test_frozen.py"],
                              "frozen_override": {"files": ["tests/test_frozen.py"], "spec": "spec-1.md",
                                                  "round": 1, "reason": "user: 'fix the expected status'"}})
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][0]
    evt = {"toolName": tool, "toolArgs": {"file_path": str(proj / "tests" / "test_frozen.py")},
           "cwd": str(proj)}
    _assert_allow(eco, _decide(eco, evt, home, capsys))


@pytest.mark.parametrize("eco", ECOS)
def test_fails_open_on_malformed_stdin(eco, tmp_path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    assert gate.main(["hercules_gate.py"], stdin_text="{not json", home=str(home), config=_config(eco)) == 0
    out = capsys.readouterr().out.strip()
    _assert_allow(eco, json.loads(out) if out else {})


@pytest.mark.parametrize("eco", ECOS)
def test_fails_open_on_empty_stdin(eco, tmp_path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    assert gate.main(["hercules_gate.py"], stdin_text="", home=str(home), config=_config(eco)) == 0
    out = capsys.readouterr().out.strip()
    _assert_allow(eco, json.loads(out) if out else {})


@pytest.mark.parametrize("eco", ECOS)
def test_fails_open_on_a_non_dict_payload(eco, tmp_path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    assert gate.main(["hercules_gate.py"], stdin_text="123", home=str(home), config=_config(eco)) == 0
    out = capsys.readouterr().out.strip()
    _assert_allow(eco, json.loads(out) if out else {})


@pytest.mark.parametrize("eco", [e for e in ECOS if PRE_TOOL_EXPECTATIONS[e]["nested_edits"]])
def test_a_nested_edit_list_naming_the_frozen_test_is_denied(eco, active_build, capsys):
    home, proj, frozen = active_build
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][-1]
    evt = {"toolName": tool, "toolArgs": {"edits": [{"file_path": str(frozen)}]}, "cwd": str(proj)}
    _assert_deny(eco, _decide(eco, evt, home, capsys))


@pytest.mark.parametrize("eco", [e for e in ECOS if PRE_TOOL_EXPECTATIONS[e]["nested_edits"]])
def test_an_edit_list_whose_items_name_no_path_fails_open(eco, active_build, capsys):
    home, proj, _ = active_build
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][-1]
    evt = {"toolName": tool, "toolArgs": {"edits": [{"note": "x"}, {"note": "y"}]}, "cwd": str(proj)}
    _assert_allow(eco, _decide(eco, evt, home, capsys))


@pytest.mark.parametrize("eco", [e for e in ECOS if PRE_TOOL_EXPECTATIONS[e]["nested_edits"]])
def test_a_batched_edit_with_a_frozen_file_in_a_LATER_hunk_is_denied(eco, active_build, capsys):
    """A batched multi-edit whose FIRST target is innocuous but a later one is a frozen test must be
    denied — the gate checks every named path, not just the first (regression for the first-path-only
    bypass: a mixed [non-frozen, frozen] patch previously sailed through)."""
    home, proj, frozen = active_build
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][-1]
    evt = {"toolName": tool, "toolArgs": {"edits": [{"file_path": str(proj / "src" / "ok.py")},
                                                    {"file_path": str(frozen)}]}, "cwd": str(proj)}
    _assert_deny(eco, _decide(eco, evt, home, capsys))


@pytest.mark.parametrize("eco", ECOS)
def test_a_relative_path_is_resolved_against_the_event_cwd(eco, active_build, capsys):
    home, proj, _ = active_build
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][0]
    evt = {"toolName": tool, "toolArgs": {"file_path": "tests/test_frozen.py"}, "cwd": str(proj)}
    _assert_deny(eco, _decide(eco, evt, home, capsys))


def test_reads_from_real_stdin_when_no_text_is_passed(active_build, capsys, monkeypatch):
    """With no ``stdin_text`` the adapter reads ``sys.stdin`` — a frozen edit there is still denied
    (exercised once; the stdin plumbing is protocol-independent)."""
    home, proj, frozen = active_build
    eco = ECOS[0]
    tool = PRE_TOOL_EXPECTATIONS[eco]["write_tools"][0]
    evt = {"toolName": tool, "toolArgs": {"file_path": str(frozen)}, "cwd": str(proj)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(evt)))
    gate.main(["hercules_gate.py"], home=str(home), config=_config(eco))
    _assert_deny(eco, json.loads(capsys.readouterr().out.strip()))
