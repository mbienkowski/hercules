"""Behavioural tests for the G1 frozen-tests PreToolUse hook (plugin/hooks/frozen_tests.py).

These are *executable* guard tests (the hook actually runs), not prose-pins: a frozen-path
edit during a build must return exit code 2; everything else must return 0 and never raise.
The hook takes an explicit `home` so we point it at a throwaway ~/.hercules tree per test.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parents[2] / "plugin" / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))
from frozen_tests import main  # noqa: E402


def _setup(home: Path, project: Path, *, phase="build", frozen=("tests/test_login.py",),
           repositories=None, slug="proj", create=True):
    """Write a registry + state tree under `home/.hercules` for one project/session."""
    hh = home / ".hercules"
    (hh / "state").mkdir(parents=True, exist_ok=True)
    entry = {"directory": str(project), "docs_root": "docs", "state_file": f"{slug}.json"}
    if repositories:
        entry["repositories"] = {k: str(v) for k, v in repositories.items()}
    (hh / "config.json").write_text(json.dumps({"schema_version": 1, "projects": {slug: entry}}))
    session = {
        "current_phase": phase,
        "current_spec": "spec-02-login.md",
        "current_spec_round": 1,
        "frozen_test_files": list(frozen),
    }
    (hh / "state" / f"{slug}.json").write_text(
        json.dumps({"schema_version": 1, "active_session": "s1", "sessions": {"s1": session}})
    )
    if create:
        for f in frozen:
            p = project / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("def test_x():\n    assert True\n")


def _payload(project: Path, rel_or_abs, tool="Edit", cwd=None):
    fp = str(rel_or_abs if Path(str(rel_or_abs)).is_absolute() else project / rel_or_abs)
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": fp},
        "cwd": str(cwd or project),
    })


def test_blocks_edit_to_frozen_test_during_build(tmp_path, capsys):
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    code = main(_payload(project, "tests/test_login.py"), home=tmp_path)
    assert code == 2
    err = capsys.readouterr().err
    # The stderr reason is the model's ONLY feedback channel on a block — pin its full shape:
    # who blocked, which file, which spec and round, why, and both sanctioned exits.
    assert err.startswith("Hercules: "), "the reason must identify Hercules as the blocker"
    assert str(project / "tests/test_login.py") in err, "the reason must name the blocked file"
    assert "spec-02-login.md" in err, "the reason must name the owning spec"
    assert "(build round 1/3). Frozen tests are not edited during implementation" in err
    assert "acceptance criteria can't be weakened to force a pass" in err
    assert (
        "on the user's explicit instruction record a round-bound frozen_override "
        "(their words quoted) and retry in the same turn" in err
    ), "the reason must lead with the same-turn, user-granted exit"
    assert (
        'finish the round limit and choose "correct the test" to re-enter /hercules:design, '
        'or say "start fresh"' in err
    ), "the reason must spell out the round-limit exits verbatim"
    assert err.rstrip("\n").endswith('frozen_hook: "off" in the registry entry.'), \
        "the reason must close by naming the per-project opt-out, verbatim"


def test_allows_edit_to_non_frozen_file(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    assert main(_payload(project, "src/login.py"), home=tmp_path) == 0


def test_allows_when_phase_is_not_build(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project, phase="design")
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_allows_non_mutating_tool(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    assert main(_payload(project, "tests/test_login.py", tool="Read"), home=tmp_path) == 0


def test_blocks_real_multiedit_shape_on_frozen_file(tmp_path):
    """Real MultiEdit carries ONE top-level file_path shared by all edits."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    payload = json.dumps({
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": str(project / "tests/test_login.py"),
            "edits": [{"old_string": "assert True", "new_string": "assert 1"}],
        },
        "cwd": str(project),
    })
    assert main(payload, home=tmp_path) == 2


