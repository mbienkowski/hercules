"""Frozen-tests hook, MAIN behaviours: block a tampered edit, allow an ordinary one, an override
lifts the block, breakage fails open, multi-project resolution finds the right session, and the
retire-time drift check catches tampering the tool-time hook never saw. Corner cases deliberately
left elsewhere: ``docs/analysis-2026-08/dropped-hook-test-classes.md``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from frozen_tests import frozen_drift
from hercules_state import canon
from tests.scripts.hooks.conftest import (
    FROZEN_TEST, SPEC, _HOOKS_DIR, _grant, _payload, _setup,
    build_project, main, run_hook,
)

def test_blocked_edit_message_tells_user_exactly_how_to_proceed(tmp_path, capsys):
    """Stderr is the model's only feedback channel, so it names the blocker, the spec, and all three
    exits — never fusing the safe "fix the test" option with the destructive "start over" reset."""
    project = build_project(tmp_path)
    assert run_hook(project, FROZEN_TEST, home=tmp_path) == 2
    reason = capsys.readouterr().err
    assert reason.startswith("Hercules: ") and SPEC in reason
    assert 'User: saying "change this test' in reason
    assert "frozen_override" in reason and 'frozen_hook: "off"' in reason
    assert "start fresh" not in reason
    assert 'correct the test" to re-enter' not in reason

@pytest.mark.parametrize("shape", ["multi_edit_bundled", "full_overwrite"])
def test_a_frozen_test_is_blocked_whatever_shape_the_edit_request_takes(tmp_path, shape):
    """Tampering must not slip through a request shape the path check was not written for."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    if shape == "multi_edit_bundled":
        payload = json.dumps({
            "tool_name": "MultiEdit",
            "tool_input": {"file_path": str(project / FROZEN_TEST),
                            "edits": [{"old_string": "assert True", "new_string": "assert 1"}]},
            "cwd": str(project),
        })
    else:
        payload = _payload(project, FROZEN_TEST, tool="Write")
    assert main(payload, home=tmp_path) == 2

@pytest.mark.parametrize("case", [
    "non_mutating_tool", "non_frozen_target", "phase_not_build",
    "empty_frozen_list", "project_opt_out",
])
def test_every_situation_that_permits_the_edit_gives_no_leftover_block_reason(tmp_path, case):
    """Every permitting case decides EXACTLY ``(0, "")`` — never a stray printable reason."""
    import frozen_tests as ft

    project = tmp_path / "proj"
    if case == "non_mutating_tool":
        _setup(tmp_path, project)
        payload = json.loads(_payload(project, FROZEN_TEST, tool="Read"))
    elif case == "non_frozen_target":
        _setup(tmp_path, project)
        payload = json.loads(_payload(project, "src/login.py"))
    elif case == "phase_not_build":
        _setup(tmp_path, project, phase="design")
        payload = json.loads(_payload(project, FROZEN_TEST))
    elif case == "empty_frozen_list":
        _setup(tmp_path, project, frozen=())
        payload = json.loads(_payload(project, FROZEN_TEST))
    else:
        _setup(tmp_path, project)
        cfg_path = tmp_path / ".hercules" / "config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["projects"]["proj"]["frozen_hook"] = "off"
        cfg_path.write_text(json.dumps(cfg))
        payload = json.loads(_payload(project, FROZEN_TEST))
    assert ft.decide(payload, home=tmp_path) == (0, "")

def test_the_guard_works_when_run_as_the_real_deployed_program(tmp_path):
    """A standalone program fed a real request, exactly as Hercules deploys it."""
    import subprocess

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    script = _HOOKS_DIR / "frozen_tests.py"
    env = {**os.environ, "HOME": str(tmp_path)}
    blocked = subprocess.run([sys.executable, str(script)], input=_payload(project, FROZEN_TEST),
                              capture_output=True, text=True, env=env)
    assert blocked.returncode == 2 and "Hercules:" in blocked.stderr
    allowed = subprocess.run([sys.executable, str(script)], input=_payload(project, "src/login.py"),
                              capture_output=True, text=True, env=env)
    assert allowed.returncode == 0

