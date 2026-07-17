"""Parity: the standalone ``dist/opencode/{agents,commands}/*.md`` files mirror the plugin.js entries.

OpenCode loads agents/commands at runtime from the inlined ``cfg.agent`` / ``cfg.command`` maps in
``plugin.js`` (built by ``cli._opencode_agents_and_commands``) — NOT from these standalone ``.md``
files, which are emitted as a human-readable, diff-friendly mirror. Two independent code paths render
the same source (``cli._opencode_agents_and_commands`` vs ``OpenCodeSerializer``), so this guards them
against silently diverging (the class of bug N5 fixed: one path rendered the description, the other
didn't).
"""
from __future__ import annotations

from scripts.build import cli
from scripts.build.parse import parse_frontmatter, split_document
from scripts.build.serialize import serialize_file


def _standalone_fields(kind: str, name: str, tokens: dict, models: dict) -> tuple[dict, str]:
    src = cli.SRC_CONTENT / kind / f"{name}.md"
    out = serialize_file("opencode", src.read_text(encoding="utf-8"), tokens, models)
    fm_block, body = split_document(out)
    meta, _ = parse_frontmatter(fm_block)
    return meta, body.strip()


def test_opencode_agents_mirror_plugin_js_entries():
    tokens, models = cli._load_tokens("opencode"), cli._load_models()
    agents, _ = cli._opencode_agents_and_commands(tokens)
    assert agents, "expected OpenCode agent entries"
    for name, meta, body in agents:
        sm, sbody = _standalone_fields("agents", name, tokens, models)
        assert sm["description"] == meta["description"], f"{name}: description diverged"
        assert sm["mode"] == meta["mode"], f"{name}: mode diverged"
        assert sbody == body, f"{name}: body diverged"


def test_opencode_commands_mirror_plugin_js_entries():
    tokens, models = cli._load_tokens("opencode"), cli._load_models()
    _, commands = cli._opencode_agents_and_commands(tokens)
    assert commands, "expected OpenCode command entries"
    for name, meta, body in commands:
        sm, sbody = _standalone_fields("commands", name, tokens, models)
        assert sm["description"] == meta["description"], f"{name}: description diverged"
        assert sm["agent"] == meta["agent"], f"{name}: agent diverged"
        assert sbody == body, f"{name}: body diverged"
