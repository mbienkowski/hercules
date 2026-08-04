"""The properties this tool's own header states, pinned: it reports both halves or says which half it
skipped, and it never answers a citation from anywhere but the repository's own file list."""

from __future__ import annotations

import io

from tests.scripts.tools.code_of_conduct.coc_lint.conftest import CONTRACT, VALID_SHAPE
from tests.scripts.tools.tool_harness import invoke, load_tool


def test_a_document_checked_without_a_repository_reports_shape_only(tmp_path):
    """Verification is membership in the repository's file list. With no repository there is no
    list — so the shape is still checked and the citations are honestly left alone, rather than
    answered from the filesystem, which is the thing this must never do."""
    main = load_tool("coc_lint")
    document = tmp_path / "coc.md"
    document.write_text(VALID_SHAPE + "- **MUST** See `src/engine.py` — CI checks it.\n")
    code, report = invoke(main, None, ["--contract", str(CONTRACT), "--file", str(document)], stdin=io.StringIO(""))
    assert code == 0
    assert report["checked"] == "shape"
    assert "entries" not in report


def test_a_path_cited_as_a_directory_resolves_to_the_directory(tmp_path):
    """A code-of-conduct cites areas as often as files — `src/` is a citation, not a typo."""
    main = load_tool("coc_lint")
    import subprocess
    root = tmp_path / "project"
    (root / "src" / "deep").mkdir(parents=True)
    (root / "src" / "deep" / "engine.py").write_text("x\n")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t.t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init", "--no-gpg-sign"], check=True, capture_output=True)
    document = tmp_path / "coc.md"
    document.write_text(VALID_SHAPE
                        + "- **MUST** Everything under `src/deep` follows this, see `engine.py`.\n")
    code, report = invoke(main, None, ["--contract", str(CONTRACT),
                                       "--file", str(document), "--root", str(root)],
                          stdin=io.StringIO(""))
    assert code == 0
    verified = {entry["token"] for entry in report["entries"] if entry["state"] == "verified"}
    assert verified == {"src/deep", "engine.py"}


def test_shape_binds_a_draft_but_only_informs_about_a_document_that_exists(tmp_path, lint, review):
    """Update mode never retro-fits an existing bullet with a tag or a reason. Listing an existing
    document's shape as something to fix would invite precisely that edit, so it is reported apart
    from the findings and does not decide the exit code."""
    badly_shaped = "## Development\n\n- Keep it tidy.\n"

    code, draft = lint(badly_shaped)
    assert code == 1
    assert draft["shape_binds"] is True
    assert [f["rule"] for f in draft["findings"]]

    run, _ = review
    code, existing = run(badly_shaped)
    assert code == 0
    assert existing["shape_binds"] is False
    assert existing["findings"] == []
    assert [n["rule"] for n in existing["shape_notes"]]


def test_a_rotted_citation_is_a_finding_no_matter_who_wrote_the_document(review):
    """Shape is a convention someone may legitimately differ on. A path the repository does not have
    is simply wrong."""
    run, _ = review
    code, report = run("## Development\n\n- Follow `src/renamed_away.py`.\n")
    assert code == 1
    assert [f["rule"] for f in report["findings"]] == ["citation_dangling"]
