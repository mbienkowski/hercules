"""Reading a code-of-conduct this generator did not write. Nothing here decides anything: the report
is advice for a person, because a best-effort parse of someone else's prose is not the ground to edit
their file from. What it must do is find a citation that has rotted, and not cry wolf about the three
things that merely look like one.
"""

from __future__ import annotations

import io
import json
import subprocess

import pytest

from tests.scripts.tools.coc_audit.conftest import CONTRACT
from tests.scripts.tools.tool_harness import invoke, load_tool


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "engine.py").write_text("x\n")
    (root / "Makefile").write_text("build:\n\techo hi\ntest:\n\techo hi\n")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t.t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init", "--no-gpg-sign"], check=True, capture_output=True)
    return root


@pytest.fixture
def review(repo, tmp_path):
    main = load_tool("coc_audit")

    def run(markdown, name="code-of-conduct.md"):
        document = tmp_path / name
        document.write_text(markdown)
        return invoke(main, None, ["existing", "--contract", str(CONTRACT),
                                   "--file", str(document), "--root", str(repo)],
                      stdin=io.StringIO(""))

    return run, repo


def entries(report, state):
    return [e for e in report["entries"] if e["state"] == state]


def test_a_citation_that_still_resolves_is_reported_as_verified(review):
    run, _ = review
    code, report = run("- Keep `src/engine.py` small — `make test` covers it.\n")
    assert code == 0
    assert {e["token"] for e in entries(report, "verified")} == {"src/engine.py", "make test"}


def test_a_path_the_repository_no_longer_has_is_reported_as_dangling(review):
    """The failure this exists to catch: a rule pointing at a file somebody moved."""
    run, _ = review
    code, report = run("- Follow the pattern in `src/renamed_away.py`.\n")
    assert entries(report, "dangling")[0]["token"] == "src/renamed_away.py"


def test_a_make_target_that_no_longer_exists_is_reported_as_dangling(review):
    run, _ = review
    code, report = run("- Run `make verify` before pushing.\n")
    assert entries(report, "dangling")[0]["token"] == "make verify"


def test_a_path_is_verified_by_membership_rather_than_by_touching_the_disk(review, tmp_path):
    """A citation is a string somebody else wrote. Resolving it against the filesystem would turn
    the document into a way to ask what exists outside the repository."""
    run, repo = review
    outside = tmp_path / "outside.txt"
    outside.write_text("x\n")
    code, report = run(f"- See `{outside}` and `../../etc/passwd`.\n")
    assert not entries(report, "verified")
    # Reported as dangling rather than quietly set aside: a rule pointing outside the repository is
    # something to look at, and calling it unparsed would hide it among the prose.
    assert {e["token"] for e in entries(report, "dangling")} == {str(outside), "../../etc/passwd"}


def test_an_example_inside_a_do_or_dont_line_is_not_treated_as_a_citation(review):
    """Measured against a real document: fragments in an example pair were the largest source of
    false alarms, and they are names chosen to be wrong."""
    run, _ = review
    code, report = run("**DON'T:** `src/badname.py`\n**DO:** `src/engine.py`\n")
    assert code == 0
    assert not entries(report, "dangling")


def test_a_package_specifier_is_not_mistaken_for_a_path(review):
    """`js-tiktoken/lite` looks like a path and is a dependency's entry point."""
    run, _ = review
    code, report = run("- Import from `js-tiktoken/lite` only.\n")
    assert not entries(report, "dangling")


def test_a_separator_quoted_as_itself_is_not_read_as_a_path(review):
    """Prose about syntax quotes the character — measured on a real document, `/` was reported as a
    missing file."""
    run, _ = review
    code, report = run("- A `/` in a branch name nests the ref.\n")
    assert not entries(report, "dangling")


def test_a_placeholder_is_never_reported_as_missing(review):
    run, _ = review
    code, report = run("- Run `make <target>` for the module you touched.\n")
    assert not entries(report, "dangling")


def test_prose_that_cites_nothing_verifiable_is_counted_rather_than_guessed_at(review):
    """Two thirds of a real document's backticked tokens are concepts and commands. Reporting them
    as findings would bury the handful that matter."""
    run, _ = review
    code, report = run("- Prefer `composition` over `inheritance` when `it depends`.\n")
    assert code == 0
    assert report["tally"]["unparsed"] == 3


def test_the_report_says_how_much_of_the_document_it_could_check(review):
    """Its coverage is about a third of citations; a report that did not say so would read as a
    clean bill of health for the whole file."""
    run, _ = review
    code, report = run("- `src/engine.py` and `some concept` and `make build`.\n")
    assert report["checked"] == 2
    assert report["tokens"] == 3


def test_a_document_that_cannot_be_read_is_refused(repo, tmp_path):
    main = load_tool("coc_audit")
    code, report = invoke(main, None, ["existing", "--contract", str(CONTRACT),
                                       "--file", str(tmp_path / "absent.md"),
                                       "--root", str(repo)], stdin=io.StringIO(""))
    assert code == 1
    assert report["error"] == "refused"


def test_a_document_of_hostile_markdown_is_reported_rather_than_crashed_on(review):
    run, _ = review
    code, report = run("`" * 5000 + "\n- ``` `` ` weird `\n")
    assert code in (0, 1)
    assert isinstance(report["entries"], list)


def test_nothing_in_the_document_is_ever_edited(review, tmp_path):
    run, _ = review
    before = "- Follow `src/renamed_away.py`.\n"
    code, report = run(before)
    assert (tmp_path / "code-of-conduct.md").read_text() == before
