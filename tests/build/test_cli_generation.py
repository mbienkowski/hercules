"""Spec 02 — cli generation, drift detection, and dispatch (FS boundary coverage).

Frozen for spec-02-claude-code-target.
"""
from pathlib import Path

import pytest

from scripts.build import cli, serialize


def test_build_writes_claude_manifest_and_settings(tmp_path):
    out = tmp_path / "claude-code"
    cli.build_target("claude-code", out)
    assert (out / ".claude-plugin" / "plugin.json").is_file()
    assert (out / "settings.json").is_file()
    assert (out / "CLAUDE.md").is_file()  # persona.md renamed


def test_non_claude_target_gets_no_claude_only_files(tmp_path):
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


def test_check_target_detects_drift(tmp_path, monkeypatch):
    committed = tmp_path / "claude-code"
    cli.build_target("claude-code", committed)
    (committed / "CLAUDE.md").write_text("TAMPERED", encoding="utf-8")
    monkeypatch.setattr(cli, "DIST", tmp_path)
    assert cli.check_target("claude-code") == 1


def test_check_target_clean_when_in_sync(tmp_path, monkeypatch):
    committed = tmp_path / "claude-code"
    cli.build_target("claude-code", committed)
    monkeypatch.setattr(cli, "DIST", tmp_path)
    assert cli.check_target("claude-code") == 0


def test_main_build_then_check_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DIST", tmp_path)
    assert cli.main(["--target", "claude-code"]) == 0        # build
    assert cli.main(["--target", "claude-code", "--check"]) == 0  # in sync


def test_main_skips_unregistered_target():
    # 'opencode' is declared but not registered until Spec 03 → skipped, exit 0.
    assert cli.main(["--target", "opencode", "--check"]) == 0
