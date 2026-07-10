"""Spec 02 — the byte-identity gate: generated dist/claude-code == today's plugin/.

Frozen for spec-02-claude-code-target.
"""
import filecmp
from pathlib import Path

import pytest

from scripts.build.cli import build_target

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = REPO_ROOT / "plugin"


def _diff(a: Path, b: Path, ignore=("__pycache__",)) -> list[str]:
    cmp = filecmp.dircmp(str(a), str(b), ignore=list(ignore))
    out = list(cmp.left_only) + list(cmp.right_only) + [f for f in cmp.diff_files if not f.endswith(".pyc")]
    for sub in cmp.common_dirs:
        out += [f"{sub}/{d}" for d in _diff(a / sub, b / sub, ignore)]
    return out


@pytest.mark.skipif(not PLUGIN.exists(), reason="plugin/ retired (post-cutover)")
def test_claude_code_matches_plugin_byte_identical(tmp_path):
    out = tmp_path / "claude-code"
    build_target("claude-code", out)
    diffs = _diff(PLUGIN, out)
    assert diffs == [], f"dist/claude-code drifts from plugin/: {diffs}"


@pytest.mark.skipif(not PLUGIN.exists(), reason="plugin/ retired (post-cutover)")
def test_every_plugin_file_has_a_generated_counterpart(tmp_path):
    out = tmp_path / "claude-code"
    build_target("claude-code", out)
    want = {p.relative_to(PLUGIN).as_posix() for p in PLUGIN.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    got = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    assert want == got
