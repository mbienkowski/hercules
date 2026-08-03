"""A gate that reports AFTER a write, in every shape one can take. Such a gate cannot prevent
anything, so what it owes is different: say so clearly, and change nothing.
Driven against ``src/scripts/hooks/hercules_gate.py`` and the ``fixtures/`` configurations, which
reach shapes nobody ships — a host whose person and agent read the SAME key. One roster test names
reality: a declared after-the-fact gate must be one of the shapes below, exactly, so a host with a
new shape fails until a fixture proves it. Gates asked BEFORE a write: test_pre_tool_write_gate.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tests.scripts.hooks.conftest import declared_gate_configs, gate_fixture


REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_HOOKS = REPO_ROOT / "src" / "scripts" / "hooks"
FROZEN = "tests/test_frozen.py"

# Every such shape; the single-channel one exists because nothing may depend on the keys differing.
SHAPES = ["after_write_two_channel_gate", "after_write_one_channel_gate"]


def _load_gate():
    """The gate module, loaded from the shared tree it is copied out of."""
    if str(SHARED_HOOKS) not in sys.path:
        sys.path.insert(0, str(SHARED_HOOKS))
    spec = importlib.util.spec_from_file_location("hercules_gate_universal", SHARED_HOOKS / "hercules_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

REPORTS_AFTER = [(name, gate_fixture(name)) for name in SHAPES]


def test_every_tool_whose_gate_reports_after_a_write_is_one_of_the_shapes_proven_here():
    """A parameterised suite that finds nothing passes, and that is indistinguishable from passing on
    everything — so the roster is stated independently, and at least one target must declare a gate."""
    declared = {name: cfg for name, cfg in declared_gate_configs().items()
                if cfg.get("when") == "after_write"}
    assert declared, "no tool declares a gate that reports after a write"
    proven = [cfg for _, cfg in REPORTS_AFTER]
    for name, cfg in declared.items():
        assert cfg in proven, (
            f"{name} declares an after-the-fact gate shape no fixture here proves — add the fixture "
            f"and the shape to SHAPES rather than shipping it unexercised")


@pytest.fixture(autouse=True)
def _interactive_by_default(monkeypatch):
    """Interactive-IDE mode throughout, so a stray ``HERCULES_RUNTIME_MODE`` in the runner
    environment cannot skew a notice; the headless half is proven in test_gate_surfaces.py."""
    monkeypatch.delenv("HERCULES_RUNTIME_MODE", raising=False)


@pytest.fixture
def project(tmp_path):
    """A project mid-build with one frozen test, and a throwaway home holding that state."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    (proj / FROZEN).write_text("def test_x():\n    assert True\n", encoding="utf-8")
    (home / ".hercules" / "state").mkdir(parents=True)
    (home / ".hercules" / "config.json").write_text(
        json.dumps({"projects": {"p": {"directory": str(proj), "state_file": "p.json"}}}), encoding="utf-8")
    (home / ".hercules" / "state" / "p.json").write_text(json.dumps({
        "active_session": "s1",
        "sessions": {"s1": {"current_phase": "build", "current_spec": "spec-1.md",
                            "current_spec_round": 1, "frozen_test_files": [FROZEN]}},
    }), encoding="utf-8")
    return home, proj


def _answer(cfg, evt, home, capsys, mode="") -> dict:
    """Run the gate and return what the tool would read, or {} when it said nothing."""
    gate.main(["hercules_gate.py", mode], stdin_text=json.dumps(evt), home=str(home), config=cfg)
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else {}


@pytest.mark.parametrize(("name", "cfg"), REPORTS_AFTER, ids=[n for n, _ in REPORTS_AFTER])
class TestAGateThatReportsAfterAWrite:
    """A gate told afterwards cannot prevent anything — so it must say so, and change nothing."""

    def test_it_speaks_up_about_a_frozen_test_that_was_written(self, name, cfg, project, capsys):
        home, proj = project
        (proj / FROZEN).write_text("def test_x():\n    assert False\n", encoding="utf-8")
        evt = {"file_path": str(proj / FROZEN), "workspace_roots": [str(proj)]}
        reply = _answer(cfg, evt, home, capsys, mode="after_edit")
        assert reply, f"{name} said nothing about a frozen test being written"

    def test_it_tells_both_the_person_and_the_agent_the_same_thing(self, name, cfg, project, capsys):
        """A person told nothing cannot undo the edit and an agent told nothing repeats it, so one
        wording reaches every key this host reads — including a host whose two keys are one key."""
        home, proj = project
        evt = {"file_path": str(proj / FROZEN), "workspace_roots": [str(proj)]}
        reply = _answer(cfg, evt, home, capsys, mode="after_edit")
        channels = {cfg["user_key"], cfg["agent_key"]}
        assert set(reply) == channels, f"{name}: the notice must reach exactly this host's channels"
        assert len({reply[key] for key in channels}) == 1, "one wording, every channel"
        assert "locked acceptance test" in reply[cfg["user_key"]]

    def test_it_stays_quiet_about_an_ordinary_file(self, name, cfg, project, capsys):
        home, proj = project
        evt = {"file_path": str(proj / "src" / "ordinary.py"), "workspace_roots": [str(proj)]}
        assert _answer(cfg, evt, home, capsys, mode="after_edit") == {}

    def test_it_stays_quiet_when_no_build_is_running(self, name, cfg, project, capsys):
        home, proj = project
        state = home / ".hercules" / "state" / "p.json"
        state.write_text(json.dumps({"active_session": "s1", "sessions": {"s1": {
            "current_phase": "design", "frozen_test_files": [FROZEN]}}}), encoding="utf-8")
        evt = {"file_path": str(proj / FROZEN), "workspace_roots": [str(proj)]}
        assert _answer(cfg, evt, home, capsys, mode="after_edit") == {}

    def test_it_stays_quiet_when_asked_about_an_event_it_has_no_answer_for(self, name, cfg, project, capsys):
        """An event with no protocol gets silence, never a guess — and never a notice about a file
        nobody wrote."""
        home, proj = project
        evt = {"file_path": str(proj / FROZEN), "workspace_roots": [str(proj)]}
        assert _answer(cfg, evt, home, capsys, mode="afterFileMoved") == {}

    def test_a_malformed_event_leaves_the_file_alone_and_says_nothing(self, name, cfg, project, capsys):
        """With no write to allow, failing open means silence — no notice, and nothing moved on disk."""
        home, proj = project
        before = (proj / FROZEN).read_bytes()
        gate.main(["hercules_gate.py", "after_edit"], stdin_text="{not json", home=str(home), config=cfg)
        assert capsys.readouterr().out.strip() == ""
        assert (proj / FROZEN).read_bytes() == before
