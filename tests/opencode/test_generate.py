"""Tests for the OpenCode artifact generator.

These tests verify that scripts/generate_opencode.py produces a valid, complete
OpenCode configuration from the Claude Code plugin source, and that the generated
plugin entry point can register the same agents/commands/skills at runtime.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def generated(repo_root: Path) -> Path:
    """Run the generator once and return the repo root."""
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "generate_opencode.py")],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"generate_opencode.py failed:\n{result.stderr}"
    return repo_root


def test_opencode_json_exists_and_is_valid(generated: Path):
    """opencode.json must exist, parse, and declare the expected top-level keys."""
    opencode_json = generated / "opencode.json"
    assert opencode_json.is_file(), "opencode.json was not generated"
    config = json.loads(opencode_json.read_text())
    assert config.get("$schema") == "https://opencode.ai/config.json"
    assert config.get("default_agent") == "hercules"
    assert config.get("model", "").startswith("anthropic/")
    assert config.get("small_model", "").startswith("anthropic/")
    assert isinstance(config.get("instructions"), list) and config["instructions"]
    assert isinstance(config.get("skills"), dict)
    assert isinstance(config["skills"].get("paths"), list) and config["skills"]["paths"]


def test_generated_agents_match_settings(generated: Path):
    """Every agent listed in plugin/settings.json must have a generated file."""
    settings = json.loads((generated / "plugin" / "settings.json").read_text())
    default_agent = settings["agent"]
    advisors = settings["advisors"]
    expected = {default_agent, *advisors}
    agents_dir = generated / ".opencode" / "agents"
    generated_agents = {p.stem for p in agents_dir.glob("*.md")}
    assert expected == generated_agents, (
        f"Agent set mismatch. Expected: {sorted(expected)}, got: {sorted(generated_agents)}"
    )


def test_generated_commands_match_settings(generated: Path):
    """Every command listed in plugin/settings.json must have a generated file."""
    settings = json.loads((generated / "plugin" / "settings.json").read_text())
    expected = set(settings["commands"])
    commands_dir = generated / ".opencode" / "commands"
    generated_commands = {p.stem for p in commands_dir.glob("*.md")}
    assert expected == generated_commands, (
        f"Command set mismatch. Expected: {sorted(expected)}, got: {sorted(generated_commands)}"
    )


def test_generated_skills_match_settings(generated: Path):
    """Every skill listed in plugin/settings.json must have a generated SKILL.md."""
    settings = json.loads((generated / "plugin" / "settings.json").read_text())
    expected = set(settings["skills"])
    skills_dir = generated / ".opencode" / "skills"
    generated_skills = {p.name for p in skills_dir.iterdir() if (p / "SKILL.md").is_file()}
    assert expected == generated_skills, (
        f"Skill set mismatch. Expected: {sorted(expected)}, got: {sorted(generated_skills)}"
    )


def test_agent_modes_are_correct(generated: Path):
    """The default agent is primary; every advisor is a subagent."""
    agents_dir = generated / ".opencode" / "agents"
    mode_re = re.compile(r"^mode:\s*(\S+)$", re.MULTILINE)
    for path in agents_dir.glob("*.md"):
        text = path.read_text()
        match = mode_re.search(text)
        assert match, f"{path.name} missing mode frontmatter"
        expected_mode = "primary" if path.stem == "hercules" else "subagent"
        assert match.group(1) == expected_mode, (
            f"{path.name} expected mode {expected_mode!r}, got {match.group(1)!r}"
        )


def test_no_claude_plan_mode_tools_remain(generated: Path):
    """Generated OpenCode artifacts must not reference Claude-only plan-mode tools."""
    opencode_dir = generated / ".opencode"
    offenders = []
    for path in opencode_dir.rglob("*.md"):
        text = path.read_text()
        if "EnterPlanMode" in text or "ExitPlanMode" in text:
            offenders.append(str(path.relative_to(generated)))
    assert not offenders, (
        "Generated files still contain Claude plan-mode tool names: " + ", ".join(offenders)
    )


def test_plugin_entry_point_loads_and_registers_config(generated: Path):
    """The generated CommonJS plugin must load and mutate a config object correctly."""
    plugin_path = generated / "opencode-plugin" / "hercules.js"
    assert plugin_path.is_file(), "plugin entry point was not generated"

    # Load via Node and capture the config mutation output.
    probe_script = f"""
    const plugin = require({json.dumps(str(plugin_path))});
    plugin().then(result => {{
      const cfg = {{}};
      result.config(cfg);
      console.log(JSON.stringify({{
        default_agent: cfg.default_agent,
        instructions: cfg.instructions,
        skills_paths: cfg.skills.paths,
        agents: Object.keys(cfg.agent).sort(),
        commands: Object.keys(cfg.command).sort(),
      }}));
    }});
    """
    result = subprocess.run(
        ["node", "-e", probe_script],
        cwd=generated,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Node plugin probe failed:\n{result.stderr}"
    emitted = json.loads(result.stdout.strip().splitlines()[-1])

    settings = json.loads((generated / "plugin" / "settings.json").read_text())
    expected_agents = sorted({settings["agent"], *settings["advisors"]})
    expected_commands = sorted(f"hercules:{name}" for name in settings["commands"])

    assert emitted["default_agent"] == "hercules"
    assert emitted["instructions"]
    assert emitted["skills_paths"]
    assert emitted["agents"] == expected_agents
    assert emitted["commands"] == expected_commands


def test_package_json_points_at_plugin_entry(generated: Path):
    """package.json must exist and reference the generated plugin entry point."""
    package_json = generated / "package.json"
    assert package_json.is_file(), "package.json is missing"
    manifest = json.loads(package_json.read_text())
    assert manifest.get("name") == "hercules"
    assert manifest.get("main") == "opencode-plugin/hercules.js"