def test_override_allows_edit_to_named_frozen_file_in_matching_round(tmp_path):
    """An approved exception goes through without formally unfreezing the file."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=[FROZEN_TEST])
    assert main(_payload(project, FROZEN_TEST), home=tmp_path) == 0

@pytest.mark.parametrize("grant_kwargs", [
    {"round_": 2}, {"spec": "spec-01-schema.md"},
], ids=["mismatched_round", "mismatched_spec"])
def test_editing_a_frozen_file_stays_blocked_when_the_grant_does_not_match_the_session(tmp_path, grant_kwargs):
    """A grant never carries forward past the round and spec it was recorded for."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=[FROZEN_TEST], **grant_kwargs)
    assert main(_payload(project, FROZEN_TEST), home=tmp_path) == 2

@pytest.mark.parametrize("bad", [
    "yes",
    {"round": 1, "spec": SPEC},
    {"files": [], "round": 1, "spec": SPEC},
    {"files": [FROZEN_TEST], "spec": SPEC},
    {"files": [FROZEN_TEST], "round": 1, "spec": SPEC},                 # reason missing
    {"files": [FROZEN_TEST], "round": 1, "spec": SPEC, "reason": "  "},  # reason blank
], ids=["not_a_dict", "files_missing", "empty_files", "round_missing", "reason_missing", "reason_blank"])
def test_a_broken_or_incomplete_grant_leaves_the_file_protected(tmp_path, bad):
    """Broken data is never read as an explicit approval."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=[], extra=bad)
    assert main(_payload(project, FROZEN_TEST), home=tmp_path) == 2

def test_a_grant_for_one_file_does_not_unblock_a_different_frozen_file(tmp_path):
    """A grant covers only the exact files named, checked in both directions."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_a.py", "tests/test_b.py"))
    _grant(tmp_path, files=["tests/test_a.py"])
    assert main(_payload(project, "tests/test_b.py"), home=tmp_path) == 2
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 0

@pytest.mark.parametrize("value", ["off", "on", "OFF", None])
def test_only_the_exact_off_setting_disables_the_frozen_file_guard(tmp_path, value):
    """A typo, a different capitalization, or nothing set all leave the guard active."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    if value is not None:
        cfg["projects"]["proj"]["frozen_hook"] = value
    (hh / "config.json").write_text(json.dumps(cfg))
    expected = 0 if value == "off" else 2
    assert main(_payload(project, FROZEN_TEST), home=tmp_path) == expected

@pytest.mark.parametrize("case", [
    "no_state", "not_a_project", "corrupted_state", "empty_input", "unparseable_input",
    "resolver_explodes", "override_check_explodes",
])
def test_the_guard_allows_the_edit_when_something_is_broken(tmp_path, monkeypatch, case):
    """The safe default is to allow — never to crash, and never to block."""
    import frozen_tests as ft

    project = tmp_path / "proj"
    if case == "no_state":
        project.mkdir()
        assert main(_payload(project, FROZEN_TEST), home=tmp_path) == 0
    elif case == "not_a_project":
        _setup(tmp_path, project)
        other = tmp_path / "elsewhere"
        other.mkdir()
        assert main(_payload(other, other / "tests/test_login.py", cwd=other), home=tmp_path) == 0
    elif case == "corrupted_state":
        project.mkdir()
        (tmp_path / ".hercules" / "state").mkdir(parents=True)
        (tmp_path / ".hercules" / "config.json").write_text("{ this is not json")
        assert main(_payload(project, FROZEN_TEST), home=tmp_path) == 0
    elif case == "empty_input":
        assert main("", home=tmp_path) == 0
    elif case == "unparseable_input":
        assert main("this is not json {", home=tmp_path) == 0
    elif case == "resolver_explodes":
        project = build_project(tmp_path)
        payload = json.loads(_payload(project, FROZEN_TEST))
        monkeypatch.setattr(ft, "resolve_build_contexts", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        assert ft.decide(payload, home=tmp_path) == (0, "")
    else:
        class _Boom(dict):
            def get(self, *_a, **_k):
                raise RuntimeError("session exploded")
        assert ft._override_allows(_Boom(), [], "x") is False

def test_garbled_input_never_crashes_or_blocks_the_users_work(tmp_path):
    """Genuinely corrupted bytes on real stdin: the deployed script exits clean, with no traceback."""
    import subprocess

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    env = {**os.environ, "HOME": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    run = subprocess.run([sys.executable, str(_HOOKS_DIR / "frozen_tests.py")],
                          input=b"\xff\xfe{bad", capture_output=True, env=env)
    assert run.returncode == 0 and b"Traceback" not in run.stderr

def test_an_edit_inside_a_nested_service_is_attributed_to_that_service(tmp_path, monorepo):
    """An inner service is checked against its OWN frozen tests, not the outer project's."""
    outer, inner = monorepo
    _setup(tmp_path, outer, slug="outer", frozen=("tests/a.py",))
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"]["inner"] = {"directory": str(inner), "state_file": "inner.json"}
    (hh / "config.json").write_text(json.dumps(cfg))
    (hh / "state" / "inner.json").write_text(json.dumps({
        "active_session": "s",
        "sessions": {"s": {"current_phase": "build", "current_spec": "spec-b",
                            "current_spec_round": 1, "frozen_test_files": ["tests/b.py"]}},
    }))
    (inner / "tests").mkdir(parents=True, exist_ok=True)
    (inner / "tests/b.py").write_text("def test_b():\n    assert True\n")
    assert main(_payload(inner, inner / "tests/b.py", cwd=inner), home=tmp_path) == 2

