"""Every way the scan declines, and the one it must never take: reporting an empty repository when it
simply could not read one. A wrong answer that looks like a finding is worse than a refusal, because
nothing downstream can tell it apart from the truth."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.scripts.tools.code_of_conduct.coc_scan.conftest import CONTRACT, build_repo


def test_a_contract_the_tool_does_not_speak_is_refused(repo, scan):
    code, doc = scan(repo, argv=["all", "--root", str(repo), "--contract", "99"])
    assert code == 2
    assert doc["error"] == "contract"


def test_a_directory_that_is_not_a_repository_is_refused(tmp_path, scan):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    code, doc = scan(plain)
    assert code == 1
    assert doc["error"] == "refused"


def test_a_repository_with_no_commits_is_refused_rather_than_reported_as_empty(tmp_path, scan):
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    subprocess.run(["git", "-C", str(fresh), "init", "-q"], check=True, capture_output=True)
    code, doc = scan(fresh)
    assert code == 1
    assert doc["error"] == "refused"


def test_a_bare_repository_is_read_rather_than_reported_as_empty(tmp_path, scan):
    """`ls-files` reads an index, which a bare clone has none of. Measured on a real bare clone, the
    first version of this scan reported zero files for a repository holding seven thousand."""
    source = build_repo(tmp_path / "source")
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(source), str(bare)],
                   check=True, capture_output=True)
    code, doc = scan(bare)
    assert code == 0
    assert doc["files_at_head"] > 0
    assert doc["root_kind"] == "bare"


def test_an_unknown_mode_is_refused_as_usage(repo, scan):
    code, doc = scan(repo, argv=["sniff", "--root", str(repo), "--contract", str(CONTRACT)])
    assert code == 4
    assert doc["error"] == "usage"


def test_the_reply_is_one_json_object_on_every_path(tmp_path, repo, scan):
    plain = tmp_path / "plain"
    plain.mkdir()
    for root in (repo, plain):
        code, doc = scan(root)
        assert isinstance(doc, dict)
        assert doc["contract"] == CONTRACT
