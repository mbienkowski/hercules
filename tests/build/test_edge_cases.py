"""Spec 01 — edge branches of the pure modules (coverage + mutation strengthening).

Frozen for spec-01-build-compiler-core.
"""
import pytest

from scripts.build import serialize
from scripts.build.model_map import resolve
from scripts.build.parse import parse_frontmatter, split_document
from scripts.build.render import RenderError, render_body
from scripts.build.serialize import ClaudeCodeSerializer


# --- parse ---------------------------------------------------------------
def test_parse_frontmatter_no_fence_returns_empty_and_text():
    meta, body = parse_frontmatter("# Just a heading\ntext")
    assert meta == {} and body == "# Just a heading\ntext"


def test_parse_frontmatter_single_fence_is_treated_as_no_frontmatter():
    meta, body = parse_frontmatter("---\nname: x\nno closing fence")
    assert meta == {}


def test_parse_frontmatter_skips_lines_without_a_colon():
    meta, _ = parse_frontmatter("---\nname: x\njustaword\ndescription: y\n---\nbody")
    assert meta == {"name": "x", "description": "y"}


def test_split_document_without_closing_fence_returns_none_block():
    text = "---\nname: x\nnever closes"
    assert split_document(text) == (None, text)


def test_split_document_without_opening_fence_returns_none_block():
    assert split_document("# heading\nbody") == (None, "# heading\nbody")


# --- model_map -----------------------------------------------------------
def test_resolve_returns_none_when_no_tier_configured():
    assert resolve({"empty": {}}, "empty", "low") is None


# --- render --------------------------------------------------------------
def test_leading_target_end_directive_raises():
    with pytest.raises(RenderError):
        render_body("${target:end}\nx", "claude-code", {})


# --- serialize -----------------------------------------------------------
def test_agent_without_model_tier_emits_no_model_line():
    fm = {"name": "n", "description": "d"}
    out = ClaudeCodeSerializer().serialize_agent(fm, "b\n", {}, {"claude-code": {}})
    assert "\nmodel:" not in out


def test_agent_with_tier_mapping_to_null_emits_no_model_line():
    fm = {"name": "n", "description": "d", "model_tier": "high"}
    out = ClaudeCodeSerializer().serialize_agent(fm, "b\n", {}, {"claude-code": {"high": None}})
    assert "\nmodel:" not in out


def test_registered_targets_includes_the_default_claude_serializer():
    assert "claude-code" in serialize.registered_targets()
