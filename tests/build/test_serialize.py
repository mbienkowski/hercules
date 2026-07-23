"""Spec 01 — the Claude serialization contract + the target registry / extensibility contract.

Frozen for spec-01-build-compiler-core (import paths migrated to the generic descriptor engine;
every behavioral assertion preserved verbatim).
"""
import pytest

from scripts.build import serialize

MODELS = {"claude-code": {"high": "opus", "medium": "sonnet", "low": "haiku"}}


def ClaudeCodeSerializer():
    """The registered claude-code serializer (kept as a callable so the assertions read unchanged)."""
    return serialize.get("claude-code")


def test_agent_definition_translates_model_tier_to_concrete_model_name():
    """When an agent's config specifies a general tier like "medium" rather than a specific
    model, the generated Claude Code agent file resolves it to the actual model name for that
    target ("sonnet") and writes the metadata fields in a fixed, predictable order -- so agents
    defined once work correctly regardless of which models back each tier."""
    fm = {"name": "challenger", "description": "d", "model_tier": "medium", "tools": "Read, Grep"}
    out = ClaudeCodeSerializer().serialize_agent(fm, "# Challenger\n", {}, MODELS)
    assert out == (
        "---\n"
        "name: challenger\n"
        "description: d\n"
        "model: sonnet\n"
        "tools: Read, Grep\n"
        "---\n\n"
        "# Challenger\n"
    )


def test_agent_without_explicit_tools_list_omits_tools_field():
    """When an agent definition doesn't restrict which tools it can use, the generated file
    leaves the tools field out entirely rather than writing an empty or placeholder value, so
    the agent correctly inherits full tool access by default."""
    fm = {"name": "hercules", "description": "d", "model_tier": "high"}
    out = ClaudeCodeSerializer().serialize_agent(fm, "# Hercules\n", {}, MODELS)
    assert "\ntools:" not in out
    assert "model: opus\n" in out


def test_a_new_output_format_can_be_registered_and_then_found_by_name():
    """Adding support for a new output target -- a new place agents can be exported to --
    registers it under its name, so it can later be looked up by that name and shows up in the
    list of all available targets. This is the plug-in point new output formats rely on."""
    class _Stub:
        target = "stub-target"

        def serialize_agent(self, frontmatter, body, tokens, models):
            return body

    serialize.register(_Stub())
    assert serialize.get("stub-target").target == "stub-target"
    assert "stub-target" in serialize.registered_targets()


def test_requesting_an_unregistered_output_format_fails_clearly():
    """Asking for an output target that was never registered raises an error immediately,
    rather than silently returning nothing or failing later with a confusing error."""
    with pytest.raises(KeyError):
        serialize.get("does-not-exist")


def test_agent_missing_required_fields_fails_with_a_helpful_error():
    """If an agent's source definition is missing a required field like its name or
    description, serializing it fails with a clear message naming the missing field, instead of
    a cryptic internal error -- so whoever is authoring the agent can find and fix the problem."""
    with pytest.raises(serialize.SerializeError, match="description"):
        ClaudeCodeSerializer().serialize_agent({"name": "challenger"}, "# Challenger\n", {}, MODELS)
    with pytest.raises(serialize.SerializeError, match="name"):
        serialize.get("opencode").serialize_agent({"description": "d"}, "# X\n", {}, MODELS)
