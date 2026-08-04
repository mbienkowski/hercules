"""Proves every rule in the catalogue detects a real violation, and that the clean fixtures trip none
of them.

This is the guard the whole linter rests on. A detector that quietly matches nothing reports success
forever, so each catalogued rule owns a document that violates it — and the roster is DERIVED from
`doc_rules.json` rather than listed here, so a rule added without a fixture fails instead of shipping
undefended, and a rule deleted takes its fixture with it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.scripts.tools.doc_lint.conftest import (
    CLEAN_REQUIREMENTS, CLEAN_SPEC, REQUIREMENTS_NAME, SPEC_NAME, fired, lint, pad_words,
)

RULES = json.loads(
    (Path(__file__).resolve().parents[4] / "src" / "scripts" / "tools" / "doc_rules.json")
    .read_text(encoding="utf-8"))

# rule id -> (document text, filename, tier). Each entry violates exactly the rule it is keyed by,
# and may trip others; the assertion only demands that its own rule is among the findings.
VIOLATIONS = {
    "DOC101": (CLEAN_REQUIREMENTS.replace(
        "## Constraints\n"
        "- Salon opening hours bound every offered slot, and no slot outside them is ever offered.\n"
        "- The existing message service delivers every notice, and this work adds no new channel.\n"
        "- A change made by one person is visible to the other within 60 seconds.\n", ""),
        REQUIREMENTS_NAME, "medium"),
    "DOC102": (CLEAN_REQUIREMENTS.replace("## Goal", "## ZZZ", 1)
               .replace("## Users", "## Goal", 1).replace("## ZZZ", "## Users", 1),
               REQUIREMENTS_NAME, "medium"),
    "DOC103": (CLEAN_REQUIREMENTS.replace("- **Change wanted**", "- **Change wanted** TBD", 1),
               REQUIREMENTS_NAME, "medium"),
    "DOC104": (CLEAN_REQUIREMENTS.replace(
        "- **Customer** — today rings the salon during opening hours and waits on hold.\n"
        "- **Stylist** — today writes the change on paper and re-enters it later that day.\n", ""),
        REQUIREMENTS_NAME, "medium"),
    "DOC106": (CLEAN_REQUIREMENTS + "\n## Invented Section\n- a bullet with the number 4 in it.\n",
               REQUIREMENTS_NAME, "medium"),
    "DOC204": (CLEAN_REQUIREMENTS.replace(
        "- **Change wanted** — a customer moves an appointment without speaking to anyone.",
        "- **Change wanted** — the `BookingCalendar` record moves for 2 people.", 1),
        REQUIREMENTS_NAME, "medium"),
    "DOC206": (CLEAN_REQUIREMENTS.replace(
        "## Constraints\n",
        "## Constraints\n- The 2 hour rule must be implemented before the launch day.\n", 1),
        REQUIREMENTS_NAME, "medium"),
    "DOC207": (CLEAN_REQUIREMENTS
               + "\n## Technical suggestions (non-binding)\n"
                 "- The nightly job owns the 2 hour cut-off and nothing else does.\n",
               REQUIREMENTS_NAME, "medium"),
    "DOC301": (CLEAN_REQUIREMENTS.replace(
        "- N3 | Stylist picks a slot another customer already holds → refused, and the clash is named.\n",
        ""), REQUIREMENTS_NAME, "medium"),
    "DOC302": (CLEAN_REQUIREMENTS.replace(
        "- N3 | Stylist picks a slot another customer already holds → refused, and the clash is named.",
        "- N3 stylist picks a slot another customer already holds and it is refused.", 1),
        REQUIREMENTS_NAME, "medium"),
    "DOC303": (CLEAN_REQUIREMENTS.replace(
        "- N2 | Under 2 hours before the start → refused, and the cancellation policy is shown.\n", "")
        .replace(
        "- N3 | Stylist picks a slot another customer already holds → refused, and the clash is named.",
        "- M3 | Stylist confirms a free slot → the appointment moves and the customer is told.", 1)
        .replace("- N1 | Slot taken while the customer was deciding → refused, and the next 3 free slots are offered.",
                 "- M4 | Slot free tomorrow → the appointment moves and the customer is told.", 1),
        REQUIREMENTS_NAME, "medium"),
    "DOC304": (CLEAN_REQUIREMENTS.replace(
        "- M2 | Stylist picks a later free slot → appointment moves and the customer sees who changed it.",
        "- M1 | Stylist picks a later free slot → appointment moves and the customer sees it.", 1),
        REQUIREMENTS_NAME, "medium"),
    "DOC305": (CLEAN_REQUIREMENTS, REQUIREMENTS_NAME, "trivial"),
    "DOC401": (CLEAN_REQUIREMENTS, "notes-business-requirements.md", "medium"),
    "DOC402": (CLEAN_SPEC.replace(
        "| Two winners for one slot | Daily clash count above 0 | One claim per slot and time | backend |",
        "| Two winners for one slot | Daily clash count above 0 |  | backend |", 1),
        SPEC_NAME, "medium"),
    "DOC601": (CLEAN_REQUIREMENTS, REQUIREMENTS_NAME, "critical"),
    "DOC602": (pad_words(CLEAN_REQUIREMENTS, 60), REQUIREMENTS_NAME, "medium"),
    "DOC701": (CLEAN_SPEC.replace("§Flows]", "§Flows That Do Not Exist]", 1), SPEC_NAME, "medium"),
}


def test_there_are_rules_to_defend():
    """An empty catalogue would make every parametrised case below vacuous."""
    assert len(RULES["rules"]) > 12


def test_almost_nothing_blocks():
    """The posture, pinned. The standard advises and a person decides; a checker that refuses
    legitimate documents teaches people to write for the checker instead of for the reader. Only an
    unresolvable reference is not a matter of taste."""
    blocking = [rule["id"] for rule in RULES["rules"] if rule["severity"] == "block"]
    assert blocking == ["DOC701"], blocking
    assert {rule["severity"] for rule in RULES["rules"]} <= {"block", "advice"}


def test_the_judgement_half_is_taught_rather_than_gated():
    """Naming, ambiguity and hollowness are real concerns and deliberately not rules: they are
    guidance in the same file, so the skill can be written from it without the linter refusing
    anyone over them."""
    topics = [entry["topic"] for group in RULES["guidance"].values()
              if isinstance(group, list) for entry in group]
    assert len(topics) >= 8
    for group in RULES["guidance"].values():
        if not isinstance(group, list):
            continue
        for entry in group:
            assert entry["do"] and entry["dont"] and entry["why"], entry


def test_every_catalogued_rule_owns_a_violation():
    """A rule with no fixture is a detector nothing proves can fire — the exact failure this file
    exists to prevent. The roster is derived, so this fails the moment a rule is added without one."""
    catalogued = {rule["id"] for rule in RULES["rules"]}
    assert catalogued == set(VIOLATIONS), (
        "these rules have no document that violates them: %s; these fixtures name no rule: %s"
        % (sorted(catalogued - set(VIOLATIONS)), sorted(set(VIOLATIONS) - catalogued)))


@pytest.mark.parametrize("rule_id", sorted(VIOLATIONS))
def test_the_rule_fires_on_a_real_violation(tmp_path, rule_id):
    """Each rule detects the document written to break it."""
    text, name, tier = VIOLATIONS[rule_id]
    # Named explicitly rather than inferred: the filename rule's own fixture carries a name the
    # inference cannot resolve, which is the point of that rule.
    kind = "spec" if name == SPEC_NAME else "business-requirements"
    _, payload = lint(tmp_path, text, name, kind=kind, tier=tier)
    assert rule_id in fired(payload), (
        "%s did not fire; findings were %s" % (rule_id, sorted(fired(payload))))


def test_a_compliant_requirements_document_trips_nothing(tmp_path):
    """The corpus test: a document written to the standard must pass it. A rule that fires here is
    too broad, and the rule is what changes — not the document."""
    code, payload = lint(tmp_path, CLEAN_REQUIREMENTS, REQUIREMENTS_NAME, tier="medium", strict=True)
    assert payload["findings"] == [], payload["findings"]
    assert payload["clean"] is True
    assert code == 0


def test_a_compliant_spec_trips_nothing(tmp_path):
    """The same obligation on the other document kind."""
    code, payload = lint(tmp_path, CLEAN_SPEC, SPEC_NAME, tier="medium", strict=True)
    assert payload["findings"] == [], payload["findings"]
    assert payload["clean"] is True
    assert code == 0
