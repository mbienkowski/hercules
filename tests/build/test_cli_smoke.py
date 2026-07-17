"""Spec 01 — cli/layout skeleton smoke (empty-tree acceptance).

The full FS round-trip lands in Spec 02; here we only prove the entry runs and plans cleanly.
Frozen for spec-01-build-compiler-core.
"""
from pathlib import Path

from scripts.build.cli import main
from scripts.build.layout import discover_sources


def test_check_runs_and_reports_in_sync_on_empty_tree():
    # No dist/ committed yet and the src/content scaffold is empty → in sync (exit 0).
    assert main(["--target", "claude-code", "--check"]) == 0


def test_discover_sources_missing_dir_is_empty():
    assert discover_sources(Path("/no/such/content/root")) == []
