"""Integrity of the record around the edit — what must survive, byte for byte."""

from __future__ import annotations

import json
import os
import stat

import pytest

from tests.scripts.tools.project_reset.conftest import apply, build_home


@pytest.mark.parametrize("cleared,expected_pointer", [
    ("2026-01-03-beta", None),  # a pointer left aimed at a feature that no longer exists is a dangling one
    ("2026-01-02-alpha", "2026-01-03-beta"),  # the pointer moves only when it has to
])
def test_clearing_a_feature_updates_the_pointer_only_when_it_was_the_one_cleared(fx, cleared, expected_pointer):
    apply(fx, "--feature", cleared)
    if expected_pointer is None:
        assert fx.state().get("active_session") in (None, "")
    else:
        assert fx.state()["active_session"] == expected_pointer


def test_a_feature_that_was_not_chosen_survives_unchanged(fx):
    """The worst outcome here is quietly rewriting a record asked to be left alone, so the survivor is compared value for value, not merely counted."""
    before = fx.state()["sessions"]["2026-01-03-beta"]
    apply(fx, "--feature", "2026-01-02-alpha")
    assert fx.state()["sessions"]["2026-01-03-beta"] == before


def test_a_record_that_cannot_be_parsed_is_refused_rather_than_half_edited(fx):
    """Editing a file the tool could not fully read would turn damage into worse damage."""
    fx.state_path.write_text("{ this is not json")
    code, _ = apply(fx, "--feature", "2026-01-02-alpha")
    assert code == 4
    assert fx.state_path.read_text() == "{ this is not json"


def test_the_records_permissions_and_schema_marker_survive_the_rewrite_and_report_as_verified(fx):
    """A rewrite through a temporary file inherits the umask unless the mode is carried across; every
    untouched key must survive unreconstructed; and the tool re-reads what it wrote and says so."""
    os.chmod(fx.state_path, 0o600)
    _, payload = apply(fx, "--feature", "2026-01-02-alpha")
    assert stat.S_IMODE(fx.state_path.stat().st_mode) == 0o600
    assert fx.state()["schema_version"] == 1
    assert payload["verified"] is True


def test_another_projects_registry_entry_is_never_touched(tmp_path):
    """Clearing one project's settings rewrites the shared registry, so a neighbour is what is most easily lost."""
    other = {"directory": str(tmp_path / "other"), "docs_root": str(tmp_path / "other-docs"),
             "state_file": "other.json"}
    fx = build_home(tmp_path, extra_projects={"other": other})
    apply(fx, "--settings", "--project", fx.slug)
    assert fx.registry()["projects"]["other"] == other


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
def test_a_record_that_cannot_be_written_leaves_the_original_intact(fx):
    """When the rewrite cannot land, the original must still be there — never a truncated file."""
    original = fx.state_path.read_text()
    os.chmod(fx.state_path.parent, 0o500)
    try:
        code, _ = apply(fx, "--feature", "2026-01-02-alpha")
        assert code == 4
        assert json.loads(original)["sessions"].keys() == fx.state()["sessions"].keys()
    finally:
        os.chmod(fx.state_path.parent, 0o700)
