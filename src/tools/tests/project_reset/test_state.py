"""Integrity of the record around the edit — what must survive, byte for byte."""

from __future__ import annotations

import json
import os
import stat

import pytest

from tools.tests.project_reset.conftest import apply, build_home


def test_a_feature_that_was_not_chosen_survives_unchanged(tmp_path):
    """The single worst outcome this tool could produce is quietly rewriting a record it was asked
    to leave alone, so the survivor is compared value for value, not merely counted."""
    fx = build_home(tmp_path)
    before = fx.state()["sessions"]["2026-01-03-beta"]
    apply(fx, "--feature", "2026-01-02-alpha")
    assert fx.state()["sessions"]["2026-01-03-beta"] == before


def test_clearing_the_feature_in_progress_also_clears_the_pointer_to_it(tmp_path):
    """A pointer left aimed at a feature that no longer exists would send the next run looking for
    something gone."""
    fx = build_home(tmp_path)
    apply(fx, "--feature", "2026-01-03-beta")
    assert fx.state().get("active_session") in (None, "")


def test_clearing_another_feature_leaves_the_pointer_alone(tmp_path):
    """The companion to the check above: the pointer moves only when it has to."""
    fx = build_home(tmp_path)
    apply(fx, "--feature", "2026-01-02-alpha")
    assert fx.state()["active_session"] == "2026-01-03-beta"


def test_a_record_that_cannot_be_parsed_is_refused_rather_than_half_edited(tmp_path):
    """Editing a file the tool could not fully read would turn damage into worse damage."""
    fx = build_home(tmp_path)
    fx.state_path.write_text("{ this is not json")
    code, _ = apply(fx, "--feature", "2026-01-02-alpha")
    assert code == 4
    assert fx.state_path.read_text() == "{ this is not json"


def test_the_records_permissions_survive_the_rewrite(tmp_path):
    """A rewrite through a temporary file inherits the process umask unless the original's mode is
    carried across — which would quietly widen who can read a person's record."""
    fx = build_home(tmp_path)
    os.chmod(fx.state_path, 0o600)
    apply(fx, "--feature", "2026-01-02-alpha")
    assert stat.S_IMODE(fx.state_path.stat().st_mode) == 0o600


def test_the_schema_marker_survives_the_rewrite(tmp_path):
    """Everything outside the removed keys is carried through, not reconstructed from what the tool
    happens to know about."""
    fx = build_home(tmp_path)
    apply(fx, "--feature", "2026-01-02-alpha")
    assert fx.state()["schema_version"] == 1


def test_another_projects_registry_entry_is_never_touched(tmp_path):
    """Clearing one project's settings rewrites the shared registry file, so the neighbours in it
    are the thing most easily lost."""
    other = {"directory": str(tmp_path / "other"), "docs_root": str(tmp_path / "other-docs"),
             "state_file": "other.json"}
    fx = build_home(tmp_path, extra_projects={"other": other})
    apply(fx, "--settings", "--project", fx.slug)
    assert fx.registry()["projects"]["other"] == other


def test_a_completed_clear_reports_that_it_verified_its_own_work(tmp_path):
    """The tool re-reads what it wrote and says so. An unverified write is a hope, not a result."""
    fx = build_home(tmp_path)
    _, payload = apply(fx, "--feature", "2026-01-02-alpha")
    assert payload["verified"] is True


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
def test_a_record_that_cannot_be_written_leaves_the_original_intact(tmp_path):
    """When the rewrite cannot land, the original must still be there — never a truncated file."""
    fx = build_home(tmp_path)
    original = fx.state_path.read_text()
    os.chmod(fx.state_path.parent, 0o500)
    try:
        code, _ = apply(fx, "--feature", "2026-01-02-alpha")
        assert code == 4
        assert json.loads(original)["sessions"].keys() == fx.state()["sessions"].keys()
    finally:
        os.chmod(fx.state_path.parent, 0o700)
