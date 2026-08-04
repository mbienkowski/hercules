"""What the budget counts, and how hard it pushes back. The bands are advisory on purpose — a hard
gate at 40 would be answered by merging two rules into one longer bullet, which buys a number and
costs a reader. Only the ceiling refuses."""

from __future__ import annotations

from tests.scripts.tools.coc_audit.conftest import a_rule, an_envelope, rules_numbering


def test_the_report_counts_one_directive_per_rule(gate):
    code, report = gate(an_envelope(rules=rules_numbering(12)))
    assert report["directives"] == 12


def test_a_draft_inside_the_intended_band_is_reported_as_such(gate):
    code, report = gate(an_envelope(rules=rules_numbering(35)))
    assert code == 0
    assert report["band"] == "intended"


def test_a_draft_past_the_intended_band_still_ships_but_says_what_it_costs(gate):
    """Coverage bought with adherence is a trade the user is told about, not one refused for them."""
    code, report = gate(an_envelope(rules=rules_numbering(55)))
    assert code == 0
    assert report["band"] == "over"
    assert report["message"]


def test_a_draft_past_the_hard_ceiling_is_refused(gate):
    code, report = gate(an_envelope(rules=rules_numbering(71)))
    assert code == 1
    assert report["band"] == "ceiling"


def test_the_explanations_attached_to_a_rule_are_not_themselves_directives(gate):
    """A WHY line and a DO/DON'T pair teach the rule already counted; counting them again would
    price the file's most useful lines out of the budget."""
    annotated = rules_numbering(
        10, why="Formatting arguments cost more review time than the formatter costs to run.",
        dont="`if(x){return}`", do="`if (x) {\n    return\n}`")
    code, report = gate(an_envelope(rules=annotated))
    assert report["directives"] == 10


def test_the_bands_are_reported_so_a_caller_never_hardcodes_them(gate):
    code, report = gate(an_envelope(rules=rules_numbering(5)))
    assert report["bands"] == {"intended": 40, "large": 50, "ceiling": 70}
