"""What each mode promises: `plan` only looks, `apply` only acts on a stated yes."""

from __future__ import annotations

import pytest

from tests.scripts.tools.project_reset.conftest import build_home, plan, run, tree_paths


def test_planning_changes_nothing_on_disk(tmp_path, fx):
    """A person may look as many times as they like. Looking is not a step toward deleting."""
    before = tree_paths(tmp_path)
    plan(fx, "--documents", "--settings", "--all-features")
    assert tree_paths(tmp_path) == before


def test_planning_without_a_selection_reports_what_the_project_holds(fx):
    """The first call is an inventory: this is what exists, nothing is chosen yet."""
    code, payload = plan(fx)
    assert code == 0
    assert sorted(f["key"] for f in payload["features"]) == ["2026-01-02-alpha", "2026-01-03-beta"]
    assert payload["would_delete"]["paths"] == []


def test_planning_a_selection_reports_exactly_what_it_would_remove(fx):
    """The confirmation screen is rendered from this and nothing else, so it must be complete."""
    code, payload = plan(fx, "--documents", "--feature", "2026-01-02-alpha")
    assert code == 0
    assert payload["would_delete"]["paths"] == [str(fx.docs)]
    assert payload["would_delete"]["state_keys"] == ["sessions.2026-01-02-alpha"]


def test_no_stored_narrative_is_ever_reported(fx):
    """A feature is named with its stage. What is written inside it — decisions, notes, quoted
    instructions — stays private, because naming an item is what announcing it requires."""
    _, payload = plan(fx)
    assert "a private narrative" not in str(payload)


@pytest.mark.parametrize("docs_inside,expected", [
    (True, True),  # the default arrangement puts documents inside the repository
    (False, False),  # the companion: the flag means something because it is not always set
])
def test_a_documents_folder_inside_the_code_repository_is_flagged(tmp_path, docs_inside, expected):
    """A documents folder inside the code repository deletes tracked files if chosen, so the person
    is told before they choose, not after."""
    fx = build_home(tmp_path, docs_inside=docs_inside)
    _, payload = plan(fx)
    assert payload["documents"]["inside_code_repo"] is expected


def test_applying_without_a_stated_yes_deletes_nothing(tmp_path, fx):
    """Confirmation is the whole gate. Without it the tool refuses, and the refusal is
    distinguishable from a safety refusal so the command can tell them apart."""
    before = tree_paths(tmp_path)
    code, payload = run(fx, "apply", "--contract", "1", "--documents")
    assert code == 3
    assert tree_paths(tmp_path) == before
    assert payload["error"]


def test_nothing_is_selected_by_default(tmp_path, fx):
    """An absent flag means not chosen. There is no maximal default, so nothing is ever removed
    because an argument was forgotten."""
    before = tree_paths(tmp_path)
    code, _ = run(fx, "apply", "--contract", "1", "--confirm")
    assert tree_paths(tmp_path) == before
    assert code in (0, 5)
