"""Live Cursor CLI smoke check: does the real ``cursor-agent`` binary run, and is the built plugin
tree structurally loadable?

Cursor has no auth-free introspection equivalent to ``opencode agent list`` (only ``--version`` runs
without a paid key), so the ALWAYS-ON check is deliberately structural: prove the real binary executes
(not a stub) and re-validate the built ``dist/cursor`` plugin against the official component contract
(kebab manifest name, per-type frontmatter, ``.mdc`` rules, the reviewer subagent). The genuinely live
end-to-end run (a headless ``cursor-agent -p`` prompt) needs ``CURSOR_API_KEY`` and is therefore
opt-in — it SKIPs (never fails) on forks and unkeyed runs so the fork-safe gate stays green.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.build.cli import build_target

REPO_ROOT = Path(__file__).resolve().parents[2]
_TIMEOUT = 60

pytestmark = pytest.mark.skipif(shutil.which("cursor-agent") is None, reason="cursor-agent CLI not available")


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    return home


def test_the_real_cursor_agent_binary_runs_and_the_plugin_is_well_formed(isolated_home, tmp_path):
    """The real ``cursor-agent --version`` must exit 0 (a stub-on-PATH would not), and the freshly
    built plugin must satisfy the official component contract — the load-bearing, auth-free guard,
    since a malformed rule/agent loads as absent on Cursor with no error."""
    res = subprocess.run(["cursor-agent", "--version"], capture_output=True, text=True, timeout=_TIMEOUT)
    assert res.returncode == 0, f"cursor-agent --version failed: {res.stdout}\n{res.stderr}"

    out = tmp_path / "cursor"
    build_target("cursor", out)

    manifest = json.loads((out / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?", manifest["name"])

    def _fm(p: Path) -> str:
        t = p.read_text(encoding="utf-8")
        assert t.startswith("---\n"), f"{p.name} lacks frontmatter"
        return t

    for agent in (out / "agents").glob("*.md"):
        t = _fm(agent)
        assert "name:" in t and "description:" in t
    for cmd in (out / "commands").glob("*.md"):
        t = _fm(cmd)
        assert "name:" in t and "description:" in t
    persona = _fm(out / "rules" / "hercules-persona.mdc")
    assert "alwaysApply: true" in persona
    assert (out / "agents" / "cynical-reviewer.md").is_file(), "the independent reviewer must ship"


@pytest.mark.skipif(not os.environ.get("CURSOR_API_KEY"), reason="CURSOR_API_KEY not set (keyed live run)")
def test_the_real_cursor_agent_runs_a_headless_prompt(isolated_home):
    """With a key present, the real binary must complete one trivial headless prompt end-to-end —
    proving auth + the CLI drive a run (the deterministic-independent-review path uses this same
    ``cursor-agent -p`` mode). Non-required and main-only; skips on forks."""
    res = subprocess.run(
        ["cursor-agent", "-p", "Reply with the single word OK.", "--output-format", "text"],
        capture_output=True, text=True, timeout=_TIMEOUT,
    )
    assert res.returncode == 0, f"headless cursor-agent run failed: {res.stdout}\n{res.stderr}"