def test_blocks_notebook_edit_to_a_frozen_notebook(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_flow.ipynb",))
    payload = json.dumps({
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": str(project / "tests/test_flow.ipynb")},
        "cwd": str(project),
    })
    assert main(payload, home=tmp_path) == 2


def test_nested_project_roots_resolve_to_the_deepest(tmp_path):
    """A monorepo project and an inner service project both active: an edit inside the inner tree
    resolves to the INNER session, so its frozen test is caught (no first-match leak)."""
    outer = tmp_path / "mono"
    inner = outer / "svc"
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


def test_multi_service_frozen_path_is_matched(tmp_path):
    """A frozen test living under a `repositories.*` path is caught even when cwd differs."""
    project = tmp_path / "home"
    svc = tmp_path / "svc-auth"
    _setup(tmp_path, project, frozen=("tests/test_token.py",), repositories={"svc-auth": svc})
    (svc / "tests").mkdir(parents=True, exist_ok=True)
    (svc / "tests/test_token.py").write_text("def test_t():\n    assert True\n")
    payload = _payload(svc, svc / "tests/test_token.py", cwd=svc)
    assert main(payload, home=tmp_path) == 2


def test_fails_open_when_no_state(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    # no ~/.hercules at all
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_fails_open_on_unrelated_cwd(tmp_path):
    """Dogfooding / unrelated repo: cwd matches no project → pure passthrough."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    other = tmp_path / "elsewhere"
    other.mkdir()
    payload = _payload(other, other / "tests/test_login.py", cwd=other)
    assert main(payload, home=tmp_path) == 0


def test_never_crashes_on_malformed_state(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    hh = tmp_path / ".hercules"
    (hh / "state").mkdir(parents=True)
    (hh / "config.json").write_text("{ this is not json")
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_empty_stdin_allows(tmp_path):
    assert main("", home=tmp_path) == 0


def test_main_fails_open_on_malformed_stdin(tmp_path):
    assert main("this is not json {", home=tmp_path) == 0


def test_allows_when_frozen_list_is_empty(tmp_path):
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=())
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_blocks_write_tool_on_frozen_file(tmp_path):
    """Write can clobber a frozen test wholesale — it must be guarded like Edit."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    assert main(_payload(project, "tests/test_login.py", tool="Write"), home=tmp_path) == 2


def test_blocks_per_edit_file_path_shape(tmp_path):
    """The defensive per-edit `edits[].file_path` shape (no top-level file_path) is honoured."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    payload = json.dumps({
        "tool_name": "MultiEdit",
        "tool_input": {"edits": [{"file_path": str(project / "tests/test_login.py")}]},
        "cwd": str(project),
    })
    assert main(payload, home=tmp_path) == 2


def test_reason_falls_back_when_spec_fields_missing(tmp_path, capsys):
    """A build session without current_spec/current_spec_round still blocks, with readable
    fallbacks in the reason ('the current spec', round '?')."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    session = state["sessions"]["s1"]
    del session["current_spec"], session["current_spec_round"]
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2
    err = capsys.readouterr().err
    # Boundary-anchored: the fallback must sit exactly where the spec name would ("for {spec} (")
    assert "is a frozen test for the current spec (build round ?/3)" in err


def test_decide_allow_paths_return_an_empty_reason(tmp_path, monkeypatch):
    """Every allow path returns exactly (0, "") — an allow must never carry a stray reason a
    future caller could print."""
    import frozen_tests as ft

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    read = json.loads(_payload(project, "tests/test_login.py", tool="Read"))
    assert ft.decide(read, home=tmp_path) == (0, "")                      # non-mutating tool
    other = json.loads(_payload(project, "src/login.py"))
    assert ft.decide(other, home=tmp_path) == (0, "")                     # non-frozen target
    _setup(tmp_path, project, phase="design")
    frozen = json.loads(_payload(project, "tests/test_login.py"))
    assert ft.decide(frozen, home=tmp_path) == (0, "")                    # phase != build
    _setup(tmp_path, project, frozen=())
    assert ft.decide(frozen, home=tmp_path) == (0, "")                    # empty frozen list

    def _boom(*_a, **_k):
        raise RuntimeError("resolver exploded")

    monkeypatch.setattr(ft, "resolve_session", _boom)
    assert ft.decide(frozen, home=tmp_path) == (0, "")                    # exception path


def test_blocks_first_of_multiple_frozen_files(tmp_path):
    """Frozen candidates accumulate across ALL entries — a match on any earlier entry blocks
    (a last-entry-wins bug would let every other frozen file through)."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_a.py", "tests/test_b.py"))
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 2


def test_whitespace_stdin_is_never_parsed_as_json(tmp_path, monkeypatch):
    """Blank stdin short-circuits before json.loads — the parser must not see whitespace."""
    import frozen_tests as ft

    calls = []

    def _spy(raw):
        calls.append(raw)
        raise ValueError("should not be reached")

    monkeypatch.setattr(ft.json, "loads", _spy)
    assert ft.main("   \n", home=tmp_path) == 0
    assert calls == [], "whitespace-only stdin must never reach json.loads"


def test_hook_runs_as_a_script_end_to_end(tmp_path):
    """The real deployment shape: `python3 frozen_tests.py` with a PreToolUse payload on stdin
    and HOME pointing at the state tree — frozen edit exits 2, non-frozen exits 0."""
    import subprocess

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    script = _HOOKS_DIR / "frozen_tests.py"
    env = {**os.environ, "HOME": str(tmp_path)}
    blocked = subprocess.run(
        [sys.executable, str(script)], input=_payload(project, "tests/test_login.py"),
        capture_output=True, text=True, env=env,
    )
    assert blocked.returncode == 2 and "Hercules:" in blocked.stderr
    allowed = subprocess.run(
        [sys.executable, str(script)], input=_payload(project, "src/login.py"),
        capture_output=True, text=True, env=env,
    )
    assert allowed.returncode == 0


def test_hook_imports_its_own_state_resolver_first(tmp_path):
    """frozen_tests.py must put its own directory at the FRONT of sys.path — a same-named
    hercules_state module earlier on the path must never shadow the real resolver."""
    import importlib.util

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    decoy_dir = tmp_path / "decoy"
    decoy_dir.mkdir()
    (decoy_dir / "hercules_state.py").write_text(
        "def canon(p):\n    return str(p)\n"
        "def resolve_session(cwd, home=None):\n    return None, [], None\n"
        "def frozen_candidates(entry, roots):\n    return set()\n"
    )
    saved_modules = {k: sys.modules.pop(k) for k in ("hercules_state",) if k in sys.modules}
    saved_path = list(sys.path)
    try:
        sys.path.insert(0, str(decoy_dir))
        spec = importlib.util.spec_from_file_location(
            "frozen_tests_fresh", _HOOKS_DIR / "frozen_tests.py"
        )
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        assert fresh.main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2, (
            "the hook resolved the decoy hercules_state instead of its own"
        )
    finally:
        sys.path[:] = saved_path
        sys.modules.pop("hercules_state", None)
        sys.modules.update(saved_modules)


def test_registry_iteration_skips_unrelated_projects(tmp_path):
    """An unrelated project listed BEFORE the matching one must be skipped, not end the scan."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"] = {
        "elsewhere": {"directory": str(tmp_path / "elsewhere"), "state_file": "elsewhere.json"},
        **cfg["projects"],
    }
    (hh / "config.json").write_text(json.dumps(cfg))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_custom_state_file_pointer_is_honoured(tmp_path):
    """A registry entry's explicit state_file (≠ {slug}.json) is the one that gets read."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"]["proj"]["state_file"] = "custom.json"
    (hh / "config.json").write_text(json.dumps(cfg))
    (hh / "state" / "proj.json").rename(hh / "state" / "custom.json")
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_state_file_defaults_to_slug_json(tmp_path):
    """An entry without a state_file pointer falls back to state/{slug}.json."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    del cfg["projects"]["proj"]["state_file"]
    (hh / "config.json").write_text(json.dumps(cfg))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_sessionless_entry_does_not_mask_a_matching_build(tmp_path):
    """A matching project whose state has no active session is skipped; a later matching
    entry with a live build still blocks."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"] = {
        "ghost": {"directory": str(project), "state_file": "ghost.json"},
        **cfg["projects"],
    }
    (hh / "config.json").write_text(json.dumps(cfg))
    (hh / "state" / "ghost.json").write_text(json.dumps({"sessions": {}}))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_malformed_sibling_state_does_not_mask_a_matching_build(tmp_path):
    """A matching entry with corrupt state is skipped; the scan continues to the valid one."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"] = {
        "broken": {"directory": str(project), "state_file": "broken.json"},
        **cfg["projects"],
    }
    (hh / "config.json").write_text(json.dumps(cfg))
    (hh / "state" / "broken.json").write_text("{ not json")
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_build_session_wins_over_non_build_at_the_same_root(tmp_path):
    """Two projects registered on the SAME directory — one designing, one building. The build
    session must be selected (the design one would fail open and disarm the guard)."""
    project = tmp_path / "proj"
    # design entry inserted FIRST so a broken tiebreak (stable sort on equal keys) picks it
    _setup(tmp_path, project, slug="designer", phase="design")
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"]["builder"] = {"directory": str(project), "state_file": "builder.json"}
    (hh / "config.json").write_text(json.dumps(cfg))
    (hh / "state" / "builder.json").write_text(json.dumps({
        "active_session": "s1",
        "sessions": {"s1": {"current_phase": "build", "current_spec": "spec-02-login.md",
                             "current_spec_round": 1,
                             "frozen_test_files": ["tests/test_login.py"]}},
    }))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_frozen_entry_blocks_even_before_the_file_exists(tmp_path):
    """Fail-closed direction: a recorded frozen path is guarded even if nothing exists on disk
    yet (e.g. a Write that would create it mid-build)."""
    project = tmp_path / "proj"
    project.mkdir(parents=True, exist_ok=True)
    _setup(tmp_path, project, create=False)
    assert main(_payload(project, "tests/test_login.py", tool="Write"), home=tmp_path) == 2


