"""Unit tests for the A2A grammar module — each function is tested independently."""

import pytest

from hercules.methodology.a2a_grammar import (
    ALLOWED_STATUSES,
    count_core_entries,
    extract_a2a_core,
    extract_used_statuses,
    find_core_entry_lines,
    matches_a2a_entry_format,
)


def test_a2a_core_block_is_correctly_extracted_from_protocol_markdown():
    """The injected Core block is the first fenced code block in the protocol file.

    When a file has two fenced blocks, only the content of the first one is returned.
    """
    # Given
    md = "intro\n```\nline a\nline b\n```\ntrailer\n```\nsecond\n```\n"

    # When
    core, ok = extract_a2a_core(md)

    # Then
    assert ok is True
    assert core == "line a\nline b"


def test_a2a_core_extraction_returns_false_when_no_fenced_block_exists():
    """A protocol file with no fenced block has no A2A Core — extraction must signal this clearly."""
    # Given
    md = "just prose, no fences"

    # When
    _, ok = extract_a2a_core(md)

    # Then
    assert ok is False


def test_numbered_entries_are_counted_excluding_continuation_lines():
    """Core entry count covers only top-level numbered lines, not indented continuations."""
    # Given
    core = "0. zero\n   continuation (indented, not counted)\n1. one\n2. two\nExample: not an entry"

    # When
    count = count_core_entries(core)

    # Then
    assert count == 3


def test_entry_lines_are_returned_with_their_role_and_status():
    """find_core_entry_lines returns every [ROLE] STATUS | CONTENT | ACTION line in the text."""
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


def test_entry_matching_a2a_format_is_accepted():
    """A valid entry has exactly two ' | ' separators — three fields total."""
    # Given
    valid_entries = [
        "[QA] Blocker | something is wrong | fix it",
        "[QA] Pass | reviewed scope x | none",
        "[QA] Medium | content with a|pipe inside | fix it",  # bare pipe in CONTENT is fine
    ]

    # When / Then
    for line in valid_entries:
        assert matches_a2a_entry_format(line) is True, f"Should be valid: {line!r}"


def test_entry_missing_required_separators_is_rejected():
    """An entry with the wrong number of ' | ' separators must be rejected."""
    # Given
    invalid_entries = [
        "[QA] Blocker | only two fields",           # one separator
        "[QA] Blocker | a | b | c",                  # three separators
    ]

    # When / Then
    for line in invalid_entries:
        assert matches_a2a_entry_format(line) is False, f"Should be invalid: {line!r}"


def test_used_statuses_are_extracted_from_entry_lines():
    """extract_used_statuses returns only statuses that appear in valid entry lines.

    Lines with unknown statuses are not captured because they don't match the entry regex.
    """
    # Given
    md = "[QA] Blocker | x | y\n[ARCH] Info | z | none\n[OLD] Bogus | a | b"

    # When
    statuses = extract_used_statuses(md)

    # Then
    assert statuses == ["Blocker", "Info"]


def test_allowed_statuses_set_contains_exactly_six_values():
    """The canonical A2A status vocabulary has exactly 6 values."""
    # Given / When / Then
    assert ALLOWED_STATUSES == frozenset(
        {"Blocker", "High", "Medium", "Nitpick", "Pass", "Info"}
    )