def test_a_frozen_test_in_another_repository_is_still_caught(tmp_path):
    """Blocked from a different cwd, in a separately referenced repository."""
    project, svc = tmp_path / "home", tmp_path / "svc-auth"
    _setup(tmp_path, project, frozen=("tests/test_token.py",), repositories={"svc-auth": svc})
    (svc / "tests").mkdir(parents=True, exist_ok=True)
    (svc / "tests/test_token.py").write_text("def test_t():\n    assert True\n")
    assert main(_payload(svc, svc / "tests/test_token.py", cwd=svc), home=tmp_path) == 2

def test_an_unrelated_project_listed_first_does_not_stop_the_search(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"] = {"elsewhere": {"directory": str(tmp_path / "elsewhere"),
                                      "state_file": "elsewhere.json"}, **cfg["projects"]}
    (hh / "config.json").write_text(json.dumps(cfg))
    assert main(_payload(project, FROZEN_TEST), home=tmp_path) == 2

def test_a_projects_custom_state_file_location_is_respected(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"]["proj"]["state_file"] = "custom.json"
    (hh / "config.json").write_text(json.dumps(cfg))
    (hh / "state" / "proj.json").rename(hh / "state" / "custom.json")
    assert main(_payload(project, FROZEN_TEST), home=tmp_path) == 2

def test_an_active_build_is_chosen_over_a_design_session_in_the_same_folder(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project, slug="designer", phase="design")
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"]["builder"] = {"directory": str(project), "state_file": "builder.json"}
    (hh / "config.json").write_text(json.dumps(cfg))
    (hh / "state" / "builder.json").write_text(json.dumps({
        "active_session": "s1",
        "sessions": {"s1": {"current_phase": "build", "current_spec": SPEC,
                             "current_spec_round": 1, "frozen_test_files": [FROZEN_TEST]}},
    }))
    assert main(_payload(project, FROZEN_TEST), home=tmp_path) == 2

def test_a_monorepo_and_its_inner_service_can_both_be_mid_build_and_stay_guarded(tmp_path, monorepo):
    """Both freezes bite from the inner working directory; one build does not mask the other."""
    mono, svc = monorepo
    _setup(tmp_path, mono, slug="mono", frozen=["svc/tests/test_x.py"], merge=True)
    _setup(tmp_path, svc, slug="svc", frozen=["tests/test_y.py"], merge=True)
    assert main(_payload(svc, "tests/test_y.py"), home=tmp_path) == 2
    assert main(_payload(svc, str(svc / "tests" / "test_x.py"), cwd=svc), home=tmp_path) == 2

def test_a_relative_file_path_is_resolved_against_the_editors_working_directory(tmp_path, monkeypatch):
    """The editor's declared `cwd` decides, never the guard process's own."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    monkeypatch.chdir(tmp_path)
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": FROZEN_TEST},
                          "cwd": str(project)})
    assert main(payload, home=tmp_path) == 2

def test_file_path_comparisons_are_case_insensitive_only_on_macos(monkeypatch):
    """A default Mac treats differently-cased paths as one file; Linux does not."""
    import hercules_state as hs

    monkeypatch.setattr(hs.sys, "platform", "darwin")
    assert hs.canon("/Foo/Test_Login.py") == hs.canon("/foo/test_login.py")
    monkeypatch.setattr(hs.sys, "platform", "linux")
    assert hs.canon("/Foo/Test_Login.py") != hs.canon("/foo/test_login.py")

def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _freeze(proj, rel: str, content: str) -> str:
    p = proj / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return _sha(content)

@pytest.mark.parametrize("case", [
    "matches_baseline", "tampered_is_reported", "sanctioned_override_is_not_drift", "deleted_fails_closed",
])
def test_frozen_drift_catches_tampering_the_tool_time_hook_never_saw(tmp_path, case):
    """The retire-time backstop re-hashes each frozen test; a sanctioned override is not drift, and a
    DELETED acceptance test fails closed exactly like a weakened one."""
    proj = tmp_path / "proj"
    override = None
    if case == "matches_baseline":
        h = _freeze(proj, "tests/test_frozen.py", "def test_x():\n    assert real()\n")
        expected = []
    elif case == "tampered_is_reported":
        h = _freeze(proj, "tests/test_frozen.py", "def test_x():\n    assert real()\n")
        (proj / "tests" / "test_frozen.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
        expected = ["tests/test_frozen.py"]
    elif case == "sanctioned_override_is_not_drift":
        h = _freeze(proj, "tests/test_frozen.py", "def test_x():\n    assert status == 200\n")
        (proj / "tests" / "test_frozen.py").write_text("def test_x():\n    assert status == 201\n",
                                                         encoding="utf-8")
        override = {"files": ["tests/test_frozen.py"], "spec": "spec-1.md", "round": 1,
                    "reason": "user: 'the expected status is 201 not 200 — fix the test'"}
        expected = []
    else:
        h = _freeze(proj, "tests/test_frozen.py", "def test_x():\n    assert real()\n")
        (proj / "tests" / "test_frozen.py").unlink()
        expected = ["tests/test_frozen.py"]
    session = {"current_phase": "build", "current_spec": "spec-1.md", "current_spec_round": 1,
               "frozen_test_files": ["tests/test_frozen.py"], "frozen_baseline": {"tests/test_frozen.py": h}}
    if override is not None:
        session["frozen_override"] = override
    assert frozen_drift(session, [canon(str(proj))]) == expected


def test_the_guard_loads_its_own_state_reader_even_when_a_decoy_shadows_it(fresh_hook_over_decoy_state):
    """The hook runs from wherever the host launched it, and importing a stranger's ``hercules_state``
    would find no frozen files and allow every write, silently — so it front-loads its own directory."""
    fresh = fresh_hook_over_decoy_state
    loaded = sys.modules["hercules_state"].__file__
    assert loaded is not None
    assert Path(loaded).parent == _HOOKS_DIR, (
        f"the guard imported hercules_state from {loaded} — the decoy shadowed the real one")
    # The decoy defines no resolve_build_contexts, so this names the real reader, not merely something.
    assert callable(fresh.resolve_build_contexts)
