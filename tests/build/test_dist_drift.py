"""Spec 02 — the byte-identity gate: generated dist/claude-code == today's plugin/.

Frozen for spec-02-claude-code-target.
"""
import os
from pathlib import Path

import pytest

from scripts.build.cli import _dir_diff, build_target

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = REPO_ROOT / "dist" / "claude-code"


@pytest.mark.skipif(not PLUGIN.exists(), reason="dist/claude-code/ retired (post-cutover)")
def test_claude_code_matches_plugin_byte_identical(tmp_path):
    out = tmp_path / "claude-code"
    build_target("claude-code", out)
    diffs = _dir_diff(PLUGIN, out)
    assert diffs == [], f"dist/claude-code drifts from plugin/: {diffs}"


def test_dir_diff_catches_same_size_same_mtime_content_change(tmp_path):
    """A same-size edit with a matching mtime must still be caught (content compare, not stat).

    This is the case a shallow (stat-signature) compare would miss: identical size + identical
    mtime -> "same" without ever reading the bytes. Exercises the real production
    ``scripts.build.cli._dir_diff`` (not a local reimplementation) so a regression in that
    function — e.g. someone dropping ``shallow=False`` — is actually caught here.
    """
    a, b = tmp_path / "a", tmp_path / "b"
    build_target("claude-code", a)
    build_target("claude-code", b)
    assert _dir_diff(a, b) == []  # two clean builds agree
    rel = "CLAUDE.md"
    ref, tam = a / rel, b / rel
    text = tam.read_text(encoding="utf-8")
    tam.write_text(("Z" if text[0] != "Z" else "Q") + text[1:], encoding="utf-8")  # flip 1 char, size kept
    os.utime(tam, (ref.stat().st_atime, ref.stat().st_mtime))  # equalise mtime -> stat compare says "same"
    assert ref.stat().st_size == tam.stat().st_size
    assert rel in _dir_diff(a, b), "same-size, same-mtime content change must be detected"


@pytest.mark.skipif(not PLUGIN.exists(), reason="dist/claude-code/ retired (post-cutover)")
def test_every_plugin_file_has_a_generated_counterpart(tmp_path):
    out = tmp_path / "claude-code"
    build_target("claude-code", out)
    want = {p.relative_to(PLUGIN).as_posix() for p in PLUGIN.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    got = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    assert want == got
