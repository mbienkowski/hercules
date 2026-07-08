#!/usr/bin/env python3
"""Generate OpenCode artifacts from the Claude Code plugin source.

This script keeps the Claude Code plugin in plugin/ as the single source of truth
and emits OpenCode-compatible files under .opencode/ plus opencode.json at the
repo root. Run it after any change to plugin/.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / "plugin"
OPENCODE_DIR = REPO_ROOT / ".opencode"
OPENCODE_JSON = REPO_ROOT / "opencode.json"

# Map Claude-style model shorthands to OpenCode provider/model IDs.
# These are defaults; users can override in their own opencode.json.
MODEL_MAP = {
    "opus": "anthropic/claude-opus-4-6",
    "sonnet": "anthropic/claude-sonnet-4-6",
    "haiku": "anthropic/claude-haiku-3-5",
}

# Default models for the root opencode.json when no specific model is requested.
DEFAULT_MODEL = MODEL_MAP["sonnet"]
DEFAULT_SMALL_MODEL = MODEL_MAP["haiku"]


def transform_content(text: str) -> str:
    """Adapt Claude-specific guidance for OpenCode.

    The source files remain Claude-oriented; this only touches the generated
    OpenCode copies.
    """
    # Plan-mode tool calls become OpenCode plan-mode guidance.
    # Handle common phrasings first, then bare tool names.
    text = re.sub(
        r"\(before EnterPlanMode\)",
        "(before beginning OpenCode plan mode)",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\(after ExitPlanMode",
        "(after exiting OpenCode plan mode",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"`EnterPlanMode`",
        "**Begin OpenCode plan mode** (present the complete proposal before any write; edits stay gated until explicit approval)",
        text,
    )
    text = re.sub(
        r"`ExitPlanMode` \(auto\)",
        "**Exit OpenCode plan mode after explicit user approval**, then execute automatically",
        text,
    )
    text = re.sub(
        r"`ExitPlanMode`",
        "**Exit OpenCode plan mode after explicit user approval**, then execute",
        text,
    )
    # Fallbacks for any remaining bare references.
    text = re.sub(r"\bEnterPlanMode\b", "begin OpenCode plan mode", text)
    text = re.sub(r"\bExitPlanMode\b", "exit OpenCode plan mode", text)
    # Product name references (careful not to break "Claude" in model names, which
    # are handled separately via MODEL_MAP).
    text = re.sub(r"\bClaude Code\b", "OpenCode", text)
    text = re.sub(r"\bClaude\b", "OpenCode", text)
    return text


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse simple YAML-like frontmatter from a markdown file."""
    text = text.strip()
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    front_text = parts[1].strip()
    body = parts[2].strip()
    metadata: dict[str, str] = {}
    for line in front_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata, body


def render_frontmatter(metadata: dict[str, Any]) -> str:
    """Render frontmatter as markdown YAML."""
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def generate_markdown(src: Path, dest: Path, metadata: dict[str, Any] | None = None) -> None:
    """Copy a markdown file, transforming body and using the supplied frontmatter."""
    text = src.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    if metadata is None:
        metadata, _ = parse_frontmatter(text)
    transformed_body = transform_content(body)
    dest.write_text(render_frontmatter(metadata) + "\n\n" + transformed_body + "\n", encoding="utf-8")


def generate_opencode_json(default_agent: str, instructions: str, skills_path: str) -> dict[str, Any]:
    """Build the root opencode.json used when the repo is opened directly."""
    return {
        "$schema": "https://opencode.ai/config.json",
        "default_agent": default_agent,
        "model": DEFAULT_MODEL,
        "small_model": DEFAULT_SMALL_MODEL,
        "instructions": [instructions],
        "skills": {"paths": [skills_path]},
    }


def escape_ts_string(value: str) -> str:
    """Return a JSON-stringified TypeScript string literal."""
    return json.dumps(value, ensure_ascii=False)


