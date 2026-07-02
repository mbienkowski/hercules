"""Structural wiring tests for the plugin's hooks manifest.

`plugin/hooks/hooks.json` auto-loads by convention at the plugin root (no plugin.json key
needed). These tests pin that it is valid, registers the frozen-tests guard on the mutating
tools, and that every referenced command path resolves to a real script under the package —
a hooks.json that points at a missing script is a dead guard.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
_HOOKS = _PLUGIN / "hooks" / "hooks.json"


@pytest.fixture(scope="module")
def hooks():
    return json.loads(_HOOKS.read_text())


def test_hooks_json_is_valid_and_declares_pretooluse(hooks):
    assert "PreToolUse" in hooks.get("hooks", {}), "hooks.json must declare a PreToolUse hook"


def test_frozen_tests_guard_matches_the_mutating_tools(hooks):
    matchers = [entry.get("matcher", "") for entry in hooks["hooks"]["PreToolUse"]]
    joined = " ".join(matchers)
    for tool in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
        assert re.search(rf"\b{tool}\b", joined), f"the frozen-tests guard must match {tool}"


def test_every_hook_script_has_a_test():
    """Every shipped `plugin/hooks/*.py` must be exercised by a test under `tests/hooks/` — the CoC
    invariant 'every shipped artifact has an owning test', enforced for hook code specifically."""
    scripts = {p.stem for p in (_PLUGIN / "hooks").glob("*.py")}
    tests_src = " ".join(
        p.read_text() for p in Path(__file__).resolve().parent.glob("test_*.py")
    )
    missing = sorted(s for s in scripts if s not in tests_src)
    assert not missing, f"hook scripts with no owning test under tests/hooks/: {missing}"


def test_every_hook_command_script_exists(hooks):
    for event in hooks["hooks"].values():
        for entry in event:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                m = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+?\.py)", cmd)
                assert m, f"hook command must invoke a ${{CLAUDE_PLUGIN_ROOT}} script: {cmd!r}"
                script = _PLUGIN / m.group(1)
                assert script.is_file(), f"hook references a missing script: {script}"
