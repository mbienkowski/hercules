"""The generic descriptor-driven serializer — ``scripts/build/genserialize.py``.

Exact-output pins for every mode, field generator, dispatcher, and route kind, carrying the
mutation-killing power the per-ecosystem serializer tests had over ``serialize.py`` onto the engine.
Specs come from the SHIPPED descriptors (so the pins also freeze the real ecosystems' data) plus
synthetic descriptors for branches no shipped ecosystem exercises.
"""
from __future__ import annotations

import pytest

from scripts.build.descriptor import discover, parse_descriptor
from scripts.build.genserialize import (
    DescriptorSerializer,
    SerializeError,
    compute_fields,
    dest,
    toml_basic,
    toml_command,
    toml_multiline,
)

DESCRIPTORS = discover()

AGENT_SRC = """---
name: backend-engineer
description: Implements ${product} backends
model_tier: high
tools: Read, Edit
---

Do the work for ${product}.
"""

COMMAND_SRC = """---
description: Build the thing
disable-model-invocation: true
---

Run the build on ${product}.
"""


def _ser(name: str) -> DescriptorSerializer:
    return DescriptorSerializer(DESCRIPTORS[name])


def test_preserve_swaps_model_tier_in_slot_for_the_resolved_model():
    """claude-code: ``model_tier`` becomes ``model:`` in the SAME slot; every other key and the
    key order survive; body tokens render."""
    out = _ser("claude-code").serialize_file(AGENT_SRC, {"product": "Claude Code"}, rel="agents/backend-engineer.md")
    assert out == (
        "---\nname: backend-engineer\ndescription: Implements ${product} backends\n"
        "model: opus\ntools: Read, Edit\n---\n\nDo the work for Claude Code.\n"
    )


def test_preserve_drops_the_model_line_entirely_on_a_null_tier():
    """grok-build maps every tier to null — the ``model_tier`` line vanishes with no residue."""
    out = _ser("grok-build").serialize_file(AGENT_SRC, {"product": "Grok Build"}, rel="agents/backend-engineer.md")
    assert out == (
        "---\nname: backend-engineer\ndescription: Implements ${product} backends\n"
        "tools: Read, Edit\n---\n\nDo the work for Grok Build.\n"
    )


def test_preserve_passes_raw_frontmatter_through_when_no_model_tier():
    """A command's frontmatter (no ``model_tier``) is raw bytes — never re-rendered, never joined
    with an extra blank line (the block ends ``---\\n`` and the body starts ``\\n``)."""
    out = _ser("claude-code").serialize_file(COMMAND_SRC, {"product": "Claude Code"}, rel="commands/build.md")
    assert out == (
        "---\ndescription: Build the thing\ndisable-model-invocation: true\n---\n\n"
        "Run the build on Claude Code.\n"
    )


def test_preserve_never_token_renders_frontmatter_values():
    """The claude description ships RAW (``${product}`` intact) — only the body renders."""
    out = _ser("claude-code").serialize_file(AGENT_SRC, {"product": "Claude Code"}, rel="agents/x.md")
    assert "description: Implements ${product} backends" in out


def test_preserve_required_fields_fail_loud_when_missing():
    src = "---\ndescription: An agent with no name\nmodel_tier: high\ntools: Read\n---\n\nBody.\n"
    with pytest.raises(SerializeError, match="'name'"):
        _ser("claude-code").serialize_file(src, {}, rel="agents/anon.md")


def test_fields_mode_rebuilds_frontmatter_and_renders_flagged_values():
    """opencode agent: ``name`` raw, ``description`` token-rendered, ``mode`` computed; the join is
    ``fm + blank line + body`` (the body's own leading newline preserved — two blank lines total)."""
    out = _ser("opencode").serialize_file(AGENT_SRC, {"product": "OpenCode"})
    assert out == (
        "---\nname: backend-engineer\ndescription: Implements OpenCode backends\n"
        "mode: subagent\n---\n\n\nDo the work for OpenCode.\n"
    )


def test_primary_mode_generator_marks_the_primary_agent():
    src = AGENT_SRC.replace("backend-engineer", "hercules")
    out = _ser("opencode").serialize_file(src, {"product": "OpenCode"})
    assert "\nmode: primary\n" in out


def test_command_lstrip_policy_removes_only_leading_newlines():
    """opencode command: the body's leading blank lines go, the trailing newline stays."""
    out = _ser("opencode").serialize_file(COMMAND_SRC, {"product": "OpenCode"})
    assert out == (
        "---\ndescription: Build the thing\nagent: hercules\n---\n\n"
        "Run the build on OpenCode.\n"
    )


