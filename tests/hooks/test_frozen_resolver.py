"""Frozen-tests hook — build-context resolution: nesting, multi-service, ordering, fallback."""

from __future__ import annotations

import json
import sys

from tests.hooks.conftest import _add_project, _payload, _setup, main


def canonical_in(roots, project):
    import hercules_state as hs
    return hs.canon(project) in roots


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


def test_all_build_sessions_keep_their_guards(tmp_path, capsys):
    """With two build sessions in one file, BOTH freezes hold — a paused build's frozen
    tests are still frozen deliverables of a pending spec. The ACTIVE session stays
    authoritative for attribution: its own frozen file is blocked under its spec's name."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_a.py",))
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    other = {"current_phase": "build", "current_spec": "spec-09-other.md",
             "current_spec_round": 1, "frozen_test_files": ["tests/test_b.py"]}
    state["sessions"] = {"s0": other, "s1": state["sessions"]["s1"]}  # non-active build FIRST
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    (project / "tests" / "test_b.py").write_text("def test_b():\n    assert True\n")
    assert main(_payload(project, "tests/test_b.py"), home=tmp_path) == 2
    capsys.readouterr()
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 2
    assert "spec-02-login.md" in capsys.readouterr().err, \
        "the active session's own frozen file is attributed to the active spec"


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


def test_nested_projects_in_build_are_both_guarded(tmp_path):
    """A monorepo project and an inner service project can both be mid-build; the outer
    build's frozen file living inside the inner tree must stay guarded even when cwd
    resolves to the inner project — the guard unions all matching build sessions."""
    mono = tmp_path / "mono"
    svc = mono / "svc"
    _add_project(tmp_path, mono, "mono", frozen=["svc/tests/test_x.py"])
    _add_project(tmp_path, svc, "svc", frozen=["tests/test_y.py"])
    assert main(_payload(svc, "tests/test_y.py"), home=tmp_path) == 2
    assert main(_payload(svc, str(svc / "tests" / "test_x.py"), cwd=svc), home=tmp_path) == 2


def test_two_projects_sharing_a_directory_are_both_guarded(tmp_path):
    """Two registry entries can point at the same directory (e.g. re-registered under a
    second slug); the one dict order disfavours must not fail open."""
    project = tmp_path / "proj"
    _add_project(tmp_path, project, "alpha", frozen=["tests/test_a.py"])
    _add_project(tmp_path, project, "beta", frozen=["tests/test_b.py"])
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 2
    assert main(_payload(project, "tests/test_b.py"), home=tmp_path) == 2


def test_one_malformed_frozen_entry_does_not_disarm_the_rest(tmp_path):
    """Junk elements in frozen_test_files (int, empty, None) are skipped per-item — they
    must never explode the frozen-set computation and fail the valid entries open."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    state["sessions"]["s1"]["frozen_test_files"] = ["tests/test_login.py", 123, "", None]
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_missing_frozen_file_is_guarded_under_every_root(tmp_path):
    """A frozen file with nothing on disk (deleted mid-build, or not yet created) must be
    guarded against creation under EVERY project root, not only the first — otherwise a
    Write under a repositories.* root recreates it unchecked."""
    project = tmp_path / "proj"
    svc = tmp_path / "svc-auth"
    svc.mkdir()
    _setup(tmp_path, project, frozen=("tests/test_token.py",),
           repositories={"svc-auth": svc}, create=False)
    assert main(_payload(project, "tests/test_token.py", tool="Write"), home=tmp_path) == 2
    assert main(_payload(project, str(svc / "tests" / "test_token.py"), tool="Write"),
                home=tmp_path) == 2


def test_paused_builds_are_both_guarded_regardless_of_order(tmp_path):
    """Active session in discover, TWO paused builds in the file: both paused builds'
    frozen files stay guarded — not whichever one JSON key order happens to yield."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_a.py",))
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    b_b = {"current_phase": "build", "current_spec": "spec-09.md", "current_spec_round": 1,
           "frozen_test_files": ["tests/test_b.py"]}
    state["sessions"] = {"bA": state["sessions"]["s1"], "bB": b_b,
                         "d": {"current_phase": "discover"}}
    state["active_session"] = "d"
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    (project / "tests" / "test_b.py").write_text("def test_b():\n    assert True\n")
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 2
    assert main(_payload(project, "tests/test_b.py"), home=tmp_path) == 2


def test_relative_target_path_resolves_against_payload_cwd(tmp_path, monkeypatch):
    """A relative tool_input path is resolved against the payload's cwd, not wherever the
    hook process happens to run — Claude Code owns the payload cwd; the process cwd is
    an accident of spawning."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    monkeypatch.chdir(tmp_path)  # process cwd deliberately NOT the project
    payload = json.dumps({"tool_name": "Edit",
                          "tool_input": {"file_path": "tests/test_login.py"},
                          "cwd": str(project)})
    assert main(payload, home=tmp_path) == 2


