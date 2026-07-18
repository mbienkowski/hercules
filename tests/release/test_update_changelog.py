"""Tests for the release changelog-update helper (scripts/update_changelog.py)."""

from __future__ import annotations

from scripts.update_changelog import format_entry, update_changelog

_V1_COMMITS = ["feat: initial release", "chore: add CI"]
_V2_COMMITS = ["feat: add new thing", "fix: correct bug"]


def test_first_release_replaces_any_leftover_changelog_content(tmp_path):
    """When a project's very first release is published, the changelog file is rewritten
    from scratch instead of being appended to whatever was left over from an earlier,
    unrelated run -- so stale notes never leak into the new project's history."""
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## v0.1.0\n\nstale content from a previous run\n\n")
    update_changelog("v1.0.0", "", is_first=True, path=str(cl), commits=_V1_COMMITS)
    content = cl.read_text()
    assert "stale content" not in content
    assert "v1.0.0" in content


def test_newest_release_notes_appear_above_older_ones(tmp_path):
    """When a new release is added to a changelog that already has history, its notes are
    placed above the previous release's notes, so anyone opening the file sees the most
    recent changes first without having to scroll past older ones."""
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## v1.0.0\n\n* feat: initial release\n\n")
    update_changelog("v1.1.0", "v1.0.0", is_first=False, path=str(cl), commits=_V2_COMMITS)
    content = cl.read_text()
    assert content.index("1.1.0") < content.index("1.0.0")


def test_adding_a_new_release_keeps_older_release_notes_intact(tmp_path):
    """Recording a new release in the changelog must not erase or overwrite the notes from
    a previous release -- the full release history stays readable, not just the latest
    entry."""
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## v1.0.0\n\n* feat: initial release\n\n")
    update_changelog("v1.1.0", "v1.0.0", is_first=False, path=str(cl), commits=_V2_COMMITS)
    assert "initial release" in cl.read_text()


def test_a_commit_message_that_skips_the_teams_usual_style_still_gets_recorded(tmp_path):
    """Not every commit message follows the team's usual 'feat:'/'fix:' labeling style --
    a plain-English commit message must still show up in the changelog rather than being
    silently dropped, so no shipped change goes unrecorded just because of its wording."""
    cl = tmp_path / "CHANGELOG.md"
    update_changelog(
        "v1.0.0", "", is_first=True, path=str(cl),
        commits=["Release improvements and proper versioning"],
    )
    assert "Release improvements and proper versioning" in cl.read_text()


def test_a_release_entry_lists_every_commit_under_its_version_number():
    """A release's changelog entry must show its version number and list every commit that
    went into that release as its own line, so a reader can tell exactly what shipped in
    that version without missing anything."""
    entry = format_entry("v1.0.0", ["feat: foo", "fix: bar", "just a plain message"])
    assert "* feat: foo" in entry
    assert "* fix: bar" in entry
    assert "* just a plain message" in entry
    assert "v1.0.0" in entry
