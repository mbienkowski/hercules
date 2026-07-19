"""The OpenCode hard write-gate (G1) — a real pre-write veto, matching Claude Code's PreToolUse gate.

The generated plugin.js `tool.execute.before` hook invokes the CANONICAL Python guard
(hooks/frozen_tests.py, the same code Claude runs) via python3; throwing aborts the Write/Edit before
it touches disk. These tests prove the wiring is emitted (Python-level, for coverage/mutation) and that
the whole chain actually blocks a frozen edit in a real Node process (skipped when node/python3 absent).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.build.cli import build_target
from scripts.build.manifests import generate_plugin_js

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_generated_plugin_wires_the_write_gate_to_the_canonical_python_guard():
    """The plugin.js must register a tool.execute.before hook that calls python3 on the shipped
    frozen_tests.py — the reuse that keeps one source of truth across ecosystems. Pinned at the
    Python (generator) level so it is covered by the coverage + mutation gates."""
    js = generate_plugin_js("hercules", [], [])
    assert '"tool.execute.before": makeWriteGate' in js, "plugin must register the write-gate hook"
    assert 'spawnSync("python3"' in js, "the gate must invoke the canonical python3 guard"
    assert 'path.join(PLUGIN_ROOT, "hooks", "frozen_tests.py")' in js, "must point at the shipped guard"
    # Fail-open discipline: a spawn/python error must never brick an unrelated edit.
    assert "fail open" in js


def test_the_shipped_guard_is_the_same_file_claude_uses(tmp_path):
    """OpenCode ships COPIES of the Claude guard files, byte-for-byte, so the write-gate logic can
    never diverge across ecosystems."""
    out = tmp_path / "opencode"
    build_target("opencode", out)
    src = REPO_ROOT / "src" / "targets" / "claude-code" / "hooks"
    for name in ("frozen_tests.py", "hercules_state.py"):
        assert (out / "hooks" / name).read_bytes() == (src / name).read_bytes()


# ── End-to-end: the real Node plugin blocks a frozen edit via the real python3 guard ──
_HAVE_TOOLS = shutil.which("node") is not None and shutil.which("python3") is not None


@pytest.fixture
def opencode_with_active_build(tmp_path):
    """Build the plugin and stand up an isolated ~/.hercules with one active build session that
    freezes ``tests/test_frozen.py`` under a project rooted at a throwaway dir."""
    out = tmp_path / "opencode"
    build_target("opencode", out)
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    (home / ".hercules" / "state").mkdir(parents=True)
    (home / ".hercules" / "config.json").write_text(
        json.dumps({"projects": {"p": {"directory": str(proj), "state_file": "p.json"}}}), encoding="utf-8")
    (home / ".hercules" / "state" / "p.json").write_text(
        json.dumps({"active_session": "s1", "sessions": {
            "s1": {"current_phase": "build", "frozen_test_files": ["tests/test_frozen.py"]}}}), encoding="utf-8")
    return out / "plugin.js", proj, home


def _edit_verdict(plugin_js: Path, proj: Path, home: Path, file_path: str) -> str:
    """Return 'BLOCKED' or 'ALLOWED' for an `edit` of *file_path*, running the real plugin in node."""
    js = f"""
    const p = require({json.dumps(str(plugin_js))});
    p.server({{directory: {json.dumps(str(proj))}}}).then((r) => {{
      try {{ r["tool.execute.before"]({{tool: "edit"}}, {{args: {{filePath: {json.dumps(file_path)}}}}}); }}
      catch (e) {{ console.log("BLOCKED:" + e.message); return; }}
      console.log("ALLOWED");
    }}).catch((e) => {{ console.error(e); process.exit(1); }});
    """
    res = subprocess.run(["node", "-e", js], capture_output=True, text=True,
                         env={**os.environ, "HOME": str(home)}, timeout=30)
    assert res.returncode == 0, res.stderr
    return res.stdout.strip().splitlines()[-1]


@pytest.mark.skipif(not _HAVE_TOOLS, reason="node + python3 required for the live gate check")
def test_the_real_plugin_hard_blocks_an_edit_to_a_frozen_test(opencode_with_active_build):
    """The real Node plugin, driving the real python3 guard, must THROW (hard-block) an edit to a
    frozen test file during an active build — proving the pre-write veto, not just its presence."""
    plugin_js, proj, home = opencode_with_active_build
    verdict = _edit_verdict(plugin_js, proj, home, "tests/test_frozen.py")
    assert verdict.startswith("BLOCKED"), f"frozen edit must be denied, got {verdict!r}"
    assert "write-gate" in verdict


@pytest.mark.skipif(not _HAVE_TOOLS, reason="node + python3 required for the live gate check")
def test_the_real_plugin_allows_an_edit_to_a_non_frozen_file(opencode_with_active_build):
    """A non-frozen file must pass — the gate blocks only frozen tests, never unrelated edits."""
    plugin_js, proj, home = opencode_with_active_build
    assert _edit_verdict(plugin_js, proj, home, "src/feature.py") == "ALLOWED"
