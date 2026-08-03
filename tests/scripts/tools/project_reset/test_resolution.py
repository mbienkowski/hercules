"""Which project a run acts on — resolved by the tool, never named by its caller. A slug may break a
tie, but only as a key checked against the registry; which files are touched never comes from it."""

from __future__ import annotations

import pytest

from tests.scripts.tools.project_reset.conftest import build_home, plan


@pytest.mark.parametrize("locate", [
    lambda fx: fx.project,  # standing in the project's own code
    lambda fx: fx.docs,  # documents live in their own repository — a supported, common arrangement
    lambda fx: fx.project / "src" / "inner",  # nobody runs this from the repository root every time
], ids=["code", "docs", "deep"])
def test_working_anywhere_inside_the_project_or_its_documents_identifies_it(fx, locate):
    """Wherever a person stands inside the project, the tool knows which one it is looking at without being told."""
    cwd = locate(fx)
    cwd.mkdir(parents=True, exist_ok=True)
    code, payload = plan(fx, cwd=cwd)
    assert code == 0
    assert payload["project"]["slug"] == fx.slug


def test_an_unrelated_directory_offers_the_registered_projects_rather_than_guessing(tmp_path, fx):
    """Standing somewhere Hercules knows nothing about, the tool lists what it does know and stops.
    Picking a project on the person's behalf would delete from a record they never named."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    code, payload = plan(fx, cwd=outside)
    assert code == 5
    assert payload["error"] == "ambiguous_project"
    assert [c["slug"] for c in payload["candidates"]] == [fx.slug]


@pytest.mark.parametrize("project_arg,expected_code", [
    ((), 5),  # two registered projects can nest — where both match, the person chooses
    (("--project", "proj"), 0),  # the tie-breaker the person is offered actually works
])
def test_two_projects_at_the_same_directory_are_disambiguated_only_when_named(tmp_path, fx, project_arg, expected_code):
    inner = {"directory": str(fx.project), "docs_root": str(fx.docs), "state_file": "other.json"}
    fx = build_home(tmp_path, extra_projects={"other": inner})
    code, payload = plan(fx, *project_arg)
    assert code == expected_code
    if expected_code == 5:
        assert sorted(c["slug"] for c in payload["candidates"]) == ["other", "proj"]
    else:
        assert payload["project"]["slug"] == "proj"


def test_naming_a_project_that_does_not_exist_is_refused(fx):
    """A slug is checked for membership in the registry, so an invented name is never joined into a path."""
    code, payload = plan(fx, "--project", "../../etc")
    assert code == 5
    assert payload["error"] == "ambiguous_project"


def test_the_resolved_project_reports_its_own_directory(fx):
    """The person is shown which directory the tool decided to act on, so a wrong resolution is visible before anything is chosen."""
    _, payload = plan(fx)
    assert payload["project"]["directory"] == str(fx.project)