def _grant(home: Path, *, files, round_=1, spec="spec-02-login.md", slug="proj", extra=None):
    """Record a frozen_override into the session, the way the orchestrator would."""
    state_path = home / ".hercules" / "state" / f"{slug}.json"
    state = json.loads(state_path.read_text())
    ov = {"files": files, "spec": spec, "round": round_,
          "reason": "user: 'the expected status is 201 not 200 — fix the test'"}
    if extra is not None:
        ov = extra
    state["sessions"]["s1"]["frozen_override"] = ov
    state_path.write_text(json.dumps(state))


def test_override_allows_edit_to_named_frozen_file_in_matching_round(tmp_path):
    """The user's explicit grant unblocks the named file, in the same round, no ceremony."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=["tests/test_login.py"])
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_override_allow_path_returns_an_empty_reason(tmp_path):
    import frozen_tests as ft

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=["tests/test_login.py"])
    payload = json.loads(_payload(project, "tests/test_login.py"))
    assert ft.decide(payload, home=tmp_path) == (0, "")


def test_override_with_stale_round_still_blocks(tmp_path):
    """Round advance is the override's machine expiry — a stale grant never re-validates."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=["tests/test_login.py"], round_=2)  # session round is 1
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_override_for_another_spec_still_blocks(tmp_path):
    """A grant left over from a different spec (round counters reset at retire) never leaks."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=["tests/test_login.py"], spec="spec-01-schema.md")
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_override_scopes_to_named_files_only(tmp_path):
    """A grant for file A must never disarm frozen file B — same state, both directions."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_a.py", "tests/test_b.py"))
    _grant(tmp_path, files=["tests/test_a.py"])
    assert main(_payload(project, "tests/test_b.py"), home=tmp_path) == 2
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 0


