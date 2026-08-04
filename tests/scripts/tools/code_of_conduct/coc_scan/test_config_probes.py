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


def test_a_probe_matches_however_the_config_spells_its_extension(repo, scan):
    """`.eslintrc.yml` is what a real project had, and what an exact-filename list missed."""
    assert "cfg.lint.eslint" in fact_ids(scan(repo)[1])


def test_tooling_declared_inside_the_python_manifest_is_found(repo, scan):
    """Ruff, mypy, pytest and coverage commonly live in `[tool.*]` sections, so a scan that only
    looks for standalone files reports a repository with no tooling at all."""
    ids = fact_ids(scan(repo)[1])
    assert "cfg.lint.ruff" in ids
    assert "cfg.test.pytest" in ids


def test_a_manifest_fact_cites_the_line_it_was_read_from(repo, scan):
    citation = fact(scan(repo)[1], "cfg.lint.ruff")["citations"][0]
    assert citation["path"] == "pyproject.toml"
    assert citation["line"] > 0


def test_tooling_declared_only_as_a_dependency_is_found(repo, scan):
    """A project can carry a test runner with no config file of its own."""
    assert "cfg.test.vitest" in fact_ids(scan(repo)[1])


def test_the_ecosystems_present_are_named(repo, scan):
    ids = fact_ids(scan(repo)[1])
    assert {"cfg.eco.node", "cfg.eco.python"} <= ids


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


def test_a_declared_runtime_constraint_is_carried_as_a_value(repo, scan):
    assert fact(scan(repo)[1], "cfg.runtime.engines")["value"] == {"node": ">=20"}
