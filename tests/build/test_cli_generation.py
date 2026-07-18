"""Spec 02 — cli generation, drift detection, and dispatch (FS boundary coverage).

Frozen for spec-02-claude-code-target.
"""
from pathlib import Path

import pytest

from scripts.build import cli, serialize


def test_building_the_claude_target_produces_all_required_files(tmp_path):
    """Building the claude-code target creates the plugin manifest, settings file, and
    CLAUDE.md it depends on, so a fresh build never ships with missing configuration."""
    out = tmp_path / "claude-code"
    cli.build_target("claude-code", out)
    assert (out / ".claude-plugin" / "plugin.json").is_file()
    assert (out / "settings.json").is_file()
    assert (out / "CLAUDE.md").is_file()  # persona.md renamed


def test_building_a_non_claude_target_skips_claude_specific_files(tmp_path):
    """When building a target other than claude-code, files that only make sense for
    Claude Code (such as the plugin manifest folder) are not created, keeping other
    targets free of irrelevant, Claude-only artifacts."""
    class _Stub:
        target = "stub-cli-target"

        def serialize_agent(self, frontmatter, body, tokens, models):
            return body

        def serialize_file(self, text, tokens, models):
            return text

    serialize.register(_Stub())
    out = tmp_path / "stub"
    cli.build_target("stub-cli-target", out)
    assert not (out / ".claude-plugin").exists()  # claude-only copies skipped


def test_checking_a_target_flags_files_that_were_edited_by_hand(tmp_path, monkeypatch):
    """If a generated file is hand-edited after being built, checking that target reports
    it as out of sync instead of silently accepting the change -- so an accidental or
    unauthorized edit to generated output gets caught rather than shipped."""
    committed = tmp_path / "claude-code"
    cli.build_target("claude-code", committed)
    (committed / "CLAUDE.md").write_text("TAMPERED", encoding="utf-8")
    monkeypatch.setattr(cli, "DIST", tmp_path)
    assert cli.check_target("claude-code") == 1


def test_checking_a_freshly_built_target_reports_it_up_to_date(tmp_path, monkeypatch):
    """Immediately after building a target, checking it reports success with no drift,
    confirming that a clean build always matches what the checker expects."""
    committed = tmp_path / "claude-code"
    cli.build_target("claude-code", committed)
    monkeypatch.setattr(cli, "DIST", tmp_path)
    assert cli.check_target("claude-code") == 0


def test_building_then_checking_the_same_target_succeeds_end_to_end(tmp_path, monkeypatch):
    """Running the command-line build step and then the check step for the same target
    both succeed, confirming the two operations agree with each other in normal use."""
    monkeypatch.setattr(cli, "DIST", tmp_path)
    assert cli.main(["--target", "claude-code"]) == 0        # build
    assert cli.main(["--target", "claude-code", "--check"]) == 0  # in sync


def test_checking_an_unrecognized_target_is_a_harmless_no_op():
    """Asking to check a target name that has no matching build configuration succeeds
    without error, so referencing an unknown or not-yet-defined target never breaks the
    command-line tool."""
    # A target with no registered serializer is skipped → exit 0.
    assert cli.main(["--target", "no-such-target", "--check"]) == 0
