"""Tests for the release changelog-update helper (scripts/update_changelog.py)."""

from __future__ import annotations

from scripts.update_changelog import format_entry, update_changelog

_V1_COMMITS = ["feat: initial release", "chore: add CI"]
_V2_COMMITS = ["feat: add new thing", "fix: correct bug"]


def test_first_release_creates_fresh_changelog(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## v0.1.0\n\nstale content from a previous run\n\n")
    update_changelog("v1.0.0", "", is_first=True, path=str(cl), commits=_V1_COMMITS)
    content = cl.read_text()
    assert "stale content" not in content
    assert "v1.0.0" in content


def test_subsequent_release_prepends(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## v1.0.0\n\n* feat: initial release\n\n")
    update_changelog("v1.1.0", "v1.0.0", is_first=False, path=str(cl), commits=_V2_COMMITS)
    content = cl.read_text()
    assert content.index("1.1.0") < content.index("1.0.0")


def test_subsequent_release_preserves_existing_content(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## v1.0.0\n\n* feat: initial release\n\n")
    update_changelog("v1.1.0", "v1.0.0", is_first=False, path=str(cl), commits=_V2_COMMITS)
    assert "initial release" in cl.read_text()


def test_non_conventional_commit_appears_in_changelog(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    update_changelog(
        "v1.0.0", "", is_first=True, path=str(cl),
        commits=["Release improvements and proper versioning"],
    )
    assert "Release improvements and proper versioning" in cl.read_text()


def test_format_entry_includes_all_commit_messages():
    entry = format_entry("v1.0.0", ["feat: foo", "fix: bar", "just a plain message"])
    assert "* feat: foo" in entry
    assert "* fix: bar" in entry
    assert "* just a plain message" in entry
    assert "v1.0.0" in entry
