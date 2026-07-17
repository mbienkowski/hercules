"""Spec 01 — the Claude serializer stub + the target registry / extensibility contract.

Frozen for spec-01-build-compiler-core.
"""
import pytest

from scripts.build import serialize
from scripts.build.serialize import ClaudeCodeSerializer

MODELS = {"claude-code": {"high": "opus", "medium": "sonnet", "low": "haiku"}}


def test_claude_agent_emits_model_from_tier_in_slot_order():
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


def test_claude_agent_without_tools_omits_the_key():
    fm = {"name": "hercules", "description": "d", "model_tier": "high"}
    out = ClaudeCodeSerializer().serialize_agent(fm, "# Hercules\n", {}, MODELS)
    assert "\ntools:" not in out
    assert "model: opus\n" in out


def test_registry_round_trips_and_lists_targets():
    class _Stub:
        target = "stub-target"

        def serialize_agent(self, frontmatter, body, tokens, models):
            return body

    serialize.register(_Stub())
    assert serialize.get("stub-target").target == "stub-target"
    assert "stub-target" in serialize.registered_targets()


def test_get_unknown_target_raises():
    with pytest.raises(KeyError):
        serialize.get("does-not-exist")


def test_missing_required_field_raises_a_scripted_message():
    """A source artifact missing name/description fails with an actionable message, not a bare KeyError."""
    with pytest.raises(serialize.SerializeError, match="description"):
        ClaudeCodeSerializer().serialize_agent({"name": "challenger"}, "# Challenger\n", {}, MODELS)
    with pytest.raises(serialize.SerializeError, match="name"):
        serialize.OpenCodeSerializer().serialize_agent({"description": "d"}, "# X\n", {}, MODELS)