def test_flag_if_name_in_emits_readonly_for_verdict_agents_only():
    ser = _ser("cursor")
    locked = ser.serialize_file(AGENT_SRC.replace("backend-engineer", "cynical-reviewer"),
                                {"product": "Cursor"}, rel="agents/cynical-reviewer.md")
    open_ = ser.serialize_file(AGENT_SRC, {"product": "Cursor"}, rel="agents/backend-engineer.md")
    assert "\nreadonly: true\n" in locked
    assert "readonly" not in open_


def test_stem_generator_names_a_cursor_command_from_its_source_rel():
    out = _ser("cursor").serialize_file(COMMAND_SRC, {"product": "Cursor"}, rel="commands/build.md")
    assert out.startswith("---\nname: build\ndescription: Build the thing\n---\n\n")


def test_stem_generator_fails_loud_without_a_source_stem():
    with pytest.raises(SerializeError, match="stem"):
        _ser("cursor").serialize_command({"description": "x"}, "Body.", {})


def test_wrap_mode_wraps_the_persona_as_an_always_applied_rule():
    out = _ser("cursor").serialize_file("Persona for ${product}.\n", {"product": "Cursor"}, rel="persona.md")
    assert out == (
        "---\ndescription: Hercules — the spec-first delivery methodology "
        "(Discover → Design → Build → Ship). Always-on persona and project instructions.\n"
        "alwaysApply: true\n---\n\nPersona for Cursor.\n"
    )


def test_plain_mode_renders_the_whole_text_verbatim():
    out = _ser("gemini-cli").serialize_file("\nPersona for ${product}.\n\n", {"product": "Gemini CLI"},
                                            rel="persona.md")
    assert out == "\nPersona for Gemini CLI.\n\n"


def test_toml_command_mode_emits_the_exact_gemini_layout():
    out = _ser("gemini-cli").serialize_file(COMMAND_SRC, {"product": "Gemini CLI"}, rel="commands/build.md")
    assert out == ('description = "Build the thing"\n\n'
                   'prompt = """\nRun the build on Gemini CLI.\n"""\n')


def test_toml_escapers_handle_backslashes_and_triple_quotes():
    """Direct pins for the escapers (mutation-gated): basic escapes backslash then quote; multiline
    doubles backslashes and breaks a 3-quote run by escaping exactly its third quote."""
    assert toml_basic('a"b\\c') == '"a\\"b\\\\c"'
    assert toml_multiline("plain") == "plain"
    assert toml_multiline("a\\b") == "a\\\\b"
    assert toml_multiline('a""b') == 'a""b'
    assert toml_multiline('x"""y') == 'x""\\"y'
    assert toml_multiline('""""') == '""\\""'


def test_toml_command_helper_escapes_both_slots():
    out = toml_command('He said "go"', 'a\\b')
    assert out == 'description = "He said \\"go\\""\n\nprompt = """\na\\\\b\n"""\n'


def test_frontmatterless_files_pass_through_every_non_persona_role():
    """A protocol (fm-less, default role) renders verbatim on a fields-mode ecosystem too."""
    out = _ser("copilot-cli").serialize_file("A protocol for ${product}.\n", {"product": "GitHub Copilot CLI"},
                                             rel="protocols/a2a.md")
    assert out == "A protocol for GitHub Copilot CLI.\n"


def test_frontmatter_dispatch_sniffs_agent_command_persona_and_default():
    ser = _ser("opencode")
    assert ser._role_by_frontmatter(AGENT_SRC) == "agent"
    assert ser._role_by_frontmatter(COMMAND_SRC) == "command"
    assert ser._role_by_frontmatter("No frontmatter at all.\n") == "persona"
    assert ser._role_by_frontmatter("---\nname: skill\ndescription: d\n---\n\nBody.\n") == "default"


def test_path_dispatch_routes_by_source_location():
    ser = _ser("claude-code")
    assert ser._role_by_path("persona.md") == "persona"
    assert ser._role_by_path("agents/x.md") == "agent"
    assert ser._role_by_path("commands/x.md") == "command"
    assert ser._role_by_path("skills/s/SKILL.md") == "default"
    assert ser._role_by_path(None) == "default"


def test_exact_route_relocates_and_identity_falls_through():
    d = DESCRIPTORS["gemini-cli"]
    assert dest(d, "persona.md") == "GEMINI.md"
    assert dest(d, "protocols/a2a.md") == "protocols/a2a.md"


def test_suffix_swap_requires_both_prefix_and_suffix():
    d = DESCRIPTORS["gemini-cli"]
    assert dest(d, "commands/build.md") == "commands/build.toml"
    assert dest(d, "protocols/x.md") == "protocols/x.md"          # prefix mismatch
    assert dest(d, "commands/notes.txt") == "commands/notes.txt"  # suffix mismatch


