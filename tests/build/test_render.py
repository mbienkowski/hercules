"""Spec 01 — the token/switch resolver: allowlist + passthrough, byte-preserving, hard cases.

Frozen for spec-01-build-compiler-core.
"""
import pytest

from scripts.build.render import RenderError, render_body

TOKENS = {"cmd.design": "/hercules:design", "instructions_file": "CLAUDE.md", "host_name": "Claude"}


def test_a_known_placeholder_is_replaced_with_its_real_value():
    """A recognized placeholder like ${cmd.design} in a template is swapped for the actual
    value configured for it, so generated instructions point users to the real command instead
    of a raw placeholder."""
    assert render_body("Run ${cmd.design} now", "claude-code", TOKENS) == "Run /hercules:design now"


def test_other_tools_own_placeholders_are_left_untouched():
    """Placeholder-looking text that belongs to another tool (such as Claude Code's own
    ${CLAUDE_PLUGIN_ROOT} runtime variable) is not Hercules's to resolve, so it must be copied
    through exactly as written rather than altered or stripped."""
    # ${CLAUDE_PLUGIN_ROOT} is Claude Code's own runtime variable — must survive untouched.
    src = 'command: "${CLAUDE_PLUGIN_ROOT}/hooks/frozen_tests.py"'
    assert render_body(src, "claude-code", TOKENS) == src


def test_a_placeholder_with_no_known_value_is_left_as_is():
    """When a template contains a placeholder that isn't one of the known, defined values,
    rendering does not fail -- the placeholder is kept in the output unchanged rather than
    causing an error."""
    # A bare ${...} that is NOT in the token map is treated as passthrough, never an error.
    assert render_body("${SOME_OTHER}", "claude-code", TOKENS) == "${SOME_OTHER}"


def test_target_specific_instructions_are_picked_for_the_matching_tool():
    """A template can offer different instructions per target tool (for example Claude Code
    versus OpenCode); rendering for a given tool selects only that tool's section and discards
    the others, so each user only sees instructions relevant to their own setup."""
    src = "${target:claude}\nUse EnterPlanMode.\n${target:opencode}\nUse OpenCode plan mode.\n${target:end}"
    assert render_body(src, "claude-code", TOKENS) == "Use EnterPlanMode."
    assert render_body(src, "opencode", TOKENS) == "Use OpenCode plan mode."


def test_an_unlisted_target_tool_gets_the_default_instructions():
    """If a template has no section written specifically for the tool being rendered for,
    rendering falls back to the template's designated default section instead of producing
    nothing."""
    src = "${target:claude}\nA\n${target:default}\nB\n${target:end}"
    assert render_body(src, "cursor", TOKENS) == "B"


def test_no_matching_section_and_no_default_leaves_that_part_blank():
    """When a template has no instructions for a given tool and provides no fallback default,
    that portion of the output is simply omitted, while the surrounding text is preserved
    exactly around the gap."""
    src = "before\n${target:claude}\nA\n${target:end}\nafter"
    assert render_body(src, "opencode", TOKENS) == "before\n\nafter"


def test_instruction_text_containing_colons_and_pipes_is_not_misparsed():
    """Ordinary instruction text that happens to contain colons and pipe characters, such as
    'model: opus | tools: Read', must render exactly as written and not be mistaken for
    template syntax."""
    src = "${target:claude}\nmodel: opus | tools: Read | see satisfies:\n${target:end}"
    assert render_body(src, "claude-code", TOKENS) == "model: opus | tools: Read | see satisfies:"


def test_a_placeholder_in_the_middle_of_a_sentence_is_replaced_correctly():
    """A known placeholder embedded inside a normal sentence, not sitting on its own line, is
    still recognized and replaced with its real value, leaving the rest of the sentence
    intact."""
    assert render_body("see ${cmd.design}, then go", "claude-code", TOKENS) == "see /hercules:design, then go"


def test_a_placeholder_inside_a_code_block_is_still_replaced():
    """Placeholders written inside a fenced code block are resolved the same way as anywhere
    else in the document, so example code shown to users displays the real command rather than
    a raw placeholder."""
    src = "```\n${cmd.design}\n```"
    assert render_body(src, "claude-code", TOKENS) == "```\n/hercules:design\n```"


def test_a_target_section_missing_its_closing_marker_fails_loudly():
    """If a template starts a per-tool instructions section but never closes it, rendering
    stops with an error instead of silently producing malformed or truncated output."""
    with pytest.raises(RenderError):
        render_body("${target:claude}\nA", "claude-code", TOKENS)


def test_an_unrecognized_section_directive_fails_loudly_instead_of_being_ignored():
    """If a template uses a directive that isn't one of the recognized section markers, such as
    a misspelled one, rendering stops with an error rather than silently treating it as plain
    text, which would let the typo slip through unnoticed."""
    with pytest.raises(RenderError):
        render_body("${target:claude}\nA\n${target:bogusdirective x}\n${target:end}", "claude-code", TOKENS)


def test_surrounding_text_and_whitespace_are_left_exactly_as_written():
    """Outside of placeholders and template markers, every character of the original document
    -- blank lines, indentation, tabs, trailing spaces -- is carried through to the output
    unchanged, so rendering never silently reformats a user's content."""
    src = "line1\n\n  indented\ttab\n${cmd.design}\ntrailing  \n"
    out = render_body(src, "claude-code", TOKENS)
    assert out == "line1\n\n  indented\ttab\n/hercules:design\ntrailing  \n"
