"""Spec 02 — the Claude-only settings.json roster stays in sync with src/content/agents/.

settings.json is byte-copied (not generated) to guarantee byte-identity; this sync test is the
reader-end pin so a new agent can't ship without being registered. Frozen for spec-02-claude-code-target.
"""
import json
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
SETTINGS = SRC / "targets" / "claude-code" / "settings.json"
AGENTS = SRC / "content" / "agents"


def test_settings_advisors_match_the_content_roster():
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    roster = {p.stem for p in AGENTS.glob("*.md")}
    listed = {settings["agent"], *settings["advisors"]}
    assert listed == roster, f"settings.json roster {listed} != content agents {roster}"


def test_default_agent_is_hercules():
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert settings["agent"] == "hercules"
