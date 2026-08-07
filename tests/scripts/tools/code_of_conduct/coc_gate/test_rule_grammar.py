"""The four properties the shipped skill promises of every rule but could only ask an agent to
honour: it is tagged, it names a check, it carries a citation, and it is one rule rather than a
paragraph. Each is proven here to stop a draft rather than merely be requested."""

from __future__ import annotations

from tests.scripts.tools.code_of_conduct.coc_gate.conftest import a_rule, an_envelope, findings_of


def test_a_draft_whose_rules_all_pass_the_grammar_clears_the_gate(gate):
    code, report = gate(an_envelope())
    assert code == 0
    assert report["findings"] == []


def test_a_rule_carrying_no_normative_tag_is_refused(gate):
    code, report = gate(an_envelope(rules=[a_rule(tag=None)]))
    assert code == 1
    assert findings_of(report, "rule_untagged")


def test_a_rule_tagged_outside_the_normative_vocabulary_is_refused(gate):
    """The four tiers each mean one enforcement posture; "SHALL" carries nothing."""
    code, report = gate(an_envelope(rules=[a_rule(tag="SHALL")]))
    assert code == 1
    assert findings_of(report, "rule_untagged")


def test_every_tier_of_the_vocabulary_is_accepted(gate):
    """MUST is gated, SHOULD is convention, AVOID names a tempting path with a better one, and
    NEVER_DO is a hard stop. Each is a posture a reader maps to one behaviour."""
    for tag in ("MUST", "SHOULD", "AVOID", "NEVER_DO"):
        code, report = gate(an_envelope(rules=[a_rule(tag=tag)]))
        assert code == 0, f"{tag} was refused: {report.get('findings')}"


def test_the_retired_nice_to_have_tier_is_refused(gate):
    """The owner folded it: one rule in a hundred lines does not earn a fifth mapping, and an
    optional-and-cheap rule is a SHOULD."""
    code, report = gate(an_envelope(rules=[a_rule(tag="NICE TO HAVE")]))
    assert code == 1
    assert findings_of(report, "rule_untagged")


def test_a_rule_naming_no_mechanical_check_is_refused(gate):
    code, report = gate(an_envelope(rules=[a_rule(check="  ")]))
    assert code == 1
    assert findings_of(report, "rule_uncheckable")


def test_a_rule_with_no_citation_is_refused(gate):
    """Evidence-first is the skill's own invariant: a rule nobody can trace is a rule nobody agreed."""
    code, report = gate(an_envelope(rules=[a_rule(citations=[])]))
    assert code == 1
    assert findings_of(report, "rule_uncited")


def test_a_finding_names_the_rule_it_came_from(gate):
    """A gate that says "something failed" sends the agent back to read the whole draft."""
    code, report = gate(an_envelope(rules=[a_rule(id="security.secrets", tag=None)]))
    assert code == 1
    assert findings_of(report, "rule_untagged")[0]["rule_id"] == "security.secrets"


def test_two_rules_sharing_one_id_are_refused(gate):
    """Ids are how the update path re-verifies a rule years later; a duplicate breaks that link."""
    code, report = gate(an_envelope(rules=[a_rule(), a_rule(text="A different sentence.")]))
    assert code == 1
    assert findings_of(report, "rule_id_duplicated")


def test_a_rule_without_an_id_is_refused(gate):
    code, report = gate(an_envelope(rules=[a_rule(id="")]))
    assert code == 1
    assert findings_of(report, "rule_unidentified")


def test_a_draft_containing_no_rules_at_all_is_refused(gate):
    """An empty draft would otherwise clear every check by having nothing to fail."""
    code, report = gate(an_envelope(rules=[]))
    assert code == 1
    assert findings_of(report, "draft_empty")
