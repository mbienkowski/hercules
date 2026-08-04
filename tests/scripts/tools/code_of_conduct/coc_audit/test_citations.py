"""Referential integrity between a rule and the evidence it claims. A citation naming something the
envelope does not contain is the exact shape of a rule an agent invented and then justified, so it is
caught here rather than trusted."""

from __future__ import annotations

from tests.scripts.tools.code_of_conduct.coc_audit.conftest import a_rule, an_envelope, findings_of


def test_a_rule_citing_a_known_fact_clears_the_gate(gate):
    code, report = gate(an_envelope(rules=[a_rule(citations=["fact:cfg.test.runner"])]))
    assert code == 0
    assert report["findings"] == []


def test_a_rule_citing_a_fact_the_scan_never_produced_is_refused(gate):
    code, report = gate(an_envelope(rules=[a_rule(citations=["fact:cfg.invented.thing"])]))
    assert code == 1
    assert findings_of(report, "citation_unknown")


def test_a_rule_citing_an_answer_the_user_never_gave_is_refused(gate):
    code, report = gate(an_envelope(rules=[a_rule(citations=["answer:q99"])]))
    assert code == 1
    assert findings_of(report, "citation_unknown")


def test_a_user_answer_is_evidence_as_good_as_a_scanned_fact(gate):
    """Intent the scan cannot see is why the skill interviews at all."""
    code, report = gate(an_envelope(rules=[a_rule(citations=["answer:q3"])]))
    assert code == 0


def test_a_citation_naming_no_evidence_kind_is_refused(gate):
    """`cfg.lint.formatter` alone cannot say whether a fact or an answer was meant."""
    code, report = gate(an_envelope(rules=[a_rule(citations=["cfg.lint.formatter"])]))
    assert code == 1
    assert findings_of(report, "citation_malformed")


def test_a_citation_of_an_unrecognised_kind_is_refused(gate):
    code, report = gate(an_envelope(rules=[a_rule(citations=["vibes:it-looks-nice"])]))
    assert code == 1
    assert findings_of(report, "citation_malformed")


def test_an_unknown_citation_names_the_id_that_could_not_be_resolved(gate):
    code, report = gate(an_envelope(rules=[a_rule(citations=["fact:cfg.invented.thing"])]))
    assert "cfg.invented.thing" in findings_of(report, "citation_unknown")[0]["message"]


def test_the_report_lists_which_evidence_the_draft_left_unused(gate):
    """Unused evidence is where the next question comes from — it is reported, never a failure."""
    code, report = gate(an_envelope(rules=[a_rule(citations=["fact:cfg.lint.formatter"])]))
    assert code == 0
    assert "cfg.test.runner" in report["unused_evidence"]
