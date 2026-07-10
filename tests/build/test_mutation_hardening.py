"""Spec 01 — targeted tests that kill surviving mutants (mutation-gate strengthening).

Each test pins a behaviour a surviving mutant would break. Frozen for spec-01-build-compiler-core.
"""
import pytest

from scripts.build.model_map import ModelMapError, resolve
from scripts.build.parse import parse_frontmatter, split_document
from scripts.build.render import RenderError, render_body


# model_map: fallback goes UP (low→high), never down — a requested high with only 'low' defined omits.
def test_fallback_does_not_descend_to_a_lower_tier():
    assert resolve({"t": {"low": "L"}}, "t", "high") is None


# parse_frontmatter: the body return value is real, not discarded.
def test_parse_frontmatter_returns_the_body():
    meta, body = parse_frontmatter("---\nk: v\n---\nthe body")
    assert body == "the body"


# parse_frontmatter: a value may itself contain a colon (split on the first only).
def test_parse_frontmatter_value_may_contain_a_colon():
    meta, _ = parse_frontmatter("---\nkey: a: b\n---")
    assert meta == {"key": "a: b"}


# split_document: a real frontmatter file yields a non-None block starting/ending with the fence.
def test_split_document_returns_the_frontmatter_block():
    block, body = split_document("---\nname: x\n---\n\nbody")
    assert block == "---\nname: x\n---\n"
    assert body == "\nbody"


# split_document: a file ending exactly at the closing fence (no trailing newline) does not crash.
def test_split_document_handles_no_trailing_newline_after_fence():
    assert split_document("---\nk: v\n---") == ("---\nk: v\n---", "")


# render: a leading ${target:end} that still closes properly is an error, not a silent empty result.
def test_leading_end_directive_is_an_error_even_when_a_later_end_exists():
    with pytest.raises(RenderError):
        render_body("${target:end}\nA\n${target:end}", "claude-code", {})


# render: when the target branch AND a default both exist, the target branch wins (break, not continue).
def test_matching_branch_wins_over_default():
    src = "${target:claude}\nA\n${target:default}\nB\n${target:end}"
    assert render_body(src, "claude-code", {}) == "A"


# render: a multi-line branch keeps its newline separator.
def test_multiline_branch_preserves_newlines():
    src = "${target:claude}\nline1\nline2\n${target:end}"
    assert render_body(src, "claude-code", {}) == "line1\nline2"


# model_map / render: error messages carry their identifying text (kills message-string mutants).
def test_error_messages_carry_identifying_text():
    with pytest.raises(ModelMapError, match="unknown tier"):
        resolve({"t": {}}, "t", "nope")
    with pytest.raises(ModelMapError, match="not configured"):
        resolve({}, "absent", "high")
    with pytest.raises(RenderError, match="unclosed"):
        render_body("${target:claude}\nA", "claude-code", {})
    with pytest.raises(RenderError, match="malformed"):
        render_body("${target:claude}\nA\n${target:bad name}\n${target:end}", "claude-code", {})
