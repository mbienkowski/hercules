"""Spec 02 — the Claude-only settings.json roster stays in sync with src/content/agents/.

settings.json is byte-copied (not generated) to guarantee byte-identity; this sync test is the
reader-end pin so a new agent can't ship without being registered. Frozen for spec-02-claude-code-target.
"""
import json
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
SETTINGS = SRC / "targets" / "claude-code" / "settings.json"
AGENTS = SRC / "content" / "agents"


def test_registered_agent_roster_matches_the_agents_that_actually_exist():
    """The agents registered for Claude Code (the default agent plus every advisor) must
    exactly match the agent files that exist in the content directory. This catches a new
    agent that was added but never registered, or a removed agent whose registration was
    left behind, before either ships to users."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    roster = {p.stem for p in AGENTS.glob("*.md")}
    listed = {settings["agent"], *settings["advisors"]}
    assert listed == roster, f"settings.json roster {listed} != content agents {roster}"


def test_hercules_is_the_default_agent():
    """Out of the box, with no explicit agent choice made, Claude Code must default to the
    hercules agent -- so users get the expected behavior on first run."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert settings["agent"] == "hercules"
