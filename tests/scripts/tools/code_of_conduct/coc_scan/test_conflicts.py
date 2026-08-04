"""Where a repository does one thing two ways. The scan reports both sides with their standing and
picks neither — recency is a good argument and a bad decision procedure, because code is edited when
it is being adopted and equally when it is being torn out, and nothing here can tell those apart.
A rule the whole repository will be held to is worth one question.
"""

from __future__ import annotations

import json



def conflict_of(document: dict, conflict_id: str) -> dict:
    return next(c for c in document["conflicts"] if c["id"] == conflict_id)


def side(entry: dict, name: str) -> dict:
    return next(c for c in entry["candidates"] if c["name"] == name)


def test_one_way_of_doing_something_is_a_convention_not_a_conflict(consistent_repo, scan):
    """Every test in this repository is written the same way. Reporting a lone convention as a split
    would put a question in front of the user for each thing the repository is consistent about."""
    code, document = scan(consistent_repo)
    assert code == 0
    assert document["conflicts"] == []


def test_two_live_conventions_for_one_concern_are_reported(split_repo, scan):
    code, document = scan(split_repo)
    assert code == 0
    assert conflict_of(document, "conflict.test.style.python")


def test_each_side_carries_how_much_of_the_code_it_holds(split_repo, scan):
    entry = conflict_of(scan(split_repo)[1], "conflict.test.style.python")
    assert side(entry, "unittest-class")["files"] == 6
    assert side(entry, "pytest-function")["files"] == 2


def test_each_side_carries_how_much_of_the_recent_work_it_sees(split_repo, scan):
    """The two majorities disagree here, which is the point: the older convention holds most of the
    files and none of the attention."""
    entry = conflict_of(scan(split_repo)[1], "conflict.test.style.python")
    assert side(entry, "unittest-class")["file_share"] > 0.5
    assert side(entry, "unittest-class")["recent_share"] == 0.0
    assert side(entry, "pytest-function")["recent_share"] == 1.0


def test_the_scan_resolves_a_conflict_to_a_question_and_never_to_a_winner(split_repo, scan):
    document = scan(split_repo)[1]
    assert [c["resolution"] for c in document["conflicts"]] == ["question"] * len(document["conflicts"])


def test_no_side_is_ever_marked_as_the_one_to_adopt(split_repo, scan):
    """The invariant, pinned as text: nothing in the document may name a winner. A `recommended`
    field would be read as an answer, and the drafting agent would stop asking."""
    document = scan(split_repo)[1]
    body = json.dumps(document["conflicts"])
    assert "recommended" not in body
    assert "recent-dominant" not in body
    assert "winner" not in body


def test_a_side_names_a_file_that_shows_it(split_repo, scan):
    """A share is an argument; the file is what lets someone check the argument."""
    entry = conflict_of(scan(split_repo)[1], "conflict.test.style.python")
    assert side(entry, "unittest-class")["example"].startswith("tests/legacy/")
    assert side(entry, "pytest-function")["example"].startswith("tests/api/")


def test_a_file_that_merely_mentions_a_convention_does_not_count_as_using_it(consistent_repo, scan):
    """The fixture holds a module whose prose names the old way while every test uses the new one.
    This scanner's own source does the same thing, and unscoped it reported itself as the
    repository's one holdout — a finding about the tool, dressed as a finding about the code."""
    code, document = scan(consistent_repo)
    assert code == 0
    assert not any(c["id"] == "conflict.test.style.python" for c in document["conflicts"])


def test_two_rival_tools_for_one_job_are_reported(tmp_path, scan):
    from tests.scripts.tools.code_of_conduct.coc_scan.conftest import build_repo
    import subprocess

    root = build_repo(tmp_path / "rivals")
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\n\n[tool.mypy]\nstrict = true\n\n[tool.pyright]\nx = 1\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "chore: two checkers",
                    "--no-gpg-sign"], check=True, capture_output=True)
    document = scan(root)[1]
    rivals = [c for c in document["conflicts"] if c["id"].startswith("conflict.cfg.")]
    assert rivals
    assert {c["name"] for c in rivals[0]["candidates"]} == {"cfg.types.mypy", "cfg.types.pyright"}


def test_tools_that_serve_different_ecosystems_are_not_rivals(repo, scan):
    """A repository with Python and TypeScript in it needs a runner for each. Grouping by concern
    read those two as a contradiction and asked the user to choose between them."""
    document = scan(repo)[1]
    assert not any(c["id"].startswith("conflict.cfg.") for c in document["conflicts"])
