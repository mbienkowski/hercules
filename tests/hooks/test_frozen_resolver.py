"""Frozen-tests hook — build-context resolution: nesting, multi-service, ordering, fallback."""

from __future__ import annotations

import json
import sys

from tests.hooks.conftest import _add_project, _payload, _setup, main


def canonical_in(roots, project):
    import hercules_state as hs
    return hs.canon(project) in roots


def test_an_edit_inside_a_nested_service_is_attributed_to_that_service(tmp_path):
    """When a monorepo and one of its inner services are both under active development, an edit
    to a file inside the inner service must be checked against the inner service's own frozen
    tests, not mistakenly matched to the outer project first."""
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


def test_a_frozen_test_in_another_repository_is_still_caught(tmp_path):
    """A protected test can live in a separate repository that the current project references,
    not just inside the project's own folder. Editing that test must still be blocked even
    though the user's current working directory is somewhere else entirely."""
    project = tmp_path / "home"
    svc = tmp_path / "svc-auth"
    _setup(tmp_path, project, frozen=("tests/test_token.py",), repositories={"svc-auth": svc})
    (svc / "tests").mkdir(parents=True, exist_ok=True)
    (svc / "tests/test_token.py").write_text("def test_t():\n    assert True\n")
    payload = _payload(svc, svc / "tests/test_token.py", cwd=svc)
    assert main(payload, home=tmp_path) == 2


def test_an_unrelated_project_listed_first_does_not_stop_the_search(tmp_path):
    """When Hercules is managing several projects and an unrelated one happens to be listed
    before the project actually being edited, that unrelated entry must be skipped rather than
    stopping the search early and letting a real block go undetected."""
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


def test_a_projects_custom_state_file_location_is_respected(tmp_path):
    """A project can be configured to store its progress under a non-default file name. Hercules
    must read that exact file rather than assuming the usual naming convention, or it would look
    in the wrong place and miss an active build."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"]["proj"]["state_file"] = "custom.json"
    (hh / "config.json").write_text(json.dumps(cfg))
    (hh / "state" / "proj.json").rename(hh / "state" / "custom.json")
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_a_project_without_a_custom_state_file_uses_its_default_location(tmp_path):
    """When a project's configuration does not specify where its progress is stored, Hercules
    must fall back to the standard default location instead of failing to find it."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    del cfg["projects"]["proj"]["state_file"]
    (hh / "config.json").write_text(json.dumps(cfg))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_a_project_with_no_active_work_does_not_hide_a_real_build_elsewhere(tmp_path):
    """One registered project can have no work in progress at all. That empty entry must not
    stop Hercules from continuing to check other registered projects, one of which has an
    active build that should still block the edit."""
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


def test_corrupted_data_for_one_project_does_not_hide_a_real_build_in_another(tmp_path):
    """If one registered project's saved progress file is unreadable or corrupted, Hercules must
    skip it and keep checking the remaining projects rather than giving up -- so a genuinely
    active build elsewhere still gets protected."""
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


def test_an_active_build_is_chosen_over_a_design_session_in_the_same_folder(tmp_path):
    """Two work sessions can be registered against the very same project folder, one still in
    design and one already building. Hercules must pick the building session -- picking the
    design one instead would incorrectly let the edit through unguarded."""
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


def test_creating_a_new_file_at_a_frozen_test_path_is_still_blocked(tmp_path):
    """A test file can be recorded as frozen before it has actually been written to disk yet.
    An attempt to create that file must still be blocked -- otherwise someone could sidestep the
    freeze simply by deleting the file first and recreating it with different expectations."""
    project = tmp_path / "proj"
    project.mkdir(parents=True, exist_ok=True)
    _setup(tmp_path, project, create=False)
    assert main(_payload(project, "tests/test_login.py", tool="Write"), home=tmp_path) == 2


