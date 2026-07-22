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
DIST = REPO_ROOT / "dist" / "grok-build"


def test_marketplace_descriptor_points_at_the_built_plugin():
    mp = json.loads((REPO_ROOT / ".grok-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert mp["plugins"][0]["source"] == "./dist/grok-build"
    assert (DIST / ".grok-plugin" / "plugin.json").is_file()


def test_built_plugin_ships_the_core_components():
    for rel in (".grok-plugin/plugin.json", "CLAUDE.md", "hooks/hooks.json",
                "hooks/frozen_tests.py", "hooks/hercules_state.py",
                "agents/hercules.md", "commands/build.md", "settings.json"):
        assert (DIST / rel).is_file(), f"grok-build plugin missing {rel}"


@pytest.mark.skipif(shutil.which("grok") is None, reason="grok CLI not installed")
def test_grok_cli_is_available():
    r = subprocess.run(["grok", "--version"], capture_output=True, text=True)
    assert r.returncode == 0, "grok --version must succeed once the CLI is installed"
