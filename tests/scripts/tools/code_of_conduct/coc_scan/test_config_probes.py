"""What the repository declares about itself. Measured against six real projects first: the probe set
these tests pin exists because exact filenames missed `.eslintrc.yml`, whole ecosystems had no entry
at all, and the tools a modern Python project uses are declared inside its manifest rather than beside
it.
"""

from __future__ import annotations

from tests.scripts.tools.code_of_conduct.coc_scan.conftest import fact, fact_ids


def test_a_config_file_becomes_a_fact_that_cites_it(repo, scan):
    code, doc = scan(repo)
    assert code == 0
    entry = fact(doc, "cfg.ci.github")
    assert entry["citations"][0]["path"].startswith(".github/workflows/")


def test_absent_configuration_invents_no_fact(repo, scan):
    """Evidence-first cuts both ways: a repository with no Go module must not acquire one."""
    ids = fact_ids(scan(repo)[1])
    assert "cfg.eco.go" not in ids
    assert "cfg.container.dockerfile" not in ids


def test_the_report_says_how_many_probes_were_tried_not_only_how_many_matched(repo, scan):
    """Otherwise a catalogue that has fallen behind an ecosystem is indistinguishable from a
    repository that genuinely uses none of what it knows to look for."""
    doc = scan(repo)[1]
    assert doc["probes_matched"] < doc["probes_attempted"]