def test_override_covers_multiple_granted_files(tmp_path):
    """Grants accumulate across the files list — the first entry works, not just the last."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_a.py", "tests/test_b.py"))
    _grant(tmp_path, files=["tests/test_a.py", "tests/test_b.py"])
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 0
    assert main(_payload(project, "tests/test_b.py"), home=tmp_path) == 0


@pytest.mark.parametrize("bad", [
    "yes",                                              # not a dict
    {"files": "tests/test_login.py", "round": 1, "spec": "spec-02-login.md"},  # files not a list
    {"round": 1, "spec": "spec-02-login.md"},           # files missing
    {"files": ["tests/test_login.py"], "spec": "spec-02-login.md"},            # round missing
    {"files": [], "round": 1, "spec": "spec-02-login.md"},                     # empty files
    {"files": [None, 123], "round": 1, "spec": "spec-02-login.md"},            # junk entries
    {"files": ["tests/test_login.py"], "round": "1", "spec": "spec-02-login.md"},  # str round
])
def test_malformed_override_still_blocks(tmp_path, bad):
    """The override fails CLOSED: anything malformed leaves the block standing."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=[], extra=bad)
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_override_junk_entries_do_not_poison_a_valid_grant(tmp_path):
    """Junk file entries are skipped, never fatal — the valid entry in the same grant works."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=[123, "tests/test_login.py"])
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_opt_out_allow_path_returns_an_empty_reason(tmp_path):
    import frozen_tests as ft

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"]["proj"]["frozen_hook"] = "off"
    (hh / "config.json").write_text(json.dumps(cfg))
    payload = json.loads(_payload(project, "tests/test_login.py"))
    assert ft.decide(payload, home=tmp_path) == (0, "")


def test_override_round_null_on_roundless_session_blocks(tmp_path):
    """None == None must never validate — the grant requires an explicit integer round."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    del state["sessions"]["s1"]["current_spec_round"]
    state["sessions"]["s1"]["frozen_override"] = {
        "files": ["tests/test_login.py"], "spec": "spec-02-login.md", "round": None}
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_override_helper_fails_closed_when_candidates_raise(tmp_path, monkeypatch):
    """A raising resolver inside the override parser must block, never disarm the guard."""
    import frozen_tests as ft

    project = tmp_path / "proj"
    _setup(tmp_path, project)

    class _Boom(dict):
        def get(self, *_a, **_k):
            raise RuntimeError("session exploded")

    assert ft._override_allows(_Boom(), [], "x") is False


