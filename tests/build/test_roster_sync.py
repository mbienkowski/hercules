"""Spec 02 — the Claude-only settings.json roster stays in sync with src/content/agents/.

settings.json is authored as an inline artifact in the claude-code descriptor (emitted verbatim);
this sync test is the reader-end pin so a new agent can't ship without being registered. Frozen for
spec-02-claude-code-target.
"""
from pathlib import Path

from scripts.build.descriptor import discover

SRC = Path(__file__).resolve().parents[2] / "src"
AGENTS = SRC / "content" / "agents"


def _settings() -> dict:
    return next(a for a in discover()["claude-code"].artifacts if a.dest == "settings.json").content


def test_registered_agent_roster_matches_the_agents_that_actually_exist():
    """The agents registered for Claude Code (the default agent plus every advisor) must
    exactly match the agent files that exist in the content directory. This catches a new
    agent that was added but never registered, or a removed agent whose registration was
    left behind, before either ships to users."""
    settings = _settings()
    roster = {p.stem for p in AGENTS.glob("*.md")}
    listed = {settings["agent"], *settings["advisors"]}
    assert listed == roster, f"settings.json roster {listed} != content agents {roster}"


def test_hercules_is_the_default_agent():
    """Out of the box, with no explicit agent choice made, Claude Code must default to the
    hercules agent -- so users get the expected behavior on first run."""
    assert _settings()["agent"] == "hercules"
