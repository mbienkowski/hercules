"""Spec 01 — cli/layout skeleton smoke (empty-tree acceptance).

The full FS round-trip lands in Spec 02; here we only prove the entry runs and plans cleanly.
Frozen for spec-01-build-compiler-core.
"""
from pathlib import Path

from scripts.build.cli import main
from scripts.build.layout import discover_sources, plan_outputs


def test_check_runs_and_reports_in_sync_on_empty_tree():
    # No dist/ committed yet and the src/content scaffold is empty → in sync (exit 0).
    assert main(["--target", "claude-code", "--check"]) == 0


def test_discover_sources_missing_dir_is_empty():
    assert discover_sources(Path("/no/such/content/root")) == []


def test_plan_outputs_maps_sources_one_to_one(tmp_path):
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "b.md").write_text("y", encoding="utf-8")
    units = plan_outputs(tmp_path, "claude-code")
    dests = sorted(u.dest for u in units)
    assert dests == ["agents/a.md", "b.md"]
    assert all(u.target == "claude-code" for u in units)
