"""Fixtures for the review judge: a complete review of a requirements document, and the helper that
runs the tool.

The complete review is the load-bearing fixture. Every test either degrades it — skips a category,
drops a finding field, raises a severity — or moves the tier under it, so what is being tested is
always one deviation from a review that should pass.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from tests.scripts.tools.tool_harness import load_tool

main = load_tool("doc_report")

RULES = json.loads(
    (Path(__file__).resolve().parents[4] / "src" / "scripts" / "tools" / "doc_rules.json")
    .read_text(encoding="utf-8"))


def full_review(kind: str = "business-requirements", tier: str = "medium", **overrides) -> dict:
    """A review that answers every category in the rubric, all passing unless a test says otherwise."""
    rubric = RULES["review"]["rubrics"][kind]
    report = {
        "document": "2026-08-04-booking-reschedule-business-requirements.md",
        "kind": kind,
        "tier": tier,
        "reviewer": "senior-qa-engineer",
        "round": 1,
        "categories": [
            {"category": item["category"], "verdict": "pass",
             "note": "checked %s and found nothing to raise" % item["category"]}
            for item in rubric
        ],
    }
    report.update(overrides)
    return report


def with_verdict(report: dict, category: str, verdict: str, **finding) -> dict:
    """Replace one category's verdict, attaching a well-formed finding unless the test supplies one."""
    body = {"where": "§Flows", "observation": "an observation",
            "impact": "the consequence if it ships", "recommendation": "what to do instead"}
    body.update(finding)
    for entry in report["categories"]:
        if entry["category"] == category:
            entry["verdict"] = verdict
            entry.pop("note", None)
            entry["findings"] = [body]
    return report


def judge(tmp_path: Path, report: dict, lint: dict = None, round_number=None):
    """Write the review (and any lint result) and run the tool, returning ``(exit_code, payload)``."""
    path = tmp_path / "review.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    argv = ["judge", "--report", str(path)]
    if lint is not None:
        lint_path = tmp_path / "lint.json"
        lint_path.write_text(json.dumps(lint), encoding="utf-8")
        argv += ["--lint", str(lint_path)]
    if round_number is not None:
        argv += ["--round", str(round_number)]
    return run(argv)


def run(argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(list(argv))
    return code, json.loads(buffer.getvalue())


@pytest.fixture()
def review() -> dict:
    return full_review()
