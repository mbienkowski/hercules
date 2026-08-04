"""What the repository's own history says about how it is worked on — the conventions nobody wrote
down but everybody follows, which is exactly the kind of standard worth codifying."""

from __future__ import annotations

from tests.scripts.tools.coc_scan.conftest import fact


def test_the_commit_convention_is_classified_from_the_subjects_themselves(repo, scan):
    value = fact(scan(repo)[1], "hist.commit.convention")["value"]
    assert value["classification"] in ("conventional-commits", "mixed", "free-form")
    assert 0.0 <= value["conventional_share"] <= 1.0


def test_a_mostly_conventional_history_is_classified_as_such(repo, scan):
    """Five of the fixture's six subjects are conventional; one deliberately is not."""
    value = fact(scan(repo)[1], "hist.commit.convention")["value"]
    assert value["conventional_share"] >= 0.8
    assert value["classification"] == "conventional-commits"


def test_the_scopes_actually_used_are_reported(repo, scan):
    """A convention rule that names the repository's own scopes beats one naming a specification."""
    assert "core" in fact(scan(repo)[1], "hist.commit.convention")["value"]["scopes_seen"]


def test_the_convention_fact_cites_how_many_subjects_it_read(repo, scan):
    citation = fact(scan(repo)[1], "hist.commit.convention")["citations"][0]
    assert citation["sampled"] > 0
    assert citation["matched"] <= citation["sampled"]


def test_a_history_with_no_merges_says_so_rather_than_staying_silent(repo, scan):
    """Silence would read as "not measured"; zero is a finding about how the project integrates."""
    assert fact(scan(repo)[1], "hist.merge.shape")["value"]["merge_commits"] == 0


def test_no_author_identity_reaches_the_document(repo, scan):
    """History is full of personal data the standards never need, and the document is both fed to a
    model and persisted."""
    import json
    body = json.dumps(scan(repo)[1])
    assert "fixture@example.invalid" not in body
    assert "@" not in body or "example.invalid" not in body
