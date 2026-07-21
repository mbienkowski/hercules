"""OpenCode target: the generated ``plugin.js`` entrypoint + inlined agent/command maps.

Capability prose lives in ``src/targets/opencode/CAPABILITIES.md`` (copied verbatim by ``emit_shared``).
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.build import emit
from scripts.build.manifests import generate_opencode_json, generate_plugin_js
from scripts.build.parse import parse_frontmatter, split_document
from scripts.build.render import render_body
from scripts.build.serialize import require_field
from scripts.build.targets.base import ExtrasContext, Target, emit_shared, register


def _agents_and_commands(src_content: Path, tokens: dict[str, str]):
    """Collect ``(name, meta, opencode-rendered-prompt)`` triples for the plugin.js inline entries."""
    agents = []
    for src in sorted((src_content / "agents").glob("*.md")):
        text = src.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        _, body = split_document(text)
        agents.append((
            src.stem,
            {"description": render_body(require_field(meta, "description"), "opencode", tokens),
             "mode": "primary" if src.stem == "hercules" else "subagent"},
            render_body(body, "opencode", tokens).strip(),
        ))
    commands = []
    for src in sorted((src_content / "commands").glob("*.md")):
        text = src.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        _, body = split_document(text)
        commands.append((
            src.stem,
            {"description": render_body(require_field(meta, "description"), "opencode", tokens),
             "agent": "hercules"},
            render_body(body, "opencode", tokens).strip(),
        ))
    return agents, commands


def _extras(ctx: ExtrasContext) -> list[str]:
    agents, commands = _agents_and_commands(ctx.src_content, ctx.tokens)
    emit.write(ctx.out_root / "plugin.js", generate_plugin_js("hercules", agents, commands))
    emit.write(ctx.out_root / "opencode.json", json.dumps(generate_opencode_json(), indent=2) + "\n")
    written = ["plugin.js", "opencode.json"]
    # Via emit_shared: the canonical Python guard + its state reader (which the generated plugin.js
    # invokes as its write-gate) + CAPABILITIES.md.
    written += emit_shared(ctx, "frozen_tests.py", "hercules_state.py")
    return written


register(Target(
    name="opencode",
    renames={"persona.md": "instructions.md"},
    emit_extras_fn=_extras,
))
