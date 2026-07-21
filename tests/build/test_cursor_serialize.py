"""Unit tests for ``CursorSerializer`` + ``cursor_dest`` — the pure, mutation-covered Cursor logic.

``serialize.py`` is in ``paths_to_mutate``; these exact-output tests kill mutants in the frontmatter
shaping and the destination routing (especially the ``.md`` -> ``.mdc`` persona extension, whose flip
is Cursor's dominant silent-fail).
"""
from __future__ import annotations

from scripts.build.serialize import CursorSerializer, cursor_dest

CUR = CursorSerializer()


def test_cursor_dest_relocates_only_the_persona():
    """persona.md becomes an .mdc rule; every other component keeps its source path (Cursor's
    agents/commands/skills dirs match src/content)."""
    assert cursor_dest("persona.md") == "rules/hercules-persona.mdc"
    assert cursor_dest("agents/cynical-reviewer.md") == "agents/cynical-reviewer.md"
    assert cursor_dest("commands/workflow.md") == "commands/workflow.md"
    assert cursor_dest("skills/hercules-reference/SKILL.md") == "skills/hercules-reference/SKILL.md"
    assert cursor_dest("protocols/workflow-protocol.md") == "protocols/workflow-protocol.md"


def test_agent_frontmatter_drops_model_and_tools():
    """A Cursor subagent carries only name+description — the Claude model_tier and tools are dropped
    (subagents inherit the user's model)."""
    meta = {"name": "backend-engineer", "description": "Implements server code.",
            "model_tier": "high", "tools": "Read, Write"}
    out = CUR.serialize_agent(meta, "Body here.", {})
    assert out == "---\nname: backend-engineer\ndescription: Implements server code.\n---\n\nBody here."


def test_readonly_set_is_exactly_the_gate_verdict_roles():
    """Pin the exact read-locked set, not just that its members get readonly:true — otherwise a
    wrong membership (a verdict-giver dropped, or a name typo'd) ships silently and a mutmut mutation
    of a name inside the frozenset survives (the per-agent build test reads the same live constant)."""
    assert CursorSerializer.readonly_agents == {
        "cynical-reviewer", "security-expert", "source-checker", "senior-qa-engineer", "maintainer",
    }


def test_reviewer_agent_is_read_locked():
    """Review/audit roles ship readonly:true so an isolated reviewer can never become an author —
    the cynical-reviewer especially, since the independent-review gate depends on it."""
    meta = {"name": "cynical-reviewer", "description": "Finds problems.", "model_tier": "high"}
    out = CUR.serialize_agent(meta, "Body.", {})
    assert "readonly: true" in out
    assert out.startswith("---\nname: cynical-reviewer\ndescription: Finds problems.\nreadonly: true\n---")


def test_non_reviewer_agent_is_not_read_locked():
    meta = {"name": "backend-engineer", "description": "Implements.", "model_tier": "high"}
    assert "readonly" not in CUR.serialize_agent(meta, "Body.", {})


def test_command_gets_stem_name_and_drops_claude_marker():
    """Commands need name (the file stem) + description for the official validator; Claude's
    disable-model-invocation marker is dropped."""
    meta = {"description": "Guided delivery.", "disable-model-invocation": "true"}
    out = CUR.serialize_command("workflow", meta, "Do the thing.", {})
    assert out == "---\nname: workflow\ndescription: Guided delivery.\n---\n\nDo the thing."


def test_persona_becomes_an_always_applied_rule():
    """The frontmatter-less persona is wrapped as an always-applied rule."""
    out = CUR.serialize_persona("# hercules\n\nInstructions.", {})
    assert out.startswith("---\ndescription: ")
    assert "\nalwaysApply: true\n---\n\n# hercules" in out


def test_switch_and_token_rendering_selects_the_cursor_branch():
    """The body is rendered for the cursor target: cursor switch branches are selected and ${var}
    tokens substituted."""
    body = "${target:opencode}\nOC\n${target:cursor}\nCUR\n${target:end}\nrun ${ns}design"
    meta = {"name": "hercules", "description": "d", "model_tier": "high"}
    out = CUR.serialize_agent(meta, body, {"ns": "/"})
    assert "CUR" in out and "OC" not in out
    assert "run /design" in out