def test_copilot_routes_swap_agent_and_prompt_extensions():
    d = DESCRIPTORS["copilot-cli"]
    assert dest(d, "agents/maintainer.md") == "agents/maintainer.agent.md"
    assert dest(d, "commands/ship.md") == "commands/ship.prompt.md"
    assert dest(d, "persona.md") == "AGENTS.md"


def test_serialize_agent_sugar_matches_the_file_path_output():
    ser = _ser("claude-code")
    meta = {"name": "backend-engineer", "description": "Implements ${product} backends",
            "model_tier": "high", "tools": "Read, Edit"}
    out = ser.serialize_agent(meta, "Do the work for ${product}.", {"product": "Claude Code"})
    assert out == (
        "---\nname: backend-engineer\ndescription: Implements ${product} backends\n"
        "model: opus\ntools: Read, Edit\n---\n\nDo the work for Claude Code."
    )


def test_serialize_command_sugar_takes_an_explicit_stem():
    out = _ser("cursor").serialize_command({"description": "Build the thing"}, "\nBody.\n", {},
                                           stem="build")
    assert out == "---\nname: build\ndescription: Build the thing\n---\n\nBody.\n"


def test_serialize_persona_sugar_wraps_or_renders_per_mode():
    assert _ser("copilot-cli").serialize_persona("P for ${product}.\n", {"product": "GitHub Copilot CLI"}) \
        == "P for GitHub Copilot CLI.\n"
    assert _ser("cursor").serialize_persona("P.\n", {}).startswith("---\ndescription: Hercules")


def test_explicitly_passed_models_override_the_descriptor_row():
    """The tiering override contract: a models dict naming the target wins over descriptor data."""
    ser = _ser("claude-code")
    out = ser.serialize_agent({"name": "x", "description": "d", "model_tier": "high"}, "B.",
                              {}, models={"claude-code": {"high": "sonnet"}})
    assert "\nmodel: sonnet\n" in out


def test_compute_fields_orders_output_by_spec_order():
    fields = DESCRIPTORS["opencode"].roles["agent"].fields
    out = compute_fields(fields, {"name": "hercules", "description": "d"}, "opencode", {})
    assert list(out) == ["name", "description", "mode"]
    assert out["mode"] == "primary"


def test_corpus_guard_model_tier_appears_only_under_agents():
    """Freezes the corpus fact that makes path- and frontmatter-dispatch equivalent: ``model_tier``
    (the agent sniff marker) never appears outside ``agents/``. If a non-agent source ever gains it,
    opencode's frontmatter sniff and every path dispatcher would diverge — this fails FIRST."""
    from pathlib import Path
    src_content = Path(__file__).resolve().parents[2] / "src" / "content"
    for p in sorted(src_content.rglob("*.md")):
        rel = p.relative_to(src_content).as_posix()
        if not rel.startswith("agents/"):
            assert "model_tier:" not in p.read_text(encoding="utf-8"), \
                f"{rel}: model_tier outside agents/ breaks dispatch equivalence"


def test_corpus_guard_command_marker_appears_only_under_commands():
    """The companion guard: ``disable-model-invocation`` (the command sniff marker) never appears
    outside ``commands/`` — same dispatch-equivalence freeze as the model_tier guard."""
    from pathlib import Path
    src_content = Path(__file__).resolve().parents[2] / "src" / "content"
    for p in sorted(src_content.rglob("*.md")):
        rel = p.relative_to(src_content).as_posix()
        if not rel.startswith("commands/"):
            assert "disable-model-invocation" not in p.read_text(encoding="utf-8"), \
                f"{rel}: command marker outside commands/ breaks dispatch equivalence"


def test_synthetic_preserve_without_resolve_leaves_model_tier_untouched():
    """A preserve role NOT flagged resolve_model_tier is a pure byte passthrough."""
    raw = {
        "schema": 1, "name": "eco", "vars": {"product": "Eco"},
        "models": {"high": None, "medium": None, "low": None},
        "smoke": {"cli": "eco", "test": "t.py"}, "dispatch": "path",
        "roles": {"agent": {"mode": "preserve"}, "command": {"mode": "preserve"},
                  "persona": {"mode": "plain"}, "default": {"mode": "preserve"}},
        "routes": [],
    }
    ser = DescriptorSerializer(parse_descriptor("eco", raw))
    out = ser.serialize_file(AGENT_SRC, {"product": "Eco"}, rel="agents/x.md")
    assert "model_tier: high" in out and "\nmodel:" not in out
