"""What actually gets removed, and what survives beside it."""

from __future__ import annotations

import os

import pytest

from tools.tests.project_reset.conftest import apply, build_home


def test_choosing_the_documents_folder_removes_it_and_everything_in_it(tmp_path):
    fx = build_home(tmp_path)
    code, payload = apply(fx, "--documents")
    assert code == 0
    assert not fx.docs.exists()
    assert payload["deleted"]["paths"] == [str(fx.docs)]


def test_choosing_the_documents_folder_leaves_the_code_untouched(tmp_path):
    """The headline promise, asserted directly rather than assumed from the refusal rules."""
    fx = build_home(tmp_path)
    marker = fx.project / "main.py"
    marker.write_text("print('hello')\n")
    apply(fx, "--documents")
    assert marker.read_text() == "print('hello')\n"


def test_choosing_one_feature_removes_only_that_record(tmp_path):
    fx = build_home(tmp_path)
    code, _ = apply(fx, "--feature", "2026-01-02-alpha")
    assert code == 0
    assert list(fx.state()["sessions"]) == ["2026-01-03-beta"]


def test_choosing_every_feature_empties_the_record_but_keeps_the_file(tmp_path):
    """The file survives so the project stays known; only its features go."""
    fx = build_home(tmp_path)
    code, _ = apply(fx, "--all-features")
    assert code == 0
    assert fx.state()["sessions"] == {}


def test_choosing_settings_clears_the_four_configurable_fields(tmp_path):
    fx = build_home(tmp_path)
    code, _ = apply(fx, "--settings")
    assert code == 0
    assert not {"docs_root", "repositories", "frozen_hook", "keep_specs"} & set(fx.entry())


def test_choosing_settings_keeps_the_fields_that_find_the_project(tmp_path):
    """Clearing settings must not orphan the record: the match key and the state pointer stay."""
    fx = build_home(tmp_path)
    apply(fx, "--settings")
    assert fx.entry()["directory"] == str(fx.project)
    assert fx.entry()["state_file"] == f"{fx.slug}.json"


def test_a_documents_folder_that_is_already_gone_counts_as_done(tmp_path):
    """Re-running after a partial failure finds less to do rather than erroring."""
    fx = build_home(tmp_path)
    apply(fx, "--documents")
    code, payload = apply(fx, "--documents")
    assert code == 0
    assert payload["failed"] == []


def test_a_symlink_inside_the_tree_is_unlinked_and_never_followed(tmp_path):
    """A link planted inside the documents folder must not become a route out of it."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keepme.txt").write_text("untouched\n")
    fx = build_home(tmp_path)
    os.symlink(outside, fx.docs / "escape")
    apply(fx, "--documents")
    assert (outside / "keepme.txt").read_text() == "untouched\n"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_a_file_that_cannot_be_removed_is_named_rather_than_glossed_over(tmp_path):
    """Partial completion is reported as partial. Claiming success while something survived is the
    one outcome that would teach a person to stop reading these messages."""
    fx = build_home(tmp_path)
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
