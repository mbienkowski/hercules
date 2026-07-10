"""Spec 01 — the token/switch resolver: allowlist + passthrough, byte-preserving, hard cases.

Frozen for spec-01-build-compiler-core.
"""
import pytest

from scripts.build.render import RenderError, render_body

TOKENS = {"cmd.design": "/hercules:design", "instructions_file": "CLAUDE.md", "host_name": "Claude"}


def test_allowlisted_token_is_substituted():
    assert render_body("Run ${cmd.design} now", "claude-code", TOKENS) == "Run /hercules:design now"


def test_unknown_dollar_brace_passes_through_verbatim():
    # ${CLAUDE_PLUGIN_ROOT} is Claude Code's own runtime variable — must survive untouched.
    src = 'command: "${CLAUDE_PLUGIN_ROOT}/hooks/frozen_tests.py"'
    assert render_body(src, "claude-code", TOKENS) == src


def test_undefined_but_allowlist_shaped_token_raises_only_when_declared_missing():
    # A bare ${...} that is NOT in the token map is treated as passthrough, never an error.
    assert render_body("${SOME_OTHER}", "claude-code", TOKENS) == "${SOME_OTHER}"


def test_switch_selects_matching_target_branch():
    src = "${target:claude}\nUse EnterPlanMode.\n${target:opencode}\nUse OpenCode plan mode.\n${target:end}"
    assert render_body(src, "claude-code", TOKENS) == "Use EnterPlanMode."
    assert render_body(src, "opencode", TOKENS) == "Use OpenCode plan mode."


def test_switch_falls_back_to_default_branch():
    src = "${target:claude}\nA\n${target:default}\nB\n${target:end}"
    assert render_body(src, "cursor", TOKENS) == "B"


def test_switch_with_no_matching_branch_and_no_default_emits_nothing():
    src = "before\n${target:claude}\nA\n${target:end}\nafter"
    assert render_body(src, "opencode", TOKENS) == "before\n\nafter"


def test_content_lines_may_contain_colons_and_pipes():
    src = "${target:claude}\nmodel: opus | tools: Read | see satisfies:\n${target:end}"
    assert render_body(src, "claude-code", TOKENS) == "model: opus | tools: Read | see satisfies:"


def test_mid_sentence_token_is_resolved_in_place():
    assert render_body("see ${cmd.design}, then go", "claude-code", TOKENS) == "see /hercules:design, then go"


def test_code_fence_content_is_preserved():
    src = "```\n${cmd.design}\n```"
    assert render_body(src, "claude-code", TOKENS) == "```\n/hercules:design\n```"


def test_unclosed_switch_raises():
    with pytest.raises(RenderError):
        render_body("${target:claude}\nA", "claude-code", TOKENS)


def test_unknown_switch_directive_raises():
    with pytest.raises(RenderError):
        render_body("${target:claude}\nA\n${target:bogusdirective x}\n${target:end}", "claude-code", TOKENS)


def test_body_is_byte_preserving_outside_markers():
    src = "line1\n\n  indented\ttab\n${cmd.design}\ntrailing  \n"
    out = render_body(src, "claude-code", TOKENS)
    assert out == "line1\n\n  indented\ttab\n/hercules:design\ntrailing  \n"