def test_canon_case_folds_on_macos_only(monkeypatch):
    """Default macOS APFS is case-insensitive: Test_Login.py IS test_login.py on disk, so
    canon must compare them equal on darwin (fail-closed) — and must not fold elsewhere."""
    import hercules_state as hs

    monkeypatch.setattr(hs.sys, "platform", "darwin")
    assert hs.canon("/Foo/Test_Login.py") == hs.canon("/foo/test_login.py")
    monkeypatch.setattr(hs.sys, "platform", "linux")
    assert hs.canon("/Foo/Test_Login.py") != hs.canon("/foo/test_login.py")


def test_resolve_session_returns_the_single_context_and_exact_shape(tmp_path):
    import hercules_state as hs

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    session, roots, entry = hs.resolve_session(str(project), home=tmp_path)
    assert session["current_spec"] == "spec-02-login.md"
    assert canonical_in(roots, project)
    assert entry["state_file"] == "proj.json"


def test_resolve_session_fail_open_shape_when_nothing_matches(tmp_path):
    """(None, [], None) — exactly; a different falsy shape would crash callers that unpack."""
    import hercules_state as hs

    (tmp_path / "empty").mkdir()
    assert hs.resolve_session(str(tmp_path / "empty"), home=tmp_path) == (None, [], None)


def test_resolve_session_surfaces_a_non_build_phase(tmp_path):
    """Callers must be able to SEE a non-build phase (decide() fail-opens on it) — the
    fallback context is a single row carrying the active session."""
    import hercules_state as hs

    project = tmp_path / "proj"
    _setup(tmp_path, project, phase="design")
    contexts = hs.resolve_build_contexts(str(project), home=tmp_path)
    assert len(contexts) == 1, "exactly one phase-visibility fallback row"
    assert contexts[0][0]["current_phase"] == "design"


def test_deepest_non_build_project_wins_the_fallback(tmp_path):
    """Two nested projects, neither building: the fallback context must be the inner
    (deepest) project's active session, and only that one."""
    import hercules_state as hs

    outer = tmp_path / "mono"
    inner = outer / "svc"
    _add_project(tmp_path, outer, "outer", frozen=[])
    _add_project(tmp_path, inner, "inner", frozen=[])
    for slug, spec in (("outer", "outer-spec"), ("inner", "inner-spec")):
        p = tmp_path / ".hercules" / "state" / f"{slug}.json"
        state = json.loads(p.read_text())
        state["sessions"]["s1"]["current_phase"] = "design"
        state["sessions"]["s1"]["current_spec"] = spec
        p.write_text(json.dumps(state))
    contexts = hs.resolve_build_contexts(str(inner), home=tmp_path)
    assert len(contexts) == 1
    assert contexts[0][0]["current_spec"] == "inner-spec"


def test_nested_build_contexts_order_deepest_first(tmp_path):
    """Attribution contract: contexts[0] (what resolve_session returns, what a block
    reason names) is the deepest build project when cwd sits inside it."""
    import hercules_state as hs

    outer = tmp_path / "mono"
    inner = outer / "svc"
    _add_project(tmp_path, outer, "mono", frozen=["svc/tests/test_x.py"])
    _add_project(tmp_path, inner, "svc", frozen=["tests/test_y.py"])
    contexts = hs.resolve_build_contexts(str(inner), home=tmp_path)
    assert [c[0]["current_spec"] for c in contexts] == ["spec-svc.md", "spec-mono.md"]


def test_contested_frozen_file_is_attributed_to_the_active_spec(tmp_path, capsys):
    """When the active AND a paused build both freeze the same file, the block stands
    either way — but the reason must name the ACTIVE session's spec (the one the user is
    working in), not whichever session the file order yields."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_shared.py",))
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    paused = {"current_phase": "build", "current_spec": "spec-99-paused.md",
              "current_spec_round": 2, "frozen_test_files": ["tests/test_shared.py"]}
    # paused FIRST in file order — attribution must still follow active_session
    state["sessions"] = {"p": paused, "s1": state["sessions"]["s1"]}
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_shared.py"), home=tmp_path) == 2
    err = capsys.readouterr().err
    assert "spec-02-login.md" in err, "the active session owns the attribution"
    assert "spec-99-paused.md" not in err


def test_canon_never_raises_on_unresolvable_input(tmp_path):
    """canon must fall back to the raw string when filesystem resolution fails (e.g. a
    null byte) — a raising canon would take the whole guard down with it."""
    import hercules_state as hs

    out = hs.canon("tests/\x00bad")
    assert isinstance(out, str) and "bad" in out
