"""The third evidence stream: what the drafting agent saw in the code with its own eyes. A scan fact
covers what a program can measure and an answer covers what only the user knows — but the rules worth
having name the architecture, and those are read, not measured. An observation makes that reading
citable and checkable instead of something smuggled through as an invented fact: the gate holds its
shape here, and the linter holds its path against the repository's file list."""

from __future__ import annotations

from tests.scripts.tools.code_of_conduct.coc_audit.conftest import (
    a_rule, an_envelope, findings_of)


def test_a_rule_citing_a_recorded_observation_clears_the_gate(gate):
    """Reading the code is evidence as good as scanning it — once the reading names its file."""
    code, report = gate(an_envelope(rules=[a_rule(citations=["code:obs.engine-strictness"])]))
    assert code == 0
    assert report["findings"] == []


def test_a_rule_citing_an_observation_nobody_recorded_is_refused(gate):
    """An observation id nothing produced is the same invented-evidence shape as a phantom fact."""
    code, report = gate(an_envelope(rules=[a_rule(citations=["code:obs.never-seen"])]))
    assert code == 1
    assert findings_of(report, "citation_unknown")


def test_an_observation_carrying_no_path_is_refused(gate):
    """An observation with no file behind it is an opinion wearing an id."""
    code, report = gate(an_envelope(observations=[{"id": "obs.pathless"}]))
    assert code == 1
    assert findings_of(report, "observation_pathless")


def test_an_observation_whose_path_leaves_the_repository_is_refused(gate):
    """The gate is pure and cannot resolve a path, but it can see one that points outside — and
    nothing outside the repository is evidence about it."""
    for path in ("/etc/passwd", "../sibling/module.py", "a/../../escape.py"):
        code, report = gate(an_envelope(
            observations=[{"id": "obs.escaping", "path": path}]))
        assert code == 1
        assert findings_of(report, "observation_path_escapes")


def test_an_observation_entry_without_an_id_offers_nothing(gate):
    """The entry is passed over rather than refused; the rule citing it fails, naming the defect."""
    code, report = gate(an_envelope(
        observations=[{"path": "src/module.py"}],
        rules=[a_rule(citations=["code:obs.engine-strictness"])]))
    assert code == 1
    assert findings_of(report, "citation_unknown")


def test_an_unused_observation_is_reported_with_the_unused_evidence(gate):
    """Unused evidence is where the next question comes from, whichever stream it arrived by."""
    code, report = gate(an_envelope(rules=[a_rule(citations=["fact:cfg.lint.formatter"])]))
    assert code == 0
    assert "obs.engine-strictness" in report["unused_evidence"]


def test_observations_that_are_not_a_list_are_refused(gate):
    code, report = gate(an_envelope(observations="what I noticed"))
    assert code == 4
