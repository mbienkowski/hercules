"""Structural wiring tests for the plugin's hooks manifest.

`src/targets/claude-code/hooks/hooks.json` auto-loads by convention at the plugin root (no plugin.json
key needed). These tests pin that it is valid, registers the frozen-tests guard on the mutating
tools, and that every referenced command path resolves to a real script under the package —
a hooks.json that points at a missing script is a dead guard.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[2] / "src" / "targets" / "claude-code"
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


def test_frozen_guard_uses_exec_form(hooks):
    """The frozen-tests guard is wired in hook exec form (`command` + `args`), the contemporary,
    marketplace-safe shape: `python3` is spawned directly with the script as one `args` element, so
    `${CLAUDE_PLUGIN_ROOT}` needs no shell quoting and a missing `python3` fails open (non-blocking).
    Scoped to the frozen guard so a future hook may legitimately choose shell form."""
    guard = next(
        (h for entry in hooks["hooks"]["PreToolUse"] for h in entry.get("hooks", [])
         if any("frozen_tests.py" in a for a in h.get("args", []))),
        None,
    )
    assert guard, "the frozen-tests guard must be wired via exec form with the script in `args`"
    assert guard["command"] == "python3", \
        f"exec form must spawn python3 directly, not a shell string: {guard['command']!r}"
    assert isinstance(guard.get("args"), list) and guard["args"], \
        "exec form must carry a non-empty `args` list (shell form has none)"


def test_every_hook_command_script_exists(hooks):
    for event in hooks["hooks"].values():
        for entry in event:
            for hook in entry.get("hooks", []):
                # Exec form puts the script path in `args`, shell form in the `command` string —
                # search both so the wiring holds regardless of invocation form.
                invocation = " ".join([hook.get("command", "")] + list(hook.get("args", [])))
                m = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+?\.py)", invocation)
                assert m, f"hook must invoke a ${{CLAUDE_PLUGIN_ROOT}} script: {hook!r}"
                script = _PLUGIN / m.group(1)
                assert script.is_file(), f"hook references a missing script: {script}"