def test_switching_to_a_new_feature_does_not_unfreeze_an_earlier_features_tests(tmp_path):
    """A user can start exploring a second feature while an earlier feature's build is still in
    progress. Switching focus to the new feature must not unfreeze the earlier feature's tests --
    working on multiple features at once is a supported flow, and the earlier one's protections
    must keep holding."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    state["sessions"]["s2"] = {"current_phase": "discover", "tier": "low"}
    state["sessions"]["junk"] = "not-a-dict"
    state["active_session"] = "s2"
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_an_idle_inner_project_cannot_hide_an_active_build_in_the_outer_project(tmp_path):
    """An inner project folder can be registered but idle (not yet building), while the outer
    project it sits inside has an active build that froze a file located in that same inner
    folder. The active build must win and still block the edit, regardless of which project's
    folder is more specific."""
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


def test_a_state_file_path_that_tries_to_escape_the_hercules_folder_is_ignored(tmp_path):
    """If a project's configured progress-file location tries to point outside Hercules's own
    data folder (e.g. via `../../`), that path must never be read. Hercules only ever reads
    files inside its own folder, so this project is treated as having no data rather than
    reading an arbitrary file elsewhere on disk."""
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


def test_one_projects_unsafe_state_file_path_does_not_block_checking_other_projects(tmp_path):
    """A project configured with an unsafe, path-escaping progress-file location must simply be
    skipped rather than aborting the whole check -- a different, legitimately registered project
    with an active build still gets to block the edit."""
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


def test_two_features_being_built_at_once_both_keep_their_tests_frozen(tmp_path, capsys):
    """When two features are being built at the same time, both of their frozen tests stay
    protected -- a paused feature's tests are still pending deliverables, not fair game just
    because attention has moved elsewhere. The block message names the specific feature whose
    tests were touched, so the user knows exactly what they can't edit and why."""
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


def test_corrupted_session_data_does_not_prevent_finding_a_real_build(tmp_path):
    """If the record of which session is currently active has gone stale, and unusable, garbled
    session data sits ahead of a legitimate paused build in the saved file, Hercules must skip
    over the garbage and still find and protect the real build."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    state["sessions"] = {"junk": "not-a-dict", "s1": state["sessions"]["s1"]}
    state["active_session"] = "gone"
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_a_monorepo_and_its_inner_service_can_both_be_mid_build_and_stay_guarded(tmp_path):
    """A monorepo and one of its inner services can each have their own build in progress at the
    same time. Even when the edit is being made from inside the inner service, a frozen test that
    belongs to the OUTER project's build must still be protected -- both builds' protections
    apply together, not just whichever project the location happens to match most narrowly."""
    mono = tmp_path / "mono"
    svc = mono / "svc"
    _add_project(tmp_path, mono, "mono", frozen=["svc/tests/test_x.py"])
    _add_project(tmp_path, svc, "svc", frozen=["tests/test_y.py"])
    assert main(_payload(svc, "tests/test_y.py"), home=tmp_path) == 2
    assert main(_payload(svc, str(svc / "tests" / "test_x.py"), cwd=svc), home=tmp_path) == 2


def test_two_projects_registered_at_the_same_folder_both_stay_guarded(tmp_path):
    """A project folder can end up registered under two different names (for example after being
    re-registered). Both registrations' frozen tests must be protected -- whichever one happens
    to be checked last must not be silently let through."""
    project = tmp_path / "proj"
    _add_project(tmp_path, project, "alpha", frozen=["tests/test_a.py"])
    _add_project(tmp_path, project, "beta", frozen=["tests/test_b.py"])
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 2
    assert main(_payload(project, "tests/test_b.py"), home=tmp_path) == 2


def test_one_bad_entry_in_the_frozen_list_does_not_unfreeze_the_valid_ones(tmp_path):
    """A saved list of frozen test files can contain junk entries -- numbers, blanks, or missing
    values -- mixed in with real file paths. Those bad entries must be ignored individually
    rather than breaking the whole list and accidentally leaving the genuine frozen tests
    unprotected."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    state["sessions"]["s1"]["frozen_test_files"] = ["tests/test_login.py", 123, "", None]
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_a_frozen_test_that_no_longer_exists_is_protected_under_every_path_it_can_be_reached_by(tmp_path):
    """A frozen test file might have been deleted, or never created yet, so nothing sits on disk
    at that path. Recreating it must still be blocked no matter which of the project's several
    known locations (including a separate referenced repository) the write targets -- checking
    only the first location would let it slip back in unprotected through another."""
    project = tmp_path / "proj"
    svc = tmp_path / "svc-auth"
    svc.mkdir()
    _setup(tmp_path, project, frozen=("tests/test_token.py",),
           repositories={"svc-auth": svc}, create=False)
    assert main(_payload(project, "tests/test_token.py", tool="Write"), home=tmp_path) == 2
    assert main(_payload(project, str(svc / "tests" / "test_token.py"), tool="Write"),
                home=tmp_path) == 2


def test_two_paused_builds_both_keep_their_frozen_tests_protected_regardless_of_storage_order(tmp_path):
    """When the current focus has moved on to exploring a new feature, but two other features
    each have a paused build behind them, both paused features' frozen tests must stay protected
    -- the order they happen to be saved in must never determine which one gets checked."""
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


