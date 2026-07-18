"""Spec 01 — targeted tests that kill surviving mutants (mutation-gate strengthening).

Each test pins a behaviour a surviving mutant would break. Frozen for spec-01-build-compiler-core.
"""
import pytest

from scripts.build.model_map import ModelMapError, resolve
from scripts.build.parse import parse_frontmatter, split_document
from scripts.build.render import RenderError, render_body


# model_map: fallback goes UP (low→high), never down — a requested high with only 'low' defined omits.
def test_requesting_a_high_tier_never_falls_back_to_a_lower_one():
    """When a target only defines a lower tier, asking for a higher tier must not silently
    return the lower tier's value -- fallback is only allowed to move up in capability, never
    down, so callers don't unknowingly end up with a weaker model than they asked for."""
    assert resolve({"t": {"low": "L"}}, "t", "high") is None


# parse_frontmatter: the body return value is real, not discarded.
def test_reading_a_documents_header_also_returns_its_content():
    """Parsing a document's metadata header must also hand back the text that follows it --
    if the body were silently dropped, every consumer that needs the actual content after
    the header would break."""
    meta, body = parse_frontmatter("---\nk: v\n---\nthe body")
    assert body == "the body"


# parse_frontmatter: a value may itself contain a colon (split on the first only).
def test_a_header_value_containing_a_colon_is_captured_in_full():
    """A metadata header value such as "a: b" contains a colon as part of its own text, not
    just as the key/value separator. Parsing must split only on the first colon so the rest
    of the value is preserved intact instead of being cut short."""
    meta, _ = parse_frontmatter("---\nkey: a: b\n---")
    assert meta == {"key": "a: b"}


# split_document: a real frontmatter file yields a non-None block starting/ending with the fence.
def test_splitting_a_document_separates_its_header_from_its_content():
    """Given a file that starts with a metadata header followed by content, splitting it must
    return the exact header block and the exact remaining content as two separate pieces, so
    downstream code can process each part correctly."""
    block, body = split_document("---\nname: x\n---\n\nbody")
    assert block == "---\nname: x\n---\n"
    assert body == "\nbody"


# split_document: a file ending exactly at the closing fence (no trailing newline) does not crash.
def test_a_document_with_no_text_after_its_header_does_not_crash():
    """A file that ends immediately after its metadata header, with no trailing newline or
    content, must still be split without error -- returning the header and an empty content
    string rather than crashing."""
    assert split_document("---\nk: v\n---") == ("---\nk: v\n---", "")


# render: a leading ${target:end} that still closes properly is an error, not a silent empty result.
def test_a_template_ending_before_it_starts_is_rejected_as_an_error():
    """If a template's content is closed off before any target section has actually begun,
    that's a malformed template -- it must raise an error immediately instead of being
    silently accepted just because a valid closing marker appears later in the file."""
    with pytest.raises(RenderError):
        render_body("${target:end}\nA\n${target:end}", "claude-code", {})


# render: when the target branch AND a default both exist, the target branch wins (break, not continue).
def test_a_targets_own_section_is_used_instead_of_the_default_section():
    """When a template defines both a section specific to the requested target and a generic
    default section, rendering must use the target-specific content -- the default is a
    fallback only, and must never override a more specific match."""
    src = "${target:claude}\nA\n${target:default}\nB\n${target:end}"
    assert render_body(src, "claude-code", {}) == "A"


# render: a multi-line branch keeps its newline separator.
def test_multi_line_template_content_keeps_its_line_breaks_when_rendered():
    """When the content for a target spans multiple lines, rendering must preserve the line
    breaks between them exactly -- collapsing them onto one line would corrupt the generated
    output."""
    src = "${target:claude}\nline1\nline2\n${target:end}"
    assert render_body(src, "claude-code", {}) == "line1\nline2"


# model_map / render: error messages carry their identifying text (kills message-string mutants).
def test_configuration_and_template_errors_explain_specifically_what_went_wrong():
    """When a model tier is unknown, a target has no configuration at all, a template section
    is left unclosed, or a template's target name is malformed, each failure must raise an
    error whose message names the specific problem -- so a developer debugging a build
    failure isn't left guessing which of several possible issues occurred."""
    with pytest.raises(ModelMapError, match="unknown tier"):
        resolve({"t": {}}, "t", "nope")
    with pytest.raises(ModelMapError, match="not configured"):
        resolve({}, "absent", "high")
    with pytest.raises(RenderError, match="unclosed"):
        render_body("${target:claude}\nA", "claude-code", {})
    with pytest.raises(RenderError, match="malformed"):
        render_body("${target:claude}\nA\n${target:bad name}\n${target:end}", "claude-code", {})