def test_override_end_to_end_as_a_script(tmp_path):
    """Real deployment shape: with a recorded grant the script exits 0 on the granted file."""
    import subprocess

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=["tests/test_login.py"])
    env = {**os.environ, "HOME": str(tmp_path)}
    run = subprocess.run(
        [sys.executable, str(_HOOKS_DIR / "frozen_tests.py")],
        input=_payload(project, "tests/test_login.py"), capture_output=True, text=True, env=env,
    )
    assert run.returncode == 0


def test_frozen_hook_off_opt_out_allows_everything(tmp_path):
    """The per-project opt-out (`frozen_hook: "off"`) switches to prompt-only discipline."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"]["proj"]["frozen_hook"] = "off"
    (hh / "config.json").write_text(json.dumps(cfg))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


@pytest.mark.parametrize("value", ["on", "OFF", "", None, True, 0])
def test_frozen_hook_other_values_keep_the_guard_armed(tmp_path, value):
    """Only the literal "off" disarms; absent or junk values keep the block."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    if value is not None:
        cfg["projects"]["proj"]["frozen_hook"] = value
    (hh / "config.json").write_text(json.dumps(cfg))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_decide_fails_open_if_resolver_raises(tmp_path, monkeypatch):
    """Last-resort guard: even if the resolver blows up, never block a user's edit."""
    import frozen_tests as ft

    def _boom(*_a, **_k):
        raise RuntimeError("resolver exploded")

    monkeypatch.setattr(ft, "resolve_session", _boom)
    payload = json.dumps({
        "tool_name": "Edit",
        "tool_input": {"file_path": "/x/tests/test_login.py"},
        "cwd": "/x",
    })
    assert ft.main(payload, home=tmp_path) == 0


