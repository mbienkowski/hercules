"""What actually gets removed, and what survives beside it."""

from __future__ import annotations

import os

import pytest

from tests.scripts.tools.project_reset.conftest import apply


def test_choosing_the_documents_folder_removes_it_and_leaves_the_code_untouched(fx):
    """The headline promise, asserted directly rather than assumed from the refusal rules."""
    marker = fx.project / "main.py"
    marker.write_text("print('hello')\n")
    code, payload = apply(fx, "--documents")
    assert code == 0
    assert not fx.docs.exists()
    assert payload["deleted"]["paths"] == [str(fx.docs)]
    assert marker.read_text() == "print('hello')\n"


@pytest.mark.parametrize("argv,expected_sessions", [
    (("--feature", "2026-01-02-alpha"), ["2026-01-03-beta"]),
    (("--all-features",), []),  # the file survives so the project stays known; only its features go
])
def test_choosing_a_feature_or_every_feature_removes_only_what_was_chosen(fx, argv, expected_sessions):
    code, _ = apply(fx, *argv)
    assert code == 0
    assert list(fx.state()["sessions"]) == expected_sessions


def test_choosing_settings_clears_the_four_configurable_fields_but_keeps_what_finds_the_project(fx):
    """Clearing settings must not orphan the record: the match key and the state pointer stay."""
    code, _ = apply(fx, "--settings")
    assert code == 0
    assert not {"docs_root", "repositories", "frozen_hook", "keep_specs"} & set(fx.entry())
    assert fx.entry()["directory"] == str(fx.project)
    assert fx.entry()["state_file"] == f"{fx.slug}.json"


def test_a_documents_folder_that_is_already_gone_counts_as_done(fx):
    """Re-running after a partial failure finds less to do rather than erroring."""
    apply(fx, "--documents")
    code, payload = apply(fx, "--documents")
    assert code == 0
    assert payload["failed"] == []


def test_a_symlink_inside_the_tree_is_unlinked_and_never_followed(tmp_path, fx):
    """A link planted inside the documents folder must not become a route out of it."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keepme.txt").write_text("untouched\n")
    os.symlink(outside, fx.docs / "escape")
    apply(fx, "--documents")
    assert (outside / "keepme.txt").read_text() == "untouched\n"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_a_file_that_cannot_be_removed_is_named_rather_than_glossed_over(fx):
    """Partial completion is reported as partial — a false success is the one outcome that teaches a person to stop reading these messages."""
    locked = fx.docs / "locked"
    locked.mkdir()
    (locked / "file.txt").write_text("x\n")
    os.chmod(locked, 0o500)
    try:
        code, payload = apply(fx, "--documents")
        assert code == 4
        assert any("file.txt" in f["path"] for f in payload["failed"])
    finally:
        os.chmod(locked, 0o700)
