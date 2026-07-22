"""Live Copilot CLI smoke check: does the real ``copilot`` binary run, and is the built plugin tree
structurally loadable?

The ALWAYS-ON check is structural (never skips): re-validate the built ``dist/copilot-cli`` plugin
against the plugin contract (kebab manifest name, per-type frontmatter, ``.agent.md`` agents,
``.prompt.md`` commands, the ``preToolUse`` write-gate, the reviewer subagent). The genuinely live check
(the real ``copilot`` binary executes) is opt-in — it SKIPs (never fails) when the CLI is not installed,
so the fork-safe gate stays green.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.build.cli import build_target

_TIMEOUT = 60


def test_the_built_plugin_is_well_formed(tmp_path):
    """The freshly built plugin must satisfy the Copilot plugin contract — this is the load-bearing,
    auth-free, never-skipping guard (a malformed agent/command loads as absent with no error)."""
    out = tmp_path / "copilot-cli"
    build_target("copilot-cli", out)

    manifest = json.loads((out / "plugin.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", manifest["name"])

    def _fm(p: Path) -> str:
        t = p.read_text(encoding="utf-8")
        assert t.startswith("---\n"), f"{p.name} lacks frontmatter"
        return t

    for agent in (out / "agents").glob("*.agent.md"):
        t = _fm(agent)
        assert "name:" in t and "description:" in t
    for cmd in (out / "commands").glob("*.prompt.md"):
        assert "description:" in _fm(cmd)
    assert (out / "AGENTS.md").is_file(), "the persona instructions must ship"
    assert (out / "agents" / "cynical-reviewer.agent.md").is_file(), "the independent reviewer must ship"
    hooks = json.loads((out / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert hooks["hooks"]["preToolUse"], "the preToolUse write-gate must be wired"


@pytest.mark.skipif(shutil.which("copilot") is None, reason="copilot CLI not available")
def test_the_real_copilot_binary_runs(tmp_path):
    """With the CLI installed, the real ``copilot --version`` must exit 0 (a stub-on-PATH would not)."""
    res = subprocess.run(["copilot", "--version"], capture_output=True, text=True, timeout=_TIMEOUT)
    assert res.returncode == 0, f"copilot --version failed: {res.stdout}\n{res.stderr}"
