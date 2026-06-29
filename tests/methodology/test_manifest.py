"""Tests that verify plugin/settings.json structure and stays in sync with the filesystem."""

import json


def test_plugin_settings_has_required_keys(repo_root):
    """plugin/settings.json must declare all required manifest keys with correct types."""
    settings = json.loads((repo_root / "plugin" / "settings.json").read_text())
    assert isinstance(settings.get("agent"), str), "agent must be a string"
    assert isinstance(settings.get("advisors"), list), "advisors must be a list"
    assert isinstance(settings.get("skills"), list), "skills must be a list"
    assert isinstance(settings.get("commands"), list), "commands must be a list"
    assert settings["advisors"], "advisors must not be empty"
    assert settings["skills"], "skills must not be empty"
    assert settings["commands"], "commands must not be empty"


def test_command_list_matches_plugin_settings(repo_root):
    """plugin/settings.json commands[] must match files in plugin/commands/."""
    existing = {p.stem for p in (repo_root / "plugin" / "commands").glob("*.md")}
    settings = json.loads((repo_root / "plugin" / "settings.json").read_text())
    manifest = settings.get("commands", [])
    missing = [c for c in manifest if c not in existing]
    extra = [c for c in existing if c not in manifest]
    assert not missing, f"Commands in settings.json but missing from commands/: {missing}"
    assert not extra, f"Commands in commands/ but missing from settings.json: {extra}"


def test_plugin_settings_lists_are_sorted(repo_root):
    """advisors, skills, and commands in plugin/settings.json must be sorted a-z."""
    settings = json.loads((repo_root / "plugin" / "settings.json").read_text())
    for key in ("advisors", "skills", "commands"):
        lst = settings.get(key, [])
        assert lst == sorted(lst), (
            f"plugin/settings.json {key!r} is not sorted a-z.\n"
            f"  Expected: {sorted(lst)}\n"
            f"  Got:      {lst}"
        )
