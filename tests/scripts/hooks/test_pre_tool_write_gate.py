"""The universal ``pre_tool`` write-gate: one behaviour body per gate SHAPE, not per host, driving
``src/scripts/hooks/hercules_gate.py`` against the hand-made configurations in ``fixtures/``.
Only a fixture reaches a shape nobody ships — no refusal shape at all, a reason nested under a
wrapper the deny shape never carried, an unimplemented path strategy ahead of a real one. Expected
decisions stay HARDCODED in ``SHAPES``, so drift on either side is caught, and ONE roster test binds
each real host to its shape: a host matching no proven fixture FAILS."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

from tests.scripts.hooks.conftest import declared_gate_configs, gate_fixture

REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_HOOKS = REPO_ROOT / "src" / "scripts" / "hooks"


# Per SHAPE: the exact allow object (None means silence), the deny object, and where its reason lands.
SHAPES: dict = {
    "pre_tool_flat_gate": {
        "write_tools": ("create", "edit", "apply_patch"),
        "read_tool": "view",
        "allow": {"permissionDecision": "allow"},
        "deny": {"permissionDecision": "deny"},
        "reason_at": ["permissionDecisionReason"],
        "nested_edits": True,
    },
    "pre_tool_silent_allow_gate": {
        "write_tools": ("write_file", "replace"),
        "read_tool": "read_file",
        "allow": None,
        "deny": {"decision": "deny"},
        "reason_at": ["reason"],
        "nested_edits": False,
    },
    "pre_tool_deep_reason_gate": {
        "write_tools": ("edit",),
        "read_tool": "view",
        "allow": {"decision": "allow"},
        # The gate creates this wrapper, so lifting the reason out leaves it behind empty — the proof.
        "deny": {"decision": "deny", "details": {}},
        "reason_at": ["details", "reason"],
        "nested_edits": True,
    },
    "pre_tool_unknown_strategy_gate": {
        "write_tools": ("edit",),
        "read_tool": "view",
        "allow": {"permissionDecision": "allow"},
        "deny": {"permissionDecision": "deny"},
        "reason_at": ["permissionDecisionReason"],
        "nested_edits": False,
    },
}

# Per host: the fixture shape standing for it, the tools it must gate, and the read tool it must not.
# ecosystem-tax:start — one entry per host; measured and capped by tests/budgets/ecosystemTax.spec.ts.
SHAPE_OF_HOST: dict = {
    "gemini-cli": ("pre_tool_silent_allow_gate", ("write_file", "replace"), "read_file"),
    "copilot-cli": ("pre_tool_flat_gate", ("create", "edit", "str_replace_editor", "apply_patch"), "view"),
}
# ecosystem-tax:end

ALL_SHAPES = sorted(SHAPES)


def _load_gate():
    import sys
    if str(SHARED_HOOKS) not in sys.path:
        sys.path.insert(0, str(SHARED_HOOKS))
    spec = importlib.util.spec_from_file_location("hercules_gate_generic", SHARED_HOOKS / "hercules_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load_gate()


def _reads_paths_from_arguments(cfg: dict) -> bool:
    """True for a gate that answers before a write and finds its paths in named arguments."""
    if cfg.get("when") != "before_write":
        return False
    return any(p.get("from") == "arg_keys" for p in cfg.get("paths") or [])


def test_every_tool_refusing_before_a_write_is_covered_by_a_shape_proven_here():
    """The bridge from a fixture back to a real host: every such target appears here, no entry outlives
    its configuration, and each host matches the fixture standing for it."""
    declared = {name: cfg for name, cfg in declared_gate_configs().items()
                if _reads_paths_from_arguments(cfg)}
    assert sorted(declared) == sorted(SHAPE_OF_HOST), \
        "SHAPE_OF_HOST must cover exactly the tools that refuse before a write"

    for host, (shape, write_tools, read_tool) in SHAPE_OF_HOST.items():
        cfg, fixture = declared[host], gate_fixture(shape)
        assert (cfg.get("allow"), cfg.get("deny"), cfg.get("reason_at")) == \
            (fixture.get("allow"), fixture.get("deny"), fixture.get("reason_at")), \
            f"{host}: its refusal shape no longer matches the fixture {shape} proves"
        host_keys = set(cfg["paths"][0]["keys"])
        assert set(fixture["paths"][0]["keys"]) <= host_keys, \
            f"{host}: the fixture names a path key this host does not read"
        assert bool(cfg["paths"][0].get("nested")) == bool(fixture["paths"][0].get("nested")), \
            f"{host}: batched-edit support diverged from the fixture standing for it"
        for tool in write_tools:
            assert cfg.get("tools", {}).get(tool), f"{host}: {tool} writes but is not gated"
        assert read_tool not in cfg.get("tools", {}), \
            f"{host}: {read_tool} only reads — the doctrine never blocks a read"


def _config(shape: str) -> dict:
    return gate_fixture(shape)


def _write_state(home: Path, proj: Path, session: dict):
    (home / ".hercules" / "state").mkdir(parents=True, exist_ok=True)
    (home / ".hercules" / "config.json").write_text(json.dumps({"projects": {
        "p": {"directory": str(proj), "state_file": "p.json"}}}), encoding="utf-8")
    (home / ".hercules" / "state" / "p.json").write_text(
        json.dumps({"active_session": "s1", "sessions": {"s1": session}}), encoding="utf-8")


@pytest.fixture
def active_build(tmp_path):
    """A throwaway ~/.hercules with one active build freezing a real on-disk ``tests/test_frozen.py``."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    frozen = proj / "tests" / "test_frozen.py"
    frozen.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _write_state(home, proj, {"current_phase": "build", "current_spec": "spec-1.md",
                              "current_spec_round": 1, "frozen_test_files": ["tests/test_frozen.py"]})
    return home, proj, frozen


