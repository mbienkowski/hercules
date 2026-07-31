"""What each mode promises: `plan` only looks, `apply` only acts on a stated yes."""

from __future__ import annotations

from tools.tests.project_reset.conftest import build_home, plan, run, tree_paths


def test_planning_changes_nothing_on_disk(tmp_path):
    """A person may look as many times as they like. Looking is not a step toward deleting."""
    fx = build_home(tmp_path)
    before = tree_paths(tmp_path)
    plan(fx, "--documents", "--settings", "--all-features")
    assert tree_paths(tmp_path) == before


def test_planning_without_a_selection_reports_what_the_project_holds(tmp_path):
    """The first call is an inventory: this is what exists, nothing is chosen yet."""
    fx = build_home(tmp_path)
    code, payload = plan(fx)
    assert code == 0
    assert sorted(f["key"] for f in payload["features"]) == ["2026-01-02-alpha", "2026-01-03-beta"]
    assert payload["would_delete"]["paths"] == []


def test_planning_a_selection_reports_exactly_what_it_would_remove(tmp_path):
    """The confirmation screen is rendered from this and nothing else, so it must be complete."""
    fx = build_home(tmp_path)
    code, payload = plan(fx, "--documents", "--feature", "2026-01-02-alpha")
    assert code == 0
    assert payload["would_delete"]["paths"] == [str(fx.docs)]
    assert payload["would_delete"]["state_keys"] == ["sessions.2026-01-02-alpha"]


def test_no_stored_narrative_is_ever_reported(tmp_path):
    """A feature is named with its stage. What is written inside it — decisions, notes, quoted
    instructions — stays private, because naming an item is what announcing it requires."""
    fx = build_home(tmp_path)
    _, payload = plan(fx)
    assert "a private narrative" not in str(payload)


def test_a_documents_folder_inside_the_code_repository_is_flagged(tmp_path):
    """The default arrangement puts documents inside the repository, so choosing them deletes
    tracked files. The person is told before they choose, not after."""
    fx = build_home(tmp_path, docs_inside=True)
    _, payload = plan(fx)
    assert payload["documents"]["inside_code_repo"] is True


def test_a_separate_documents_repository_is_not_flagged(tmp_path):
    """The companion to the check above: the flag means something because it is not always set."""
    fx = build_home(tmp_path)
    _, payload = plan(fx)
    assert payload["documents"]["inside_code_repo"] is False


def test_applying_without_a_stated_yes_deletes_nothing(tmp_path):
    """Confirmation is the whole gate. Without it the tool refuses, and the refusal is
    distinguishable from a safety refusal so the command can tell them apart."""
    fx = build_home(tmp_path)
    before = tree_paths(tmp_path)
    code, payload = run(fx, "apply", "--contract", "1", "--documents")
    assert code == 3
    assert tree_paths(tmp_path) == before
    assert payload["error"]


def test_nothing_is_selected_by_default(tmp_path):
    """An absent flag means not chosen. There is no maximal default, so nothing is ever removed
    because an argument was forgotten."""
    fx = build_home(tmp_path)
    before = tree_paths(tmp_path)
    code, _ = run(fx, "apply", "--contract", "1", "--confirm")
    assert tree_paths(tmp_path) == before
    assert code in (0, 5)
