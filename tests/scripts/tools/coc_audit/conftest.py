"""The envelope a drafting agent submits, and the one call that runs the gate over it. Built here
rather than inline so a test names only the field it bends — every other field stays valid, which is
what makes a single-field failure attributable."""

from __future__ import annotations

import io
import json

import pytest

from tests.scripts.tools.tool_harness import invoke, load_tool

CONTRACT = 1

FACT_IDS = ("cfg.lint.formatter", "cfg.test.runner", "hist.commit.convention")
ANSWER_IDS = ("q1", "q3")


def a_rule(**overrides) -> dict:
    """One valid rule: tagged, checked, cited. Overrides bend exactly one field at a time."""
    rule = {
        "id": "style.formatter",
        "section": "Development",
        "tag": "MUST",
        "text": "Format every file with the repository formatter before committing.",
        "check": "CI runs the formatter in check mode",
        "citations": ["fact:cfg.lint.formatter"],
    }
    rule.update(overrides)
    return rule


def an_envelope(rules=None, facts=None, answers=None, **overrides) -> dict:
    envelope = {
        "contract": CONTRACT,
        "facts": [{"id": fid} for fid in (FACT_IDS if facts is None else facts)],
        "answers": [{"id": aid} for aid in (ANSWER_IDS if answers is None else answers)],
        "rules": [a_rule()] if rules is None else list(rules),
    }
    envelope.update(overrides)
    return envelope


def rules_numbering(count: int, **overrides) -> list:
    """`count` distinct valid rules — the shape every budget-band test needs."""
    return [a_rule(id=f"rule.{index:03d}", **overrides) for index in range(count)]


@pytest.fixture
def gate():
    """Run the draft gate over an envelope, returning `(exit_code, report)`."""
    main = load_tool("coc_audit")

    def run(envelope, argv=None, raw=None):
        text = raw if raw is not None else json.dumps(envelope)
        return invoke(main, None, argv or ["draft", "--contract", str(CONTRACT)],
                      stdin=io.StringIO(text))

    return run


def findings_of(report: dict, rule_name: str) -> list:
    return [f for f in report.get("findings", []) if f.get("rule") == rule_name]
