"""The JavaScript plugin: the one host whose integration is a program rather than a table, so the
distribution ships CODE that must call the shipped guard correctly — a contract no configuration
file can express. It runs in a user's editor with their repository open, so it must reach no network
and must veto a frozen edit through the same Python guard every other ecosystem runs.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
# Two static files the recipe copies through; the plugin `require`s read-file.js, so both promise it.
_PLUGIN_DIR = REPO_ROOT / "src" / "content" / "targets" / "opencode"
_PLUGIN_JS = _PLUGIN_DIR / "plugin.js"
_READ_FILE_JS = _PLUGIN_DIR / "read-file.js"
# The committed dist/ tree, kept byte-identical to a fresh build by the `make ci-build` drift gate.
_DIST_OPENCODE = REPO_ROOT / "dist" / "opencode"


def test_shipped_plugin_js_ships_no_network_channel():
    """JavaScript sits outside the AST (abstract syntax tree) scan of the Python guards, so the "no
    external network channel" promise needs its own allowlist here."""
    allowed = {"path", "fs", "os", "child_process"}
    for source in (_PLUGIN_JS, _READ_FILE_JS):
        js = source.read_text(encoding="utf-8")
        requires = set(re.findall(r'require\(["\']([^"\']+)["\']\)', js))
        assert requires, f"{source.name}: no require() found — the scan matched nothing and proves nothing"
        # A relative require reads a sibling, allowed only when that file really ships beside it.
        siblings = {m for m in requires if m.startswith(".")}
        for rel in siblings:
            assert (_PLUGIN_DIR / rel).is_file(), f"{source.name}: requires missing sibling {rel!r}"
        third_party = requires - siblings - allowed
        assert not third_party, f"{source.name} requires unexpected module(s): {sorted(third_party)}"
        for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "http.request", "https.request",
                       'require("http', 'require("https', 'require("net', 'require("dns', 'require("tls',
                       "import("):
            assert banned not in js, f"{source.name} must not reference {banned!r} — no network egress"


def test_shipped_plugin_wires_the_write_gate_to_the_canonical_python_guard():
    """Calling the shipped frozen_tests.py is what keeps one source of truth across ecosystems."""
    js = _PLUGIN_JS.read_text(encoding="utf-8")
    assert '"tool.execute.before": makeWriteGate' in js, "plugin must register the write-gate hook"
    assert 'spawnSync("python3"' in js, "the gate must invoke the canonical python3 guard"
    assert 'path.join(PLUGIN_ROOT, "hooks", "frozen_tests.py")' in js, "must point at the shipped guard"
    # A spawn or python error must never brick an unrelated edit.
    assert "fail open" in js


def test_the_shipped_guard_is_the_same_file_claude_uses():
    """Byte-for-byte copies, so the write-gate logic can never diverge across ecosystems."""
    src = REPO_ROOT / "src" / "scripts" / "hooks"
    for name in ("frozen_tests.py", "hercules_state.py"):
        assert (_DIST_OPENCODE / "hooks" / name).read_bytes() == (src / name).read_bytes()


# ── End-to-end: the real Node plugin blocks a frozen edit via the real python3 guard ──
_HAVE_TOOLS = shutil.which("node") is not None and shutil.which("python3") is not None


@pytest.fixture
def opencode_with_active_build(tmp_path):
    """The committed plugin, plus an isolated ~/.hercules whose one active build freezes a test."""
    out = _DIST_OPENCODE
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
    """A real veto, not just its presence: the plugin must THROW rather than report."""
    plugin_js, proj, home = opencode_with_active_build
    verdict = _edit_verdict(plugin_js, proj, home, "tests/test_frozen.py")
    assert verdict.startswith("BLOCKED"), f"frozen edit must be denied, got {verdict!r}"
    assert "write-gate" in verdict


@pytest.mark.skipif(not _HAVE_TOOLS, reason="node + python3 required for the live gate check")
def test_the_real_plugin_allows_an_edit_to_a_non_frozen_file(opencode_with_active_build):
    plugin_js, proj, home = opencode_with_active_build
    assert _edit_verdict(plugin_js, proj, home, "src/feature.py") == "ALLOWED"


def _patch_verdict(plugin_js: Path, proj: Path, home: Path, patch_text: str) -> str:
    """Return 'BLOCKED'/'ALLOWED' for an `apply_patch` carrying *patch_text*, via the real node plugin."""
    js = f"""
    const p = require({json.dumps(str(plugin_js))});
    p.server({{directory: {json.dumps(str(proj))}}}).then((r) => {{
      try {{ r["tool.execute.before"]({{tool: "apply_patch"}}, {{args: {{patchText: {json.dumps(patch_text)}}}}}); }}
      catch (e) {{ console.log("BLOCKED:" + e.message); return; }}
      console.log("ALLOWED");
    }}).catch((e) => {{ console.error(e); process.exit(1); }});
    """
    res = subprocess.run(["node", "-e", js], capture_output=True, text=True,
                         env={**os.environ, "HOME": str(home)}, timeout=30)
    assert res.returncode == 0, res.stderr
    return res.stdout.strip().splitlines()[-1]


@pytest.mark.skipif(not _HAVE_TOOLS, reason="node + python3 required for the live gate check")
def test_the_real_plugin_blocks_a_frozen_file_in_a_later_patch_hunk(opencode_with_active_build):
    """The gate checks every hunk's file, not just the first."""
    plugin_js, proj, home = opencode_with_active_build
    patch = ("*** Begin Patch\n"
             "*** Update File: src/innocuous.py\n@@\n-x\n+y\n"
             "*** Update File: tests/test_frozen.py\n@@\n-a\n+b\n"
             "*** End Patch\n")
    verdict = _patch_verdict(plugin_js, proj, home, patch)
    assert verdict.startswith("BLOCKED"), f"a frozen file in a later hunk must be denied, got {verdict!r}"


@pytest.mark.skipif(not _HAVE_TOOLS, reason="node + python3 required for the live gate check")
def test_the_real_plugin_allows_a_multi_file_patch_with_no_frozen_file(opencode_with_active_build):
    plugin_js, proj, home = opencode_with_active_build
    patch = ("*** Begin Patch\n"
             "*** Update File: src/a.py\n@@\n-x\n+y\n"
             "*** Update File: src/b.py\n@@\n-a\n+b\n"
             "*** End Patch\n")
    assert _patch_verdict(plugin_js, proj, home, patch) == "ALLOWED"
