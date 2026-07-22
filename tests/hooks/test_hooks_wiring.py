"""Structural wiring tests for the plugin's hooks manifest.

Claude Code's ``hooks/hooks.json`` auto-loads by convention at the plugin root (no plugin.json key
needed); it is authored as an inline artifact in ``src/ecosystems/claude-code.json``. These tests
pin that it is valid, registers the frozen-tests guard on the mutating tools, and that every
referenced command path resolves to a real script in the BUILT plugin — a hooks.json that points at
a missing script is a dead guard.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.build.cli import build_target
from scripts.build.descriptor import discover


@pytest.fixture(scope="module")
def hooks():
    artifact = next(a for a in discover()["claude-code"].artifacts if a.dest == "hooks/hooks.json")
    return artifact.content


@pytest.fixture(scope="module")
def built_plugin(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("claude-code")
    build_target("claude-code", out)
    return out


def test_hooks_manifest_declares_a_check_that_runs_before_tools_execute(hooks):
    """The plugin's hooks manifest must declare a PreToolUse hook so guards such as the
    frozen-tests check actually run before a tool is allowed to act. Without this entry no
    safety check would ever fire, and mutating tools would run unchecked."""
    assert "PreToolUse" in hooks.get("hooks", {}), "hooks.json must declare a PreToolUse hook"


def test_frozen_tests_guard_watches_every_file_editing_tool(hooks):
    """The guard that protects frozen test files must be wired to trigger on every tool capable
    of changing a file: Edit, MultiEdit, Write, and NotebookEdit. If any one of these were left
    out, a locked test could be silently altered through that tool instead of being blocked."""
    matchers = [entry.get("matcher", "") for entry in hooks["hooks"]["PreToolUse"]]
    joined = " ".join(matchers)
    for tool in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
        assert re.search(rf"\b{tool}\b", joined), f"the frozen-tests guard must match {tool}"


def test_frozen_tests_guard_is_installed_so_a_missing_interpreter_never_blocks_work(hooks):
    """The guard that protects frozen tests is registered by launching its script as a direct
    program call rather than as a shell command string. That means the plugin's install path
    never needs special quoting, and on a machine without a Python interpreter available the
    guard simply does nothing instead of blocking every edit a user makes."""
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


def test_every_hook_points_to_a_script_that_actually_exists(hooks, built_plugin):
    """Every hook listed in the manifest must reference a script file that really ships in the
    BUILT plugin tree. A hook pointing at a missing script would silently fail to run, leaving
    whatever safety check it was supposed to provide completely disabled."""
    for event in hooks["hooks"].values():
        for entry in event:
            for hook in entry.get("hooks", []):
                # Exec form puts the script path in `args`, shell form in the `command` string —
                # search both so the wiring holds regardless of invocation form.
                invocation = " ".join([hook.get("command", "")] + list(hook.get("args", [])))
                m = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+?\.py)", invocation)
                assert m, f"hook must invoke a ${{CLAUDE_PLUGIN_ROOT}} script: {hook!r}"
                script = built_plugin / m.group(1)
                assert script.is_file(), f"hook references a missing script: {script}"