def test_paused_build_session_stays_guarded_when_active_session_moves_on(tmp_path):
    """Discover for feature B flips active_session; feature A's build (frozen files, phase
    'build') must STILL block edits to its frozen tests — the guard must not hinge on the
    single active_session pointer (multi-session is an advertised flow)."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    state["sessions"]["s2"] = {"current_phase": "discover", "tier": "low"}
    state["sessions"]["junk"] = "not-a-dict"
    state["active_session"] = "s2"
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_deeper_non_build_project_cannot_shadow_an_outer_active_build(tmp_path):
    """A registry entry for an inner directory (idle, phase discover) must not shadow the
    outer project's ACTIVE BUILD that froze a file inside that inner tree — a build session
    outranks a non-build one regardless of registry depth."""
    outer = tmp_path / "mono"
    inner = outer / "svc"
    _setup(tmp_path, outer, slug="outer", frozen=("svc/tests/test_x.py",))
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"]["inner"] = {"directory": str(inner), "state_file": "inner.json"}
    (hh / "config.json").write_text(json.dumps(cfg))
    (hh / "state" / "inner.json").write_text(json.dumps({
        "active_session": "s", "sessions": {"s": {"current_phase": "discover", "tier": "low"}}}))
    assert main(_payload(inner, inner / "tests/test_x.py", cwd=inner), home=tmp_path) == 2


def test_state_file_pointer_cannot_escape_the_state_dir(tmp_path):
    """A state_file value like ../../evil.json must be ignored (fail-open), never read —
    the documented read scope is ~/.hercules only."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    evil = tmp_path / "evil.json"
    evil.write_text((hh / "state" / "proj.json").read_text())
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"]["proj"]["state_file"] = "../../evil.json"
    (hh / "config.json").write_text(json.dumps(cfg))
    (hh / "state" / "proj.json").unlink()
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_undecodable_stdin_fails_open_without_a_traceback(tmp_path):
    """Invalid UTF-8 on stdin must exit 0 with no traceback — 'never raises' includes the read."""
    import subprocess

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    env = {**os.environ, "HOME": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    run = subprocess.run(
        [sys.executable, str(_HOOKS_DIR / "frozen_tests.py")],
        input=b"\xff\xfe{bad", capture_output=True, env=env,
    )
    assert run.returncode == 0
    assert b"Traceback" not in run.stderr


def test_escaping_pointer_skips_only_that_project(tmp_path):
    """One project with a traversal state_file must be skipped, not end the registry scan —
    a later matching project with a live build still blocks."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"] = {
        "evil": {"directory": str(project), "state_file": "../../evil.json"},
        **cfg["projects"],
    }
    (hh / "config.json").write_text(json.dumps(cfg))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_active_build_session_outranks_other_build_sessions(tmp_path):
    """With two build sessions in one file, the ACTIVE one is authoritative — the fallback scan
    is only for when the active session is not building. An edit frozen only in the non-active
    build session is allowed; the active session's own frozen file still blocks."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_a.py",))
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    other = {"current_phase": "build", "current_spec": "spec-09-other.md",
             "current_spec_round": 1, "frozen_test_files": ["tests/test_b.py"]}
    state["sessions"] = {"s0": other, "s1": state["sessions"]["s1"]}  # non-active build FIRST
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    (project / "tests" / "test_b.py").write_text("def test_b():\n    assert True\n")
    assert main(_payload(project, "tests/test_b.py"), home=tmp_path) == 0
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 2


def test_fallback_scan_survives_junk_sessions_listed_first(tmp_path):
    """When the active session is gone and a junk (non-dict) session precedes the paused build
    in the file, the fallback must skip the junk and still find the build session."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    state["sessions"] = {"junk": "not-a-dict", "s1": state["sessions"]["s1"]}
    state["active_session"] = "gone"
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_importing_the_hook_module_has_no_side_effects(tmp_path):
    """Importing frozen_tests must never run main() — the __main__ guard is load-bearing:
    a module-level sys.exit would abort any tool that imports the hook for reuse."""
    import subprocess

    run = subprocess.run(
        [sys.executable, "-c", "import frozen_tests; print('IMPORT_OK')"],
        cwd=str(_HOOKS_DIR), input="", capture_output=True, text=True,
    )
    assert run.returncode == 0
    assert "IMPORT_OK" in run.stdout, "import must reach the end of the probe — no exit in between"