def test_a_relative_file_path_is_resolved_against_the_editors_working_directory(tmp_path, monkeypatch):
    """When the edit request gives a relative file path, it must be resolved relative to the
    directory the editor says it's working in, not wherever Hercules's own background process
    happens to have been started from -- otherwise a correctly relative path could be checked
    against the wrong project entirely."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    monkeypatch.chdir(tmp_path)  # process cwd deliberately NOT the project
    payload = json.dumps({"tool_name": "Edit",
                          "tool_input": {"file_path": "tests/test_login.py"},
                          "cwd": str(project)})
    assert main(payload, home=tmp_path) == 2


def test_file_path_comparisons_are_case_insensitive_only_on_macos(monkeypatch):
    """On a default Mac, `Test_Login.py` and `test_login.py` are literally the same file on disk,
    so path comparisons must treat them as equal there to stay fail-closed. On other operating
    systems, where case does distinguish files, they must NOT be treated as equal."""
    import hercules_state as hs

    monkeypatch.setattr(hs.sys, "platform", "darwin")
    assert hs.canon("/Foo/Test_Login.py") == hs.canon("/foo/test_login.py")
    monkeypatch.setattr(hs.sys, "platform", "linux")
    assert hs.canon("/Foo/Test_Login.py") != hs.canon("/foo/test_login.py")


def test_looking_up_a_projects_active_session_returns_its_spec_and_matching_folders(tmp_path):
    """Looking up a known project by its folder must return the specification it's currently
    building, the set of folders that count as part of that project, and the registry
    information Hercules used to find it -- all three pieces callers depend on."""
    import hercules_state as hs

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    session, roots, entry = hs.resolve_session(str(project), home=tmp_path)
    assert session["current_spec"] == "spec-02-login.md"
    assert canonical_in(roots, project)
    assert entry["state_file"] == "proj.json"


def test_looking_up_an_unmanaged_directory_returns_empty_results_instead_of_erroring(tmp_path):
    """When asked about a directory that isn't part of any Hercules-managed project, the lookup
    must return a specific empty result rather than raising an error or returning some other
    shape -- callers rely on that exact empty result to safely conclude there is nothing to
    guard."""
    import hercules_state as hs

    (tmp_path / "empty").mkdir()
    assert hs.resolve_session(str(tmp_path / "empty"), home=tmp_path) == (None, [], None)


def test_a_project_thats_still_in_design_is_still_visible_to_callers(tmp_path):
    """Even when a project hasn't reached the build phase yet, callers must still be able to see
    what phase it's in -- the guard intentionally lets edits through during design, but only
    because it can see and recognize that phase, not because the project is invisible to it."""
    import hercules_state as hs

    project = tmp_path / "proj"
    _setup(tmp_path, project, phase="design")
    contexts = hs.resolve_build_contexts(str(project), home=tmp_path)
    assert len(contexts) == 1, "exactly one phase-visibility fallback row"
    assert contexts[0][0]["current_phase"] == "design"


def test_the_innermost_of_two_nested_non_building_projects_is_the_one_reported(tmp_path):
    """A monorepo and an inner service can both be registered but neither is actively building.
    When checking a file inside the inner service, Hercules must report the inner service's own
    session -- and only that one -- not the outer project's."""
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


def test_when_a_project_and_its_inner_service_are_both_building_the_inner_services_spec_is_named_first(tmp_path):
    """When both an outer project and its inner service have active builds, and the edit is being
    made from inside the inner service, any block message must credit the inner service's own
    specification first -- attributing the block to the most specific, relevant piece of work."""
    import hercules_state as hs

    outer = tmp_path / "mono"
    inner = outer / "svc"
    _add_project(tmp_path, outer, "mono", frozen=["svc/tests/test_x.py"])
    _add_project(tmp_path, inner, "svc", frozen=["tests/test_y.py"])
    contexts = hs.resolve_build_contexts(str(inner), home=tmp_path)
    assert [c[0]["current_spec"] for c in contexts] == ["spec-svc.md", "spec-mono.md"]


def test_when_two_builds_freeze_the_same_test_the_block_names_the_current_work_not_a_paused_one(tmp_path, capsys):
    """A test file can be frozen by both the feature the user is actively working on and by a
    separate, paused feature. The edit is blocked either way, but the message shown to the user
    must credit the feature they're actually working on -- not whichever one happens to be
    stored first -- so the explanation actually matches what they're doing."""
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


def test_comparing_a_corrupted_file_path_never_crashes_the_guard(tmp_path):
    """A file path can contain characters the filesystem can't resolve, such as an embedded null
    byte. Comparing such a path must fall back to comparing it as plain text instead of raising
    an error -- a crash here would take down the whole safety guard, leaving nothing checking
    edits at all."""
    import hercules_state as hs

    out = hs.canon("tests/\x00bad")
    assert isinstance(out, str) and "bad" in out