def _ts_object_literal(obj: Any, indent: int = 8) -> str:
    """Render a JSON-serializable object as a TypeScript object literal."""
    spaces = " " * indent
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        items = []
        for k, v in obj.items():
            key = k if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", k) else escape_ts_string(k)
            items.append(f"{spaces}  {key}: {_ts_object_literal(v, indent + 2)},")
        return "{\n" + "\n".join(items) + f"\n{spaces}}}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        items = [f"{_ts_object_literal(v, indent + 2)}" for v in obj]
        return "[" + ", ".join(items) + "]"
    if isinstance(obj, str):
        return escape_ts_string(obj)
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if obj is None:
        return "null"
    return str(obj)


def generate_plugin_js(
    default_agent: str,
    agents: list[tuple[str, dict[str, Any], str]],
    commands: list[tuple[str, dict[str, Any], str]],
    instructions_path: str,
    skills_path: str,
) -> str:
    """Generate the OpenCode plugin entry point with inlined agents/commands.

    Uses CommonJS so it loads without a TypeScript toolchain and without needing
    import.meta or Node type declarations.
    """
    agent_entries: dict[str, dict[str, Any]] = {}
    for name, metadata, prompt in agents:
        entry: dict[str, Any] = {
            "description": metadata.get("description", ""),
            "mode": metadata.get("mode", "subagent"),
            "prompt": prompt,
        }
        if "model" in metadata:
            entry["model"] = metadata["model"]
        agent_entries[name] = entry

    command_entries: dict[str, dict[str, Any]] = {}
    for name, metadata, prompt in commands:
        entry = {
            "description": metadata.get("description", ""),
            "agent": metadata.get("agent", "hercules"),
            "template": prompt,
        }
        if "model" in metadata:
            entry["model"] = metadata["model"]
        command_entries[f"hercules:{name}"] = entry

    template = """// Generated by scripts/generate_opencode.py - do not edit manually.
const path = require("path");

// This file lives in opencode-plugin/; the repo root is one level up.
const PLUGIN_ROOT = path.resolve(__dirname, "..");

module.exports = async () => {
  return {
    config: (cfg) => {
      cfg.default_agent = __DEFAULT_AGENT__;
      cfg.instructions = [
        ...(cfg.instructions || []),
        path.join(PLUGIN_ROOT, __INSTRUCTIONS_PATH__),
      ];
      cfg.skills = cfg.skills || {};
      cfg.skills.paths = [
        ...(cfg.skills.paths || []),
        path.join(PLUGIN_ROOT, __SKILLS_PATH__),
      ];
      cfg.agent = { ...(cfg.agent || {}), ...__AGENT_ENTRIES__ };
      cfg.command = { ...(cfg.command || {}), ...__COMMAND_ENTRIES__ };
    },
  };
};
"""
    return (
        template
        .replace("__DEFAULT_AGENT__", json.dumps(default_agent, ensure_ascii=False))
        .replace("__INSTRUCTIONS_PATH__", json.dumps(instructions_path, ensure_ascii=False))
        .replace("__SKILLS_PATH__", json.dumps(skills_path, ensure_ascii=False))
        .replace("__AGENT_ENTRIES__", _ts_object_literal(agent_entries))
        .replace("__COMMAND_ENTRIES__", _ts_object_literal(command_entries))
    )


