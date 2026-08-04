"""Which code the standards should come from. Three states rather than two, because a directory
nobody has touched in a year and one nobody has touched this quarter are different arguments — and
because a repository's dormant mass is invisible to `git log`, which only ever reports what moved.
"""

from __future__ import annotations

from tests.scripts.tools.coc_scan.conftest import (
    ALIVE_DIR, COOLING_DIR, DORMANT_DIR, GENERATED_DIR, directory)


def test_a_directory_worked_on_lately_is_alive(repo, scan):
    code, doc = scan(repo)
    assert code == 0
    assert directory(doc, ALIVE_DIR)["status"] == "alive"


def test_a_directory_touched_inside_the_year_but_not_lately_is_cooling(repo, scan):
    """The middle state is the one that carries an argument: still current, no longer the frontier."""
    assert directory(scan(repo)[1], COOLING_DIR)["status"] == "cooling"


def test_a_directory_present_but_untouched_within_the_window_is_dormant(repo, scan):
    assert directory(scan(repo)[1], DORMANT_DIR)["status"] == "dormant"


def test_dormant_code_is_reported_even_though_no_commit_in_the_window_names_it(repo, scan):
    """The whole point of measuring against the tree at HEAD: a monolith's dead mass never appears
    in a log of what changed, so a log-only scan cannot see the thing it most needs to report."""
    entry = directory(scan(repo)[1], DORMANT_DIR)
    assert entry["touches"] == 0
    assert entry["files_at_head"] == 2


def test_a_path_renamed_away_cannot_rank(repo, scan):
    """Its history is real and its file is gone; counting it ranks code that no longer exists."""
    doc = scan(repo)[1]
    paths = [d["path"] for d in doc["liveness"]["directories"]]
    top = [f["path"] for f in doc["liveness"]["top_files"]]
    assert "src/old_name.py" not in top
    assert doc["liveness"]["ghost_touches_dropped"] >= 1
    assert "src" in paths or any(p.startswith("src") for p in paths)


def test_a_generated_tree_is_tagged_rather_than_ranked_as_authored_work(repo, scan):
    """A build output can out-commit every hand-written module in the repository."""
    doc = scan(repo)[1]
    assert directory(doc, GENERATED_DIR)["generated"] is True
    assert all(not f["path"].startswith("dist/") for f in doc["liveness"]["top_files"])


def test_every_directory_carries_both_a_long_and_a_recent_share(repo, scan):
    """The conflict rule needs both numbers: which pattern dominates overall, and which lately."""
    entry = directory(scan(repo)[1], COOLING_DIR)
    assert entry["touches"] > 0
    assert entry["recent_touches"] == 0
    assert 0.0 <= entry["share"] <= 1.0


def test_the_sample_list_is_bounded_and_ordered_by_how_much_a_file_moves(repo, scan):
    """The agent reads from this list instead of walking the tree; unbounded, it is a tree walk."""
    top = scan(repo)[1]["liveness"]["top_files"]
    assert top
    assert len(top) <= 50
    assert [f["touches"] for f in top] == sorted((f["touches"] for f in top), reverse=True)
