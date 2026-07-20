"""Parity: the standalone ``dist/opencode/{agents,commands}/*.md`` files mirror the plugin.js entries.

OpenCode loads agents/commands at runtime from the inlined ``cfg.agent`` / ``cfg.command`` maps in
``plugin.js`` (built by ``targets.opencode._agents_and_commands``) — NOT from these standalone ``.md``
files, which are emitted as a human-readable, diff-friendly mirror. Two independent code paths render
the same source (``targets.opencode._agents_and_commands`` vs ``OpenCodeSerializer``), so this guards
them against silently diverging (the class of bug N5 fixed: one path rendered the description, the
other didn't).
"""
from __future__ import annotations

from scripts.build import cli
from scripts.build.parse import parse_frontmatter, split_document
from scripts.build.serialize import serialize_file
from scripts.build.targets.opencode import _agents_and_commands


def _standalone_fields(kind: str, name: str, tokens: dict, models: dict) -> tuple[dict, str]:
    src = cli.SRC_CONTENT / kind / f"{name}.md"
    out = serialize_file("opencode", src.read_text(encoding="utf-8"), tokens, models)
    fm_block, body = split_document(out)
    meta, _ = parse_frontmatter(fm_block)
    return meta, body.strip()


def test_every_opencode_agent_matches_its_human_readable_reference_copy():
    """Each OpenCode agent actually runs from the compiled data baked into plugin.js, but a
    separate, human-readable copy of the same agent is also kept on disk for people to review.
    This checks every agent's description, mode, and instructions are identical in both places,
    so someone reading the reference copy never gets misled about what actually runs."""
    tokens, models = cli._load_tokens("opencode"), cli._load_models()
    agents, _ = _agents_and_commands(cli.SRC_CONTENT, tokens)
    assert agents, "expected OpenCode agent entries"
    for name, meta, body in agents:
        sm, sbody = _standalone_fields("agents", name, tokens, models)
        assert sm["description"] == meta["description"], f"{name}: description diverged"
        assert sm["mode"] == meta["mode"], f"{name}: mode diverged"
        assert sbody == body, f"{name}: body diverged"


def test_every_opencode_command_matches_its_human_readable_reference_copy():
    """Each OpenCode command actually runs from the compiled data baked into plugin.js, but a
    separate, human-readable copy of the same command is also kept on disk for people to review.
    This checks every command's description, assigned agent, and instructions are identical in
    both places, so someone reading the reference copy never gets misled about what actually runs."""
    tokens, models = cli._load_tokens("opencode"), cli._load_models()
    _, commands = _agents_and_commands(cli.SRC_CONTENT, tokens)
    assert commands, "expected OpenCode command entries"
    for name, meta, body in commands:
        sm, sbody = _standalone_fields("commands", name, tokens, models)
        assert sm["description"] == meta["description"], f"{name}: description diverged"
        assert sm["agent"] == meta["agent"], f"{name}: agent diverged"
        assert sbody == body, f"{name}: body diverged"
