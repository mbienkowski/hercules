"""Which project a run acts on — resolved by the tool, never named by its caller.

The caller may pass a slug to break a tie, but only as a key checked against the registry. Nothing
about which files are touched ever comes from the caller.
"""

from __future__ import annotations

from tools.tests.project_reset.conftest import build_home, plan


def test_working_inside_the_code_repository_identifies_that_project(tmp_path):
    """Standing in the project's own code, the tool knows which project it is looking at without
    being told."""
    fx = build_home(tmp_path)
    code, payload = plan(fx)
    assert code == 0
    assert payload["project"]["slug"] == fx.slug


def test_working_inside_the_documents_repository_identifies_the_same_project(tmp_path):
    """A person whose documents live in their own repository, and who is working there, must still
    reach their project. Matching only the code directory finds nothing at all — the arrangement is
    supported and common, so it cannot be a dead end."""
    fx = build_home(tmp_path)
    code, payload = plan(fx, cwd=fx.docs)
    assert code == 0
    assert payload["project"]["slug"] == fx.slug


def test_a_directory_deep_inside_the_project_still_identifies_it(tmp_path):
    """Nobody runs this from the repository root every time."""
    fx = build_home(tmp_path)
    deep = fx.project / "src" / "inner"
    deep.mkdir(parents=True)
    code, payload = plan(fx, cwd=deep)
    assert code == 0
    assert payload["project"]["slug"] == fx.slug


def test_an_unrelated_directory_offers_the_registered_projects_rather_than_guessing(tmp_path):
    """Standing somewhere Hercules knows nothing about, the tool lists what it does know and stops.
    Picking a project on the person's behalf would delete from a record they never named."""
    fx = build_home(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    code, payload = plan(fx, cwd=outside)
    assert code == 5
    assert payload["error"] == "ambiguous_project"
    assert [c["slug"] for c in payload["candidates"]] == [fx.slug]


def test_a_directory_matching_two_projects_asks_which_one(tmp_path):
    """Two registered projects can nest. Where both match, the person chooses."""
    fx = build_home(tmp_path)
    inner = {"directory": str(fx.project), "docs_root": str(fx.docs), "state_file": "other.json"}
    fx = build_home(tmp_path, extra_projects={"other": inner})
    code, payload = plan(fx)
    assert code == 5
    assert sorted(c["slug"] for c in payload["candidates"]) == ["other", "proj"]


def test_naming_a_project_settles_which_one_to_act_on(tmp_path):
    """The tie-breaker the person is offered actually works."""
    inner = {"directory": str(tmp_path / "code"), "docs_root": str(tmp_path / "docs-repo"),
             "state_file": "other.json"}
    fx = build_home(tmp_path, extra_projects={"other": inner})
    code, payload = plan(fx, "--project", fx.slug)
    assert code == 0
    assert payload["project"]["slug"] == fx.slug


def test_naming_a_project_that_does_not_exist_is_refused(tmp_path):
    """A slug is checked for membership in the registry, so an invented name reaches nothing —
    it is never joined into a path."""
    fx = build_home(tmp_path)
    code, payload = plan(fx, "--project", "../../etc")
    assert code == 5
    assert payload["error"] == "ambiguous_project"


def test_the_resolved_project_reports_its_own_directory(tmp_path):
    """The person is shown which directory the tool decided to act on, so a wrong resolution is
    visible before anything is chosen."""
    fx = build_home(tmp_path)
    _, payload = plan(fx)
    assert payload["project"]["directory"] == str(fx.project)