def _decide(shape: str, evt: dict, home: Path, capsys) -> dict:
    gate.main(["hercules_gate.py", "preToolUse"], stdin_text=json.dumps(evt), home=str(home),
              config=_config(shape))
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else {}


def _assert_allow(shape: str, decision: dict):
    expected = SHAPES[shape]["allow"]
    assert decision == ({} if expected is None else expected), f"{shape}: expected an allow decision"


def _assert_deny(shape: str, decision: dict) -> str:
    """Assert the refusal takes this shape's own form, and return the reason lifted out of it."""
    exp = SHAPES[shape]
    where = exp["reason_at"]
    node = decision
    for key in where[:-1]:
        node = node.get(key, {})
    reason = node.pop(where[-1], None)
    assert decision == exp["deny"], f"{shape}: deny decision shape drifted"
    assert reason, f"{shape}: a refusal must carry its reason at {where!r}"
    return reason


def _cases_write_tools():
    return [(shape, tool) for shape in ALL_SHAPES for tool in SHAPES[shape]["write_tools"]]


@pytest.mark.parametrize("shape,tool", _cases_write_tools(), ids=lambda p: p if isinstance(p, str) else p)
def test_every_write_tool_on_a_frozen_test_is_denied_and_never_touches_the_file(shape, tool, active_build, capsys):
    home, proj, frozen = active_build
    before = frozen.read_text(encoding="utf-8")
    d = _decide(shape, {"toolName": tool, "toolArgs": {"file_path": str(frozen)}, "cwd": str(proj)}, home, capsys)
    reason = _assert_deny(shape, d)
    assert "is a frozen test for spec-1.md (build round 1/3)" in reason
    assert 'saying "change this test' in reason, "the escape hatch must be named in the block"
    assert frozen.read_text(encoding="utf-8") == before, "the veto must not mutate the file"


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_snake_case_payload_shape_is_honored_identically(shape, active_build, capsys):
    home, proj, frozen = active_build
    tool = SHAPES[shape]["write_tools"][0]
    d = _decide(shape, {"tool_name": tool, "tool_input": {"file_path": str(frozen)}, "cwd": str(proj)},
                home, capsys)
    _assert_deny(shape, d)


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_a_json_string_argument_is_parsed_and_still_denied(shape, active_build, capsys):
    home, proj, frozen = active_build
    tool = SHAPES[shape]["write_tools"][0]
    evt = {"tool_name": tool, "tool_input": json.dumps({"filePath": str(frozen)}), "cwd": str(proj)}
    _assert_deny(shape, _decide(shape, evt, home, capsys))


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_a_read_tool_on_a_frozen_test_is_allowed(shape, active_build, capsys):
    """The agent must read the very test it makes pass, so the lock is against edits, not reads."""
    home, proj, frozen = active_build
    evt = {"toolName": SHAPES[shape]["read_tool"],
           "toolArgs": {"file_path": str(frozen)}, "cwd": str(proj)}
    _assert_allow(shape, _decide(shape, evt, home, capsys))


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_a_write_to_a_non_frozen_file_is_allowed(shape, active_build, capsys):
    home, proj, _ = active_build
    tool = SHAPES[shape]["write_tools"][0]
    evt = {"toolName": tool, "toolArgs": {"file_path": str(proj / "src" / "feature.py")}, "cwd": str(proj)}
    _assert_allow(shape, _decide(shape, evt, home, capsys))


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_a_write_tool_with_no_resolvable_path_fails_open(shape, active_build, capsys):
    home, proj, _ = active_build
    tool = SHAPES[shape]["write_tools"][0]
    _assert_allow(shape, _decide(shape, {"toolName": tool, "toolArgs": {"weird": 1}, "cwd": str(proj)}, home, capsys))


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_a_malformed_json_string_argument_fails_open(shape, active_build, capsys):
    home, proj, _ = active_build
    tool = SHAPES[shape]["write_tools"][0]
    _assert_allow(shape, _decide(shape, {"tool_name": tool, "tool_input": "{not json", "cwd": str(proj)}, home, capsys))


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_a_json_scalar_argument_fails_open(shape, active_build, capsys):
    home, proj, _ = active_build
    tool = SHAPES[shape]["write_tools"][0]
    _assert_allow(shape, _decide(shape, {"tool_name": tool, "tool_input": "123", "cwd": str(proj)}, home, capsys))


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_everything_is_allowed_when_no_build_is_active(shape, tmp_path, capsys):
    home = tmp_path / "empty"
    home.mkdir()
    tool = SHAPES[shape]["write_tools"][0]
    evt = {"toolName": tool, "toolArgs": {"file_path": str(tmp_path / "tests" / "test_frozen.py")},
           "cwd": str(tmp_path)}
    _assert_allow(shape, _decide(shape, evt, home, capsys))


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_a_user_granted_frozen_override_lifts_the_gate(shape, tmp_path, capsys):
    """One canonical override policy, never re-implemented per shape."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "build", "current_spec": "spec-1.md", "current_spec_round": 1,
                              "frozen_test_files": ["tests/test_frozen.py"],
                              "frozen_override": {"files": ["tests/test_frozen.py"], "spec": "spec-1.md",
                                                  "round": 1, "reason": "user: 'fix the expected status'"}})
    tool = SHAPES[shape]["write_tools"][0]
    evt = {"toolName": tool, "toolArgs": {"file_path": str(proj / "tests" / "test_frozen.py")},
           "cwd": str(proj)}
    _assert_allow(shape, _decide(shape, evt, home, capsys))


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_fails_open_on_malformed_stdin(shape, tmp_path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    assert gate.main(["hercules_gate.py"], stdin_text="{not json", home=str(home), config=_config(shape)) == 0
    out = capsys.readouterr().out.strip()
    _assert_allow(shape, json.loads(out) if out else {})


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_fails_open_on_empty_stdin(shape, tmp_path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    assert gate.main(["hercules_gate.py"], stdin_text="", home=str(home), config=_config(shape)) == 0
    out = capsys.readouterr().out.strip()
    _assert_allow(shape, json.loads(out) if out else {})


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_fails_open_on_a_non_dict_payload(shape, tmp_path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    assert gate.main(["hercules_gate.py"], stdin_text="123", home=str(home), config=_config(shape)) == 0
    out = capsys.readouterr().out.strip()
    _assert_allow(shape, json.loads(out) if out else {})


@pytest.mark.parametrize("shape", [s for s in ALL_SHAPES if SHAPES[s]["nested_edits"]])
def test_a_nested_edit_list_naming_the_frozen_test_is_denied(shape, active_build, capsys):
    home, proj, frozen = active_build
    tool = SHAPES[shape]["write_tools"][-1]
    evt = {"toolName": tool, "toolArgs": {"edits": [{"file_path": str(frozen)}]}, "cwd": str(proj)}
    _assert_deny(shape, _decide(shape, evt, home, capsys))


@pytest.mark.parametrize("shape", [s for s in ALL_SHAPES if SHAPES[s]["nested_edits"]])
def test_an_edit_list_whose_items_name_no_path_fails_open(shape, active_build, capsys):
    home, proj, _ = active_build
    tool = SHAPES[shape]["write_tools"][-1]
    evt = {"toolName": tool, "toolArgs": {"edits": [{"note": "x"}, {"note": "y"}]}, "cwd": str(proj)}
    _assert_allow(shape, _decide(shape, evt, home, capsys))


@pytest.mark.parametrize("shape", [s for s in ALL_SHAPES if SHAPES[s]["nested_edits"]])
def test_a_batched_edit_with_a_frozen_file_in_a_LATER_hunk_is_denied(shape, active_build, capsys):
    """The gate checks every path a batch names, not just the first."""
    home, proj, frozen = active_build
    tool = SHAPES[shape]["write_tools"][-1]
    evt = {"toolName": tool, "toolArgs": {"edits": [{"file_path": str(proj / "src" / "ok.py")},
                                                    {"file_path": str(frozen)}]}, "cwd": str(proj)}
    _assert_deny(shape, _decide(shape, evt, home, capsys))


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_a_relative_path_is_resolved_against_the_event_cwd(shape, active_build, capsys):
    home, proj, _ = active_build
    tool = SHAPES[shape]["write_tools"][0]
    evt = {"toolName": tool, "toolArgs": {"file_path": "tests/test_frozen.py"}, "cwd": str(proj)}
    _assert_deny(shape, _decide(shape, evt, home, capsys))


def test_reads_from_real_stdin_when_no_text_is_passed(active_build, capsys, monkeypatch):
    """The stdin plumbing is protocol-independent, so one shape exercises it for all."""
    home, proj, frozen = active_build
    shape = ALL_SHAPES[0]
    tool = SHAPES[shape]["write_tools"][0]
    evt = {"toolName": tool, "toolArgs": {"file_path": str(frozen)}, "cwd": str(proj)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(evt)))
    gate.main(["hercules_gate.py"], home=str(home), config=_config(shape))
    _assert_deny(shape, json.loads(capsys.readouterr().out.strip()))


# ── shapes a dist/ read could never reach ──────────────────────────────────────────────────────
def test_a_refusal_nests_under_a_wrapper_the_deny_shape_never_carried(active_build, capsys):
    """A refusal that loses its reason is one an agent cannot act on, so the gate builds the missing
    level rather than dropping it — a shape no shipped gate asks for, reachable only from a fixture."""
    home, proj, frozen = active_build
    evt = {"tool_name": "edit", "tool_input": {"file_path": str(frozen)}, "cwd": str(proj)}
    decision = _decide("pre_tool_deep_reason_gate", evt, home, capsys)
    assert decision["decision"] == "deny"
    assert "is a frozen test for spec-1.md (build round 1/3)" in decision["details"]["reason"], \
        "the reason must land inside the wrapper the gate had to create"


def test_a_gate_that_declares_no_refusal_shape_fails_open_instead_of_crashing(active_build, capsys):
    """A broken gate must never brick an edit — and no shipped gate is broken, so only a fixture can
    hold the adapter to that."""
    home, proj, frozen = active_build
    evt = {"tool_name": "edit", "tool_input": {"file_path": str(frozen)}, "cwd": str(proj)}
    assert gate.main(["hercules_gate.py", "preToolUse"], stdin_text=json.dumps(evt), home=str(home),
                     config=_config("pre_tool_no_deny_gate")) == 0
    out = capsys.readouterr().out.strip()
    assert json.loads(out) == {"permissionDecision": "allow"}, "a gate that cannot refuse must allow"


def test_an_unreadable_configuration_is_not_a_configuration_at_all(tmp_path, capsys):
    """Without a readable configuration the adapter cannot know the host's allow shape, so it says
    nothing rather than guessing a verdict."""
    home = tmp_path / "home"
    home.mkdir()
    assert gate.main(["hercules_gate.py", "preToolUse"], stdin_text="{}", home=str(home), config=[]) == 0
    assert capsys.readouterr().out.strip() == ""


def test_a_gate_asking_through_a_protocol_this_adapter_has_none_for_says_nothing(active_build, capsys):
    """The protocols are a CLOSED set, so no behaviour can be smuggled in through the JSON: an
    unimplemented ``when`` gets silence, never an invented verdict and above all never a block."""
    home, proj, frozen = active_build
    evt = {"tool_name": "edit", "tool_input": {"file_path": str(frozen)}, "cwd": str(proj)}
    assert gate.main(["hercules_gate.py", "preToolUse"], stdin_text=json.dumps(evt), home=str(home),
                     config=gate_fixture("unknown_protocol_gate")) == 0
    assert capsys.readouterr().out.strip() == ""


def test_a_path_strategy_nobody_implements_is_skipped_rather_than_ending_the_search(active_build, capsys):
    """An unimplemented strategy must find nothing AND leave the rest to run, so the real one behind
    it still catches the frozen path."""
    home, proj, frozen = active_build
    evt = {"tool_name": "edit", "tool_input": {"file_path": str(frozen)}, "cwd": str(proj)}
    reason = _assert_deny("pre_tool_unknown_strategy_gate", _decide("pre_tool_unknown_strategy_gate", evt, home, capsys))
    assert "is a frozen test for spec-1.md (build round 1/3)" in reason
