"""Unit tests for the A2A grammar module — each function is tested independently."""

import pytest

from tests.metrics.a2a_grammar import (
    count_core_entries,
    extract_a2a_core,
    extract_used_statuses,
    find_core_entry_lines,
    matches_a2a_entry_format,
)


def test_only_the_first_core_section_is_extracted_when_multiple_exist():
    """The Core section of the A2A protocol document is the first fenced block in the file.

    When the document contains additional fenced blocks after it, they are ignored and only
    the first section's content is returned.
    """
    # Given
    md = "intro\n```\nline a\nline b\n```\ntrailer\n```\nsecond\n```\n"

    # When
    core, ok = extract_a2a_core(md)

    # Then
    assert ok is True
    assert core == "line a\nline b"


def test_a_protocol_document_missing_its_core_section_is_clearly_flagged():
    """When the protocol document doesn't contain a Core section at all, extraction must report
    failure and return an empty result rather than silently succeeding with nothing -- so
    callers can tell "no data" apart from "missing data"."""
    # Given
    md = "just prose, no fences"

    # When
    core, ok = extract_a2a_core(md)

    # Then
    assert ok is False
    assert core == "", "no fenced block must return an empty core string"


def test_only_top_level_numbered_entries_are_counted_not_their_continuation_lines():
    """Counting entries in the Core section only counts the numbered lines themselves;
    indented continuation text that wraps under an entry, and lines like "Example:", are
    not counted as separate entries."""
    # Given
    core = "0. zero\n   continuation (indented, not counted)\n1. one\n2. two\nExample: not an entry"

    # When
    count = count_core_entries(core)

    # Then
    assert count == 3


def test_every_role_status_content_action_line_is_found_and_other_text_is_ignored():
    """Scanning the Core section text picks out every line formatted as
    [ROLE] STATUS | CONTENT | ACTION, in order, while ordinary prose lines mixed in
    between them are skipped."""
    # Given
    text = (
        "[QA] Blocker | something is broken | fix it\n"
        "prose line (ignored)\n"
        "[ARCH] Pass | reviewed | none\n"
    )

    # When
    lines = find_core_entry_lines(text)

    # Then
    assert len(lines) == 2
    assert lines[0].startswith("[QA] Blocker")
    assert lines[1].startswith("[ARCH] Pass")


def test_a_valid_entry_line_is_recognized_even_with_a_pipe_inside_its_content():
    """An entry line is recognized as valid when it has exactly the three fields separated
    by ' | ' -- role/status, content, and action. A stray '|' character inside the content
    field alone does not stop it from being recognized."""
    # Given
    valid_entries = [
        "[QA] Blocker | something is wrong | fix it",
        "[QA] Pass | reviewed scope x | none",
        "[QA] Medium | content with a|pipe inside | fix it",  # bare pipe in CONTENT is fine
    ]

    # When / Then
    for line in valid_entries:
        assert matches_a2a_entry_format(line) is True, f"Should be valid: {line!r}"


def test_an_entry_with_the_wrong_number_of_fields_is_rejected():
    """An entry line is rejected as invalid when it doesn't have exactly three fields
    separated by ' | ' -- whether it's missing a field or has an extra one -- so a
    malformed entry can't slip through and be treated as real data."""
    # Given
    invalid_entries = [
        "[QA] Blocker | only two fields",           # one separator
        "[QA] Blocker | a | b | c",                  # three separators
    ]

    # When / Then
    for line in invalid_entries:
        assert matches_a2a_entry_format(line) is False, f"Should be invalid: {line!r}"


def test_only_statuses_from_correctly_formatted_entries_are_collected():
    """Collecting the set of statuses actually used in the document only picks up statuses
    from lines that are properly formatted as entries; a status-like word sitting in a
    malformed or unrecognized line is not counted, since it isn't a real entry.
    """
    # Given
    md = "[QA] Blocker | x | y\n[ARCH] Info | z | none\n[OLD] Bogus | a | b"

    # When
    statuses = extract_used_statuses(md)

    # Then
    assert statuses == ["Blocker", "Info"]
