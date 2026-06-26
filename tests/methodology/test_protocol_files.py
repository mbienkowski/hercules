"""Tests that verify the A2A and debate protocol files follow the methodology."""

import pytest

from hercules.methodology.a2a_grammar import (
    ALLOWED_STATUSES,
    extract_a2a_core,
    extract_used_statuses,
    find_core_entry_lines,
    matches_a2a_entry_format,
)
from hercules.methodology.markdown_metrics import count_status_table_rows


_A2A_PROTOCOL = "plugin/protocols/a2a-communication-protocol.md"
_DEBATE_PROTOCOL = "plugin/protocols/debate-consensus-protocol.md"
_ALL_PROTOCOLS = [_A2A_PROTOCOL, _DEBATE_PROTOCOL]


def test_a2a_protocol_entries_each_have_three_fields(read_file):
    """Every [ROLE] STATUS | CONTENT | ACTION line in the protocol must have exactly three fields.

    This protects against accidental edits that break the A2A parser on the agent side.
    """
    # Given
    md = read_file(_A2A_PROTOCOL)

    # When
    entry_lines = find_core_entry_lines(md)

    # Then
    violations = [ln for ln in entry_lines if not matches_a2a_entry_format(ln)]
    assert not violations, f"Entry lines with wrong field count: {violations}"


def test_only_approved_status_words_appear_in_the_protocol(read_file):
    """No undefined STATUS value should appear in any protocol file entry.

    Unknown statuses would be silently ignored by agents that enforce the contract.
    """
    # Given / When / Then
    for rel in _ALL_PROTOCOLS:
        md = read_file(rel)
        violations = [s for s in extract_used_statuses(md) if s not in ALLOWED_STATUSES]
        assert not violations, f"{rel}: undefined statuses found: {violations}"


def test_status_table_has_a_row_for_each_approved_status(read_file):
    """The STATUS reference table in the A2A protocol must list all 6 approved statuses."""
    # Given
    md = read_file(_A2A_PROTOCOL)

    # When
    row_count = count_status_table_rows(md)

    # Then
    assert row_count == 6, (
        f"STATUS reference table has {row_count} rows, expected 6 "
        "(must match the 6-status set: Blocker/High/Medium/Nitpick/Pass/Info)"
    )


def test_debate_protocol_references_all_required_elements(read_file):
    """The debate protocol must reference the A2A protocol and define the round limit."""
    # Given
    md = read_file(_DEBATE_PROTOCOL)
    lower = md.lower()

    # When / Then
    assert "a2a-communication-protocol.md" in md, (
        "debate protocol must reference a2a-communication-protocol.md"
    )
    assert "maximum 3 rounds" in lower, (
        "debate protocol must state 'Maximum 3 rounds' (canonical hard-limit phrase)"
    )
    for level in ["complexity:trivial", "complexity:low", "complexity:medium",
                  "complexity:high", "complexity:critical"]:
        assert level in md, f"debate protocol must define {level}"
    assert "fresh-eyes" in lower, "debate protocol must include the fresh-eyes panel rule"


def test_injected_agent_core_has_not_been_accidentally_changed(repo_root):
    """The A2A Core block must match the blessed golden snapshot exactly.

    If you intentionally changed the Core, update tests/testdata/core.golden with:
      python -c "from hercules.methodology.a2a_grammar import extract_a2a_core; ..."
    """
    # Given
    md = (repo_root / _A2A_PROTOCOL).read_text()
    golden_path = repo_root / "tests" / "testdata" / "core.golden"

    # When
    core, ok = extract_a2a_core(md)

    # Then
    assert ok, "No fenced Core block found in the A2A protocol"
    want = golden_path.read_text()
    assert core == want, (
        "Injected Core changed vs golden. If intentional, update tests/testdata/core.golden."
    )