def main() -> int:
    settings_path = PLUGIN_DIR / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    default_agent = settings["agent"]
    advisors = settings["advisors"]
    skills = settings["skills"]
    commands = settings["commands"]

    # Ensure the default agent file exists.
    default_agent_src = PLUGIN_DIR / "agents" / f"{default_agent}.md"
    if not default_agent_src.exists():
        print(f"Error: default agent file not found: {default_agent_src}", file=sys.stderr)
        return 1

    # Wipe and recreate .opencode.
    if OPENCODE_DIR.exists():
        shutil.rmtree(OPENCODE_DIR)
    OPENCODE_DIR.mkdir()

    # Instructions: transformed CLAUDE.md.
    instructions_dest = OPENCODE_DIR / "instructions.md"
    claude_md = PLUGIN_DIR / "CLAUDE.md"
    instructions_dest.write_text(transform_content(claude_md.read_text(encoding="utf-8")) + "\n", encoding="utf-8")

    # Agents.
    agents_dir = OPENCODE_DIR / "agents"
    agents_dir.mkdir()
    agent_specs: list[tuple[str, dict[str, Any], str]] = []

    def process_agent(name: str, is_default: bool) -> None:
        src = PLUGIN_DIR / "agents" / f"{name}.md"
        if not src.exists():
            print(f"Warning: agent file missing: {src}", file=sys.stderr)
            return
        metadata, body = parse_frontmatter(src.read_text(encoding="utf-8"))
        metadata["name"] = name
        metadata["mode"] = "primary" if is_default else "subagent"
        # The `tools` field is Claude-specific (comma-separated string); OpenCode expects an object
        # under `permission` instead. Drop it so generated agents do not crash OpenCode's config loader.
        metadata.pop("tools", None)
        if "model" in metadata:
            metadata["model"] = MODEL_MAP.get(metadata["model"], metadata["model"])
        transformed_body = transform_content(body)
        generate_markdown(src, agents_dir / f"{name}.md", metadata)
        agent_specs.append((name, metadata, transformed_body))

    process_agent(default_agent, is_default=True)
    for name in advisors:
        if name == default_agent:
            continue
        process_agent(name, is_default=False)

    # Commands.
    commands_dir = OPENCODE_DIR / "commands"
    commands_dir.mkdir()
    command_specs: list[tuple[str, dict[str, Any], str]] = []
    for name in commands:
        src = PLUGIN_DIR / "commands" / f"{name}.md"
        if not src.exists():
            print(f"Warning: command file missing: {src}", file=sys.stderr)
            continue
        metadata, body = parse_frontmatter(src.read_text(encoding="utf-8"))
        metadata.pop("disable-model-invocation", None)
        metadata["agent"] = "hercules"
        if "model" in metadata:
            metadata["model"] = MODEL_MAP.get(metadata["model"], metadata["model"])
        transformed_body = transform_content(body)
        generate_markdown(src, commands_dir / f"{name}.md", metadata)
        command_specs.append((name, metadata, transformed_body))

    # Skills.
    skills_dir = OPENCODE_DIR / "skills"
    skills_dir.mkdir()
    for skill_name in skills:
        skill_src_dir = PLUGIN_DIR / "skills" / skill_name
        skill_dest_dir = skills_dir / skill_name
        if not skill_src_dir.exists():
            print(f"Warning: skill directory missing: {skill_src_dir}", file=sys.stderr)
            continue
        skill_dest_dir.mkdir()
        skill_md = skill_src_dir / "SKILL.md"
        if skill_md.exists():
            generate_markdown(skill_md, skill_dest_dir / "SKILL.md")
        # Copy any companion markdown files (e.g. coverage-map.md).
        for companion in skill_src_dir.glob("*.md"):
            if companion.name == "SKILL.md":
                continue
            shutil.copy2(companion, skill_dest_dir / companion.name)

    # Protocols.
    protocols_src = PLUGIN_DIR / "protocols"
    protocols_dest = OPENCODE_DIR / "protocols"
    if protocols_src.exists():
        shutil.copytree(protocols_src, protocols_dest)

    # Plugin entry point (outside .opencode/ so OpenCode does not try to install
    # plugin-dev dependencies for the local .opencode directory).
    plugin_dir = REPO_ROOT / "opencode-plugin"
    plugin_dir.mkdir(exist_ok=True)
    plugin_js = plugin_dir / "hercules.js"
    instructions_rel = str(instructions_dest.relative_to(REPO_ROOT))
    skills_rel = str(skills_dir.relative_to(REPO_ROOT))
    plugin_js.write_text(
        generate_plugin_js(default_agent, agent_specs, command_specs, instructions_rel, skills_rel),
        encoding="utf-8",
    )

    # Root opencode.json for project-level use.
    opencode_config = generate_opencode_json(default_agent, instructions_rel, skills_rel)
    OPENCODE_JSON.write_text(json.dumps(opencode_config, indent=2) + "\n", encoding="utf-8")

    print(f"Generated OpenCode artifacts in {OPENCODE_DIR.name}/ and {OPENCODE_JSON.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
