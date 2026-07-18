"""Tests that verify the A2A and debate protocol files follow the methodology."""

import pytest

from tests.metrics.a2a_grammar import (
    ALLOWED_STATUSES,
    extract_a2a_core,
    extract_used_statuses,
    find_core_entry_lines,
    matches_a2a_entry_format,
)
from tests.metrics.markdown_metrics import count_status_table_rows


_A2A_PROTOCOL = "dist/claude-code/protocols/a2a-communication-protocol.md"
_DEBATE_PROTOCOL = "dist/claude-code/protocols/debate-consensus-protocol.md"
_ALL_PROTOCOLS = [_A2A_PROTOCOL, _DEBATE_PROTOCOL]


def test_a2a_protocol_entries_each_have_three_fields(read_file):
    """Every status/content/action entry line in the A2A protocol document must supply exactly
    three fields, matching the documented [ROLE] STATUS | CONTENT | ACTION format. A line with
    the wrong field count would silently break how agents read each other's messages."""
    # Given
    md = read_file(_A2A_PROTOCOL)

    # When
    entry_lines = find_core_entry_lines(md)

    # Then
    violations = [ln for ln in entry_lines if not matches_a2a_entry_format(ln)]
    assert not violations, f"Entry lines with wrong field count: {violations}"


def test_only_approved_status_words_appear_in_the_protocol(read_file):
    """Every status word used in the A2A and debate protocol documents must come from the
    approved set. An unrecognized status would be silently ignored by any agent enforcing the
    contract, letting a misspelled or made-up status slip through unnoticed."""
    # Given / When / Then
    for rel in _ALL_PROTOCOLS:
        md = read_file(rel)
        violations = [s for s in extract_used_statuses(md) if s not in ALLOWED_STATUSES]
        assert not violations, f"{rel}: undefined statuses found: {violations}"


def test_status_table_has_a_row_for_each_approved_status(read_file):
    """The status reference table in the A2A protocol document must list all six approved
    statuses (Blocker, High, Medium, Nitpick, Pass, Info). A missing row would leave that
    status undocumented for anyone reading the protocol."""
    # Given
    md = read_file(_A2A_PROTOCOL)

    # When
    row_count = count_status_table_rows(md)

    # Then
    assert row_count == 6, (
        f"STATUS reference table has {row_count} rows, expected 6 "
        "(must match the 6-status set: Blocker/High/Medium/Nitpick/Pass/Info)"
    )


def test_shared_agent_instructions_block_matches_the_approved_reference_copy(repo_root):
    """The block of instructions injected into every agent's prompt from the A2A protocol
    document must exactly match the previously approved reference copy stored in
    tests/testdata/core.golden. Any unnoticed drift here changes what every agent is told to
    do without anyone having reviewed the change; if the change is intentional, update
    tests/testdata/core.golden to match."""
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


def test_round3_reinvoke_threshold_excludes_resolved_votes(read_file):
    """Only ≤3/5 votes re-trigger a round: a 4/5 is now a reservation carried to the user (not
    resolved) but is still not re-invoked, and a 5/5 is resolved — so re-spawning anyone above
    ≤3/5 wastes a round. The threshold must read ≤3/5, never ≤4/5."""
    for rel in (_A2A_PROTOCOL, _DEBATE_PROTOCOL):
        assert "≤4/5" not in read_file(rel), \
            f"{rel}: R3 re-invoke threshold must stay ≤3/5 — a 4/5 reservation escalates, it is not re-debated"


def test_debate_resolves_only_at_full_consensus_else_escalates(read_file):
    """Strict end-state: a debate resolves ONLY at unanimous 5/5. A 4/5 reservation or residual
    ≤3/5 dissent that survives the tier's round cap is not resolved — it is put to the user as a
    decision (accept as-is / another angle / override), never auto-applied."""
    # Given the debate protocol
    md = read_file(_DEBATE_PROTOCOL)
    lower = md.lower()
    # Then only 5/5 resolves; 4/5 is a reservation carried to the user, not 'Resolved'
    assert "| 5 | full agreement | resolved" in lower, "5/5 must remain the resolved row"
    assert "reservation — carried to the user's decision, not resolved" in lower, \
        "4/5 must be a reservation escalated to the user, not auto-resolved"
    # And the close rule is full-consensus-or-cap, not ≥4/5
    assert "closes at full 5/5" in lower, "a round must close at full 5/5 (or the tier cap), not ≥4/5"
    # And Synthesis escalates the residue as an explicit user decision, never auto-applying
    assert "resolves only at full 5/5" in lower, "Synthesis must state the 5/5-only resolve rule"
    assert "accept as-is" in lower and "another angle" in lower and "override" in lower, \
        "the user's decision must offer accept-as-is / another-angle / override"
    assert "never auto-applied" in lower, "a contested or reserved finding is never auto-applied"
