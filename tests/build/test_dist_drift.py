"""Spec 02 (generalized) — the byte-identity gate: every generated dist/<eco> == the committed tree.

Frozen for spec-02-claude-code-target; parametrized over every registered target so ALL committed
trees are byte-pinned INSIDE the pytest run (the mutation gate's highest-kill test — an
output-affecting engine mutant for any ecosystem fails here).
"""
import os
from pathlib import Path

import pytest

from scripts.build.cli import TARGETS, _dir_diff, build_target

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = REPO_ROOT / "dist" / "claude-code"


@pytest.mark.parametrize("target", TARGETS)
def test_building_each_target_reproduces_the_committed_dist_exactly(target, tmp_path):
    """Rebuilding any target from source must produce output byte-for-byte identical to the tree
    already checked into the repo. If it ever drifts, the published plugin a user installs would
    no longer match what the build actually produces."""
    committed = REPO_ROOT / "dist" / target
    if not committed.exists():
        pytest.skip(f"dist/{target}/ not committed")
    out = tmp_path / target
    build_target(target, out)
    diffs = _dir_diff(committed, out)
    assert diffs == [], f"dist/{target} drifts from a fresh build: {diffs}"


def test_a_content_edit_is_detected_even_when_file_size_and_timestamp_match(tmp_path):
    """If a file's text changes but its size and last-modified time happen to stay the same,
    the drift check must still notice the change instead of assuming the files are identical.
    A comparison that trusted size and timestamp alone would silently miss real edits, letting
    a broken build pass as matching the published plugin."""
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
def test_the_build_produces_every_file_the_published_plugin_has(tmp_path):
    """Every file present in the published plugin must also appear in a freshly built copy, with
    no extras and nothing missing. A gap here would mean a user installing the built plugin ends
    up with an incomplete or mismatched set of files compared to what was published."""
    out = tmp_path / "claude-code"
    build_target("claude-code", out)
    want = {p.relative_to(PLUGIN).as_posix() for p in PLUGIN.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    got = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    assert want == got
