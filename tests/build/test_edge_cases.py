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
def test_a_file_with_no_metadata_header_keeps_its_full_content_as_body():
    """When a source file doesn't start with a metadata header block, parsing treats it as
    having no metadata at all and returns the entire file untouched as the body. This ensures
    plain files without a metadata header still build correctly instead of losing content."""
    meta, body = parse_frontmatter("# Just a heading\ntext")
    assert meta == {} and body == "# Just a heading\ntext"


def test_a_metadata_block_missing_its_closing_marker_is_ignored():
    """If a file starts a metadata block but never closes it, the parser doesn't guess where
    it should end -- it treats the whole thing as having no metadata rather than misreading
    partial data. This avoids silently picking up garbage metadata from a malformed file."""
    meta, body = parse_frontmatter("---\nname: x\nno closing fence")
    assert meta == {}


def test_a_metadata_line_missing_a_colon_is_skipped_without_breaking_the_rest():
    """When a metadata block contains a malformed line that isn't a key-value pair, that one
    line is ignored while every other valid metadata entry is still read correctly. This keeps
    a single typo from wiping out an agent's entire metadata."""
    meta, _ = parse_frontmatter("---\nname: x\njustaword\ndescription: y\n---\nbody")
    assert meta == {"name": "x", "description": "y"}


def test_a_document_with_an_unterminated_metadata_block_is_returned_as_plain_text():
    """If a document opens a metadata section but never closes it, splitting the document
    reports that there is no metadata block and returns the original text unchanged as the
    body. This prevents a broken metadata fence from corrupting or truncating the content."""
    text = "---\nname: x\nnever closes"
    assert split_document(text) == (None, text)


def test_a_document_with_no_metadata_block_passes_through_unchanged():
    """A document that never starts a metadata section is recognized as having no metadata at
    all, and its full text is returned as-is. This is the normal path for plain content files,
    so it must never lose or alter the content."""
    assert split_document("# heading\nbody") == (None, "# heading\nbody")


# --- model_map -----------------------------------------------------------
def test_choosing_a_model_for_an_unconfigured_tier_yields_no_selection():
    """When a build target has no model configured for a requested tier, resolving that tier
    returns no model rather than crashing or guessing a default. Callers rely on this to know
    they should omit a model setting instead of writing a wrong one."""
    assert resolve({"empty": {}}, "empty", "low") is None


# --- render --------------------------------------------------------------
def test_a_template_ending_a_section_that_was_never_opened_fails_to_render():
    """If a template's content closes a target-specific section before ever opening one,
    rendering raises a clear error instead of silently producing malformed output. This catches
    a broken template early rather than shipping a corrupted generated file."""
    with pytest.raises(RenderError):
        render_body("${target:end}\nx", "claude-code", {})


# --- serialize -----------------------------------------------------------
def test_an_agent_with_no_model_tier_specified_gets_no_model_line_in_its_config():
    """When an agent definition doesn't specify a model tier at all, the generated Claude Code
    configuration omits the model setting entirely rather than writing a blank or default one.
    This lets Claude Code apply its own default model instead of being pinned to nothing."""
    fm = {"name": "n", "description": "d"}
    out = ClaudeCodeSerializer().serialize_agent(fm, "b\n", {}, {"claude-code": {}})
    assert "\nmodel:" not in out


def test_an_agent_whose_tier_is_explicitly_unmapped_gets_no_model_line():
    """When an agent requests a model tier that the target platform explicitly maps to 'no
    model', the generated configuration leaves out the model line rather than writing an
    invalid or empty value. This lets that platform fall back to its own default model."""
    fm = {"name": "n", "description": "d", "model_tier": "high"}
    out = ClaudeCodeSerializer().serialize_agent(fm, "b\n", {}, {"claude-code": {"high": None}})
    assert "\nmodel:" not in out


def test_claude_code_is_always_available_as_a_build_target():
    """The list of supported output targets always includes Claude Code by default, without
    any extra configuration. This guarantees that every project can build Claude Code agent
    files out of the box."""
    assert "claude-code" in serialize.registered_targets()
