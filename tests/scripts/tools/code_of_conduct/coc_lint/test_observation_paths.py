"""Verifying the draft's observations against the repository. The gate is pure and can only judge an
observation's shape; the path inside it is a claim about the repository, and this is where the claim
meets the file list — by membership, never by touching the disk, exactly as every other citation."""

from __future__ import annotations

import subprocess

from tests.scripts.tools.code_of_conduct.coc_lint.conftest import (
    CONTRACT, VALID_SHAPE, findings)


def test_an_observation_path_the_repository_has_is_verified(lint, repo):
    code, report = lint(VALID_SHAPE, argv=["--contract", str(CONTRACT), "--root", str(repo)],
                        paths=["src/engine.py"])
    assert code == 0
    assert report["declared_paths"] == [
        {"path": "src/engine.py", "state": "verified"}]


def test_an_observation_path_the_repository_lacks_is_a_finding(lint, repo):
    """A rule was justified by a file that is not there: the exact invented-evidence shape the
    envelope gate cannot see, caught at the one point where the file list is in reach."""
    code, report = lint(VALID_SHAPE, argv=["--contract", str(CONTRACT), "--root", str(repo)],
                        paths=["src/imagined.py"])
    assert code == 1
    assert findings(report, "observation_dangling")


def test_an_observation_may_name_a_directory(lint, repo):
    """Architecture observations are about areas as often as files."""
    code, report = lint(VALID_SHAPE, argv=["--contract", str(CONTRACT), "--root", str(repo)],
                        paths=["src"])
    assert code == 0
    assert report["declared_paths"][0]["state"] == "verified"


def test_paths_without_a_repository_are_refused(lint):
    """No repository means no file list, and a clean exit here would read as verification of paths
    nothing looked at — the exact silent gap that once let an invented observation ship. The tool
    refuses instead, naming the missing flag."""
    code, report = lint(VALID_SHAPE, paths=["src/imagined.py"])
    assert code == 4
    assert report["error"] == "internal"
    assert "--root" in report["message"]


def test_an_inherited_git_dir_cannot_redirect_verification(lint, repo, tmp_path, monkeypatch):
    """GIT_DIR overrides git's own `-C` discovery: inherited from the caller's shell, it would hold
    every citation against a different repository than `--root` names — real paths dangling, and a
    hostile GIT_DIR vouching for paths the project does not have."""
    other = tmp_path / "other"
    (other / "docs").mkdir(parents=True)
    (other / "docs" / "unrelated.md").write_text("x\n")
    subprocess.run(["git", "-C", str(other), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(other), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(other), "-c", "user.email=t@t.t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init", "--no-gpg-sign"], check=True, capture_output=True)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    code, report = lint(VALID_SHAPE, argv=["--contract", str(CONTRACT), "--root", str(repo)],
                        paths=["src/engine.py"])
    assert code == 0
    assert report["declared_paths"] == [{"path": "src/engine.py", "state": "verified"}]


def test_paths_that_are_not_a_list_of_strings_are_refused(lint, repo):
    code, report = lint(VALID_SHAPE, argv=["--contract", str(CONTRACT), "--root", str(repo)],
                        paths="src/engine.py")
    assert code == 4
