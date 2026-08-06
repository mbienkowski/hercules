"""Reading a code-of-conduct this generator did not write. Nothing here decides anything: the report
is advice for a person, because a best-effort parse of someone else's prose is not the ground to edit
their file from. What it must do is find a citation that has rotted, and not cry wolf about the
things that merely look like one.
"""

from __future__ import annotations

import io
import subprocess

from tests.scripts.tools.code_of_conduct.coc_lint.conftest import (
    CONTRACT, document, entries)
from tests.scripts.tools.tool_harness import invoke, load_tool


def test_a_citation_that_still_resolves_is_reported_as_verified(review):
    run, _ = review
    code, report = run(document("- MUST: Keep `src/engine.py` small — `make test` covers it.\n"))
    assert code == 0
    assert {e["token"] for e in entries(report, "verified")} == {"src/engine.py", "make test"}


def test_a_path_the_repository_no_longer_has_is_reported_as_dangling(review):
    """The failure this exists to catch: a rule pointing at a file somebody moved."""
    run, _ = review
    code, report = run(document("- MUST: Follow the pattern in `src/renamed_away.py`.\n"))
    assert entries(report, "dangling")[0]["token"] == "src/renamed_away.py"


def test_a_make_target_that_no_longer_exists_is_reported_as_dangling(review):
    run, _ = review
    code, report = run(document("- MUST: Run `make verify` before pushing.\n"))
    assert entries(report, "dangling")[0]["token"] == "make verify"


def test_a_path_is_verified_by_membership_rather_than_by_touching_the_disk(review, tmp_path):
    """A citation is a string somebody else wrote. Resolving it against the filesystem would turn
    the document into a way to ask what exists outside the repository."""
    run, repo = review
    outside = tmp_path / "outside.txt"
    outside.write_text("x\n")
    code, report = run(document(f"- MUST: See `{outside}` and `../../etc/passwd`.\n"))
    assert not entries(report, "verified")
    # Reported as dangling rather than quietly set aside: a rule pointing outside the repository is
    # something to look at, and calling it unparsed would hide it among the prose.
    assert {e["token"] for e in entries(report, "dangling")} == {str(outside), "../../etc/passwd"}


def test_a_path_inside_a_worked_example_is_still_a_citation(review):
    """The owner's format demonstrates with real paths — a worked example that walks a reader
    through a file the repository no longer has is exactly a rotted citation."""
    run, _ = review
    code, report = run(document("\nWorked example:\n\n    1. Edit `src/engine.py`\n"))
    assert {e["token"] for e in entries(report, "verified")} == {"src/engine.py"}


def test_a_package_specifier_is_not_mistaken_for_a_path(review):
    """`js-tiktoken/lite` looks like a path and is a dependency's entry point."""
    run, _ = review
    code, report = run(document("- MUST: Import from `js-tiktoken/lite` only.\n"))
    assert not entries(report, "dangling")


def test_a_separator_quoted_as_itself_is_not_read_as_a_path(review):
    """Prose about syntax quotes the character — measured on a real document, `/` was reported as a
    missing file."""
    run, _ = review
    code, report = run(document("- MUST: A `/` in a branch name nests the ref.\n"))
    assert not entries(report, "dangling")


def test_a_placeholder_is_never_reported_as_missing(review):
    run, _ = review
    code, report = run(document("- MUST: Run `make <target>` for the module you touched.\n"))
    assert not entries(report, "dangling")


def test_prose_that_cites_nothing_verifiable_is_counted_rather_than_guessed_at(review):
    """Most of a real document's backticked tokens are concepts and commands. Reporting them as
    findings would bury the handful that matter. Asserted by naming the concepts rather than by a
    total, so adding a citation to the shared fixture cannot silently pass this test."""
    run, _ = review
    code, report = run(document("- MUST: Prefer `composition` over `inheritance` when `it depends`.\n"))
    assert code == 0
    unparsed = {e["token"] for e in entries(report, "unparsed")}
    assert {"composition", "inheritance", "it depends"} <= unparsed


def test_the_report_says_how_much_of_the_document_it_could_check(review):
    """Its coverage is about a third of citations; a report that did not say so would read as a
    clean bill of health for the whole file."""
    run, _ = review
    code, report = run(document("- MUST: `src/engine.py` and `some concept` and `make build`.\n"))
    resolvable = {e["token"] for e in entries(report, "verified") + entries(report, "dangling")}
    assert {"src/engine.py", "make build"} <= resolvable
    assert "some concept" not in resolvable
    assert report["citations_resolvable"] < report["tokens"]


def test_a_document_that_cannot_be_read_is_refused(repo, tmp_path):
    main = load_tool("coc_lint")
    code, report = invoke(main, None, ["--contract", str(CONTRACT),
                                       "--file", str(tmp_path / "absent.md"),
                                       "--root", str(repo)], stdin=io.StringIO(""))
    assert code == 1
    assert report["error"] == "refused"


def test_a_document_of_hostile_markdown_is_reported_rather_than_crashed_on(review):
    run, _ = review
    code, report = run(document("`" * 5000 + "\n- ``` `` ` weird `\n"))
    assert code in (0, 1)
    assert isinstance(report["entries"], list)


def test_nothing_in_the_document_is_ever_edited(review, tmp_path):
    run, _ = review
    before = document("- MUST: Follow `src/renamed_away.py`.\n")
    code, report = run(before)
    assert (tmp_path / "code-of-conduct.md").read_text() == before
