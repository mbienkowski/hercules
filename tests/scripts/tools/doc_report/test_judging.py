"""Proves the judge does the two things it exists for, and none of the things it must not.

It exists to (a) refuse a review that skipped a question, because an unanswered category is how a
review passes something nobody looked at, and (b) turn severities into the same decision every time
so "needs work" is a threshold rather than a mood.

It must NOT form an opinion about the document. Every quality judgement here arrives in the report;
the tool that reads it can only count, and this file pins that boundary.
"""

from __future__ import annotations

import pytest

from tests.scripts.tools.doc_report.conftest import (
    RULES, full_review, judge, run, with_verdict,
)

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_NOT_FOUND = 4


def test_there_is_a_rubric_to_answer():
    """An empty rubric would make completeness vacuous — every review would be complete."""
    for kind, rubric in RULES["review"]["rubrics"].items():
        assert len(rubric) >= 5, kind
        assert all(item["asks"].endswith("?") for item in rubric), kind


def test_a_complete_review_proceeds(tmp_path, review):
    code, payload = judge(tmp_path, review)
    assert code == EXIT_OK
    assert payload["decision"] == "proceed"
    assert payload["counts"]["pass"] == len(RULES["review"]["rubrics"]["business-requirements"])


@pytest.mark.parametrize("category", [item["category"]
                                      for item in RULES["review"]["rubrics"]["business-requirements"]])
def test_skipping_any_category_is_refused(tmp_path, category):
    """Silence on a category is never a pass — the same rule the A2A protocol puts on a Pass status.
    Parametrised over the real rubric so a category added later is defended without a new test."""
    review = full_review()
    review["categories"] = [entry for entry in review["categories"]
                            if entry["category"] != category]
    code, payload = judge(tmp_path, review)
    assert code == EXIT_REFUSED
    assert any(category in problem and "never a pass" in problem
               for problem in payload["detail"]), payload["detail"]


def test_a_bare_pass_is_refused(tmp_path, review):
    """A pass that names nothing it checked is a rubber stamp, and reads identically to real work."""
    review["categories"][0].pop("note")
    code, payload = judge(tmp_path, review)
    assert code == EXIT_REFUSED
    assert any("must name what was checked" in problem for problem in payload["detail"])


def test_a_non_pass_without_a_finding_is_refused(tmp_path, review):
    """Saying 'major' and nothing else tells an author their document is wrong but not how."""
    for entry in review["categories"]:
        if entry["category"] == "flow-coverage":
            entry["verdict"] = "major"
            entry.pop("note")
    code, payload = judge(tmp_path, review)
    assert code == EXIT_REFUSED
    assert any("no finding" in problem for problem in payload["detail"])


@pytest.mark.parametrize("missing", ["where", "observation", "impact", "recommendation"])
def test_a_finding_missing_any_field_is_refused(tmp_path, missing):
    """A finding without a recommendation is a complaint; without an impact it cannot be ranked."""
    review = with_verdict(full_review(), "flow-coverage", "major", **{missing: "  "})
    code, payload = judge(tmp_path, review)
    assert code == EXIT_REFUSED
    assert any(missing in problem for problem in payload["detail"])


def test_an_invented_category_is_refused(tmp_path, review):
    """A reviewer answering a question nobody asked has drifted from the rubric everyone agreed on."""
    review["categories"].append({"category": "vibes", "verdict": "pass", "note": "felt fine"})
    code, payload = judge(tmp_path, review)
    assert code == EXIT_REFUSED
    assert any("not a category" in problem for problem in payload["detail"])


# ── the decision ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tier,expected", [
    ("trivial", "proceed"), ("low", "proceed"), ("medium", "proceed"),
    ("high", "proceed"), ("critical", "revise"),
])
def test_one_major_is_tolerated_by_tier(tmp_path, tier, expected):
    """Depth scaling, made concrete: the identical review is fine at low and sends the draft back at
    critical, because that is where an unfixed gap is least recoverable."""
    review = with_verdict(full_review(tier=tier), "flow-coverage", "major")
    _, payload = judge(tmp_path, review)
    assert payload["decision"] == expected, payload["reasons"]


