"""Tests that verify dist/claude-code/settings.json structure and stays in sync with the filesystem."""

import json


def test_installed_plugin_declares_its_agent_advisors_skills_and_commands(repo_root):
    """The plugin package that ships to users must describe itself completely: an agent name,
    plus non-empty lists of advisors, skills, and commands. If any of these is missing or the
    wrong type, Claude Code would install a plugin that silently lacks capabilities the user
    expects."""
    settings = json.loads((repo_root / "dist" / "claude-code" / "settings.json").read_text())
    assert isinstance(settings.get("agent"), str), "agent must be a string"
    assert isinstance(settings.get("advisors"), list), "advisors must be a list"
    assert isinstance(settings.get("skills"), list), "skills must be a list"
    assert isinstance(settings.get("commands"), list), "commands must be a list"
    assert settings["advisors"], "advisors must not be empty"
    assert settings["skills"], "skills must not be empty"
    assert settings["commands"], "commands must not be empty"


def test_every_shipped_command_file_is_listed_and_vice_versa(repo_root):
    """Every command file placed in the plugin's commands folder must be listed in the plugin's
    manifest, and every command named in the manifest must have a matching file. A mismatch
    would leave a shipped command invisible to users, or advertise a command that doesn't
    actually exist."""
    existing = {p.stem for p in (repo_root / "dist" / "claude-code" / "commands").glob("*.md")}
    settings = json.loads((repo_root / "dist" / "claude-code" / "settings.json").read_text())
    manifest = settings.get("commands", [])
    missing = [c for c in manifest if c not in existing]
    extra = [c for c in existing if c not in manifest]
    assert not missing, f"Commands in settings.json but missing from commands/: {missing}"
    assert not extra, f"Commands in commands/ but missing from settings.json: {extra}"
