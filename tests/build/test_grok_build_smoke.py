"""Grok Build smoke: the built plugin is structurally installable; live `grok` CLI check when present.

The structural checks never skip (so the CI leg produces "N passed" without secrets); the live-CLI
check skips cleanly when `grok` is absent, mirroring the Cursor smoke pattern.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_CONTENT = REPO_ROOT / "src" / "content"
DIST = REPO_ROOT / "dist" / "grok-build"


def _src_stems(sub):
    return sorted(p.stem for p in (SRC_CONTENT / sub).glob("*.md"))


def _src_skills():
    return sorted(d.name for d in (SRC_CONTENT / "skills").iterdir() if d.is_dir())


def test_marketplace_descriptor_points_at_the_built_plugin():
    mp = json.loads((REPO_ROOT / ".grok-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert mp["plugins"][0]["source"] == "./dist/grok-build"
    assert (DIST / ".grok-plugin" / "plugin.json").is_file()


def test_built_plugin_ships_the_core_components():
    for rel in (".grok-plugin/plugin.json", "CLAUDE.md", "hooks/hooks.json",
                "hooks/frozen_tests.py", "hooks/hercules_state.py",
                "agents/hercules.md", "commands/build.md", "settings.json"):
        assert (DIST / rel).is_file(), f"grok-build plugin missing {rel}"


def test_ships_the_full_component_inventory():
    """The installed plugin must carry the WHOLE inventory — all 5 commands, every advisor agent, and
    every skill — so nothing silently fails to load. Names derive from src/content (the single source
    of truth), so a dropped or renamed component fails here rather than shipping a half-loaded plugin."""
    for name in _src_stems("commands"):
        assert (DIST / "commands" / f"{name}.md").is_file(), f"grok-build missing command {name}"
    for name in _src_stems("agents"):
        assert (DIST / "agents" / f"{name}.md").is_file(), f"grok-build missing agent {name}"
    for skill in _src_skills():
        assert (DIST / "skills" / skill / "SKILL.md").is_file(), f"grok-build missing skill {skill}"
    assert (DIST / "CLAUDE.md").is_file(), "grok-build persona instructions (CLAUDE.md) must ship"


@pytest.mark.skipif(shutil.which("grok") is None, reason="grok CLI not installed")
def test_grok_cli_is_available():
    r = subprocess.run(["grok", "--version"], capture_output=True, text=True)
    assert r.returncode == 0, "grok --version must succeed once the CLI is installed"