def test_a_blocker_sends_it_back_at_every_tier(tmp_path):
    for tier in RULES["tiers"]:
        review = with_verdict(full_review(tier=tier), "flow-coverage", "blocker")
        _, payload = judge(tmp_path, review)
        assert payload["decision"] in ("revise", "escalate"), (tier, payload)


def test_minors_and_nits_never_send_it_back(tmp_path):
    """Otherwise the standard becomes a compliance exercise and people stop reading the findings."""
    review = with_verdict(full_review(), "measurability", "minor")
    review = with_verdict(review, "scope-boundaries", "nit")
    code, payload = judge(tmp_path, review)
    assert payload["decision"] == "proceed"
    assert code == EXIT_OK
    assert len(payload["worklist"]) == 2


def test_the_loop_stops_and_a_person_decides(tmp_path):
    """A review that keeps returning revise would loop forever; the round cap hands it to a human,
    the same shape as the build phase's three-round limit."""
    review = with_verdict(full_review(tier="critical"), "flow-coverage", "major")
    max_rounds = RULES["review"]["policy"]["max_rounds"]
    _, payload = judge(tmp_path, review, round_number=max_rounds)
    assert payload["decision"] == "escalate"
    assert any("person decides" in reason for reason in payload["reasons"])


def test_the_worklist_is_ordered_worst_first(tmp_path):
    """The output an author acts on: an ordered list of work, not an impression."""
    review = with_verdict(full_review(), "measurability", "nit")
    review = with_verdict(review, "flow-coverage", "blocker")
    review = with_verdict(review, "risk-realism", "minor")
    _, payload = judge(tmp_path, review)
    assert [item["severity"] for item in payload["worklist"]] == ["blocker", "minor", "nit"]
    assert all(item["do"] and item["because"] for item in payload["worklist"])


# ── folding in the mechanical half ──────────────────────────────────────────────────────────────


def test_a_lint_block_enters_as_a_blocker(tmp_path, review):
    """The one thing doc_lint blocks on — an unresolvable reference — has to survive the merge."""
    lint = {"path": "spec.md", "findings": [
        {"rule": "DOC701", "severity": "block", "line": 2, "section": "",
         "title": "reference does not resolve", "message": "no section 'Nowhere'",
         "fix": "point it at a section that exists"}]}
    code, payload = judge(tmp_path, review, lint=lint)
    assert payload["decision"] == "revise"
    assert payload["worklist"][0]["severity"] == "blocker"
    assert code == EXIT_REFUSED


def test_lint_advice_never_outranks_a_human_reviewer(tmp_path, review):
    """The linter is advisory by design, so folding it in must not let a regex send a draft back
    that a reviewer was content with."""
    lint = {"path": "doc.md", "findings": [
        {"rule": "DOC401", "severity": "advice", "line": 0, "section": "",
         "title": "filename", "message": "off pattern", "fix": "rename it"}] * 5}
    code, payload = judge(tmp_path, review, lint=lint)
    assert payload["decision"] == "proceed"
    assert code == EXIT_OK
    assert all(item["severity"] == "minor" for item in payload["worklist"])


# ── shape and refusals ──────────────────────────────────────────────────────────────────────────


def test_a_missing_report_is_not_found(tmp_path):
    code, payload = run(["judge", "--report", str(tmp_path / "absent.json")])
    assert code == EXIT_NOT_FOUND
    assert payload["error"] == "refused"


def test_an_unknown_tier_names_the_options(tmp_path):
    code, payload = judge(tmp_path, full_review(tier="enormous"))
    assert code == EXIT_REFUSED
    assert "medium" in payload["message"]


def test_the_template_matches_the_rubric_it_will_be_judged_against():
    """The reviewer fills in what the checker will read — emitted from one place so the two cannot
    disagree about what a complete review looks like."""
    for kind, rubric in RULES["review"]["rubrics"].items():
        _, payload = run(["template", "--kind", kind])
        offered = [entry["category"] for entry in payload["report_template"]["categories"]]
        assert offered == [item["category"] for item in rubric]


def test_the_rubric_mode_publishes_the_policy():
    """The thresholds are stated in advance, so a decision is never a surprise."""
    code, payload = run(["rubric"])
    assert code == EXIT_OK
    assert set(payload["policy"]["tiers"]) == set(RULES["tiers"])
    assert payload["severity_meaning"]["blocker"]
