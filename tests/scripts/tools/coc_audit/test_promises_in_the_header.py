"""The properties this tool's own header states, pinned. A gate that errs open is not a gate, so the
claim that it fails closed is the one worth a test of its own.
"""

from __future__ import annotations

import io
import json

from tests.scripts.tools.coc_audit.conftest import CONTRACT, an_envelope
from tests.scripts.tools.tool_harness import invoke, load_tool


def test_an_unclassified_failure_refuses_rather_than_passing_the_draft(monkeypatch):
    """The dangerous direction is only one: a gate that errors and returns zero waves through a
    draft nobody judged, and reads exactly like a draft that passed."""
    # `load_tool` is what puts the tools directory on the path, so it comes first:
    # importing the module directly would depend on another test having run.
    load_tool("coc_audit")
    import coc_audit

    def explode(*_args, **_kwargs):
        raise RuntimeError("something nobody anticipated")

    monkeypatch.setattr(coc_audit, "judge", explode)
    code, report = invoke(coc_audit.main, None, ["draft", "--contract", str(CONTRACT)],
                          stdin=io.StringIO(json.dumps(an_envelope())))
    assert code == 4
    assert report["error"] == "internal"


def test_reviewing_an_existing_document_needs_both_the_file_and_the_repository(tmp_path):
    """Verification is membership in the repository's file list; without the repository there is no
    list, and answering from the filesystem instead is the thing this must never do."""
    main = load_tool("coc_audit")
    document = tmp_path / "coc.md"
    document.write_text("- See `src/engine.py`.\n")
    code, report = invoke(main, None, ["existing", "--contract", str(CONTRACT),
                                       "--file", str(document)], stdin=io.StringIO(""))
    assert code == 4
    assert report["error"] == "internal"


def test_a_path_cited_as_a_directory_resolves_to_the_directory(tmp_path):
    """A code-of-conduct cites areas as often as files — `src/` is a citation, not a typo."""
    main = load_tool("coc_audit")
    import subprocess
    root = tmp_path / "project"
    (root / "src" / "deep").mkdir(parents=True)
    (root / "src" / "deep" / "engine.py").write_text("x\n")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t.t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init", "--no-gpg-sign"], check=True, capture_output=True)
    document = tmp_path / "coc.md"
    document.write_text("- Everything under `src/deep` follows this, see `engine.py`.\n")
    code, report = invoke(main, None, ["existing", "--contract", str(CONTRACT),
                                       "--file", str(document), "--root", str(root)],
                          stdin=io.StringIO(""))
    assert code == 0
    verified = {entry["token"] for entry in report["entries"] if entry["state"] == "verified"}
    assert verified == {"src/deep", "engine.py"}
