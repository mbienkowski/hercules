"""Spec 01 — cli/layout skeleton smoke (empty-tree acceptance).

The full FS round-trip lands in Spec 02; here we only prove the entry runs and plans cleanly.
Frozen for spec-01-build-compiler-core.
"""
from pathlib import Path

from scripts.build.cli import main
from scripts.build.layout import discover_sources


def test_check_command_reports_in_sync_when_project_has_no_content_yet():
    """Running the build's "--check" command on a brand-new project -- one with no
    built output and no source content yet -- must report everything as already
    in sync (a clean success) instead of failing, so setting up a new project
    doesn't start with a false alarm."""
    # No dist/ committed yet and the src/content scaffold is empty → in sync (exit 0).
    assert main(["--target", "claude-code", "--check"]) == 0


def test_scanning_a_missing_content_folder_finds_no_sources_without_erroring():
    """If the folder where source content is supposed to live doesn't exist on disk,
    scanning for content must simply report that there is none, rather than crashing --
    so a fresh checkout or a not-yet-created content directory doesn't break the build."""
    assert discover_sources(Path("/no/such/content/root")) == []
