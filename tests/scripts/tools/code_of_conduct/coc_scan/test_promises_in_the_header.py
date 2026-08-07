"""The properties this tool's own header states, pinned. A claim in a header is a promise a reader
relies on and nothing else keeps, so each of these exists because the module says it is true.
"""

from __future__ import annotations

import json
import subprocess

from tests.scripts.tools.code_of_conduct.coc_scan.conftest import CONTRACT, build_repo
from tests.scripts.tools.tool_harness import invoke, load_tool


def test_an_unclassified_failure_refuses_rather_than_reporting_an_empty_repository(repo,
                                                                                   monkeypatch):
    """"Fails closed" is the header's claim, and the failure it guards against is subtle: a scan that
    errored halfway would otherwise emit a document describing a repository with nothing in it, which
    reads downstream exactly like a repository that genuinely has nothing."""
    # `load_tool` is what puts the tools directory on the path, so it comes first:
    # importing the module directly would depend on another test having run.
    load_tool("coc_scan")
    import coc_scan

    def explode(*_args, **_kwargs):
        raise RuntimeError("something nobody anticipated")

    monkeypatch.setattr(coc_scan, "liveness", explode)
    code, document = invoke(coc_scan.main, None,
                            ["all", "--root", str(repo), "--contract", str(CONTRACT)])
    assert code == 4
    assert document["error"] == "internal"
    assert "facts" not in document


def test_a_release_history_is_reported_when_the_repository_tags_one(tmp_path, scan):
    repo = build_repo(tmp_path / "tagged")
    for tag in ("v1.0.0", "v1.1.0", "nightly"):
        subprocess.run(["git", "-C", str(repo), "tag", tag], check=True, capture_output=True)
    code, document = scan(repo)
    assert code == 0
    tagging = next(f for f in document["facts"] if f["id"] == "hist.release.tagging")
    assert tagging["value"] == {"tags": 3, "semver_like": 2}


def test_a_repository_that_tags_nothing_claims_no_release_scheme(repo, scan):
    """Absent evidence yields no fact — a repository with no tags has not chosen a scheme, and
    saying it has none would be a finding nobody observed."""
    code, document = scan(repo)
    assert not any(f["id"] == "hist.release.tagging" for f in document["facts"])
