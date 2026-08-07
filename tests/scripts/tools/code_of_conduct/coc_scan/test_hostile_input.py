"""The repository being scanned is written by whoever wrote it, and the scan runs with the user's
authority. These are the properties that hold when it was written to break the scan rather than to be
read by one."""

from __future__ import annotations

import json
import subprocess

from tests.scripts.tools.code_of_conduct.coc_scan.conftest import build_repo


def _commit_file_named(root, name: str, subject: str = "chore: add"):
    """Commit dated just after the fixture's own last commit, so HEAD stays the anchor every window
    is measured back from and these repositories do not drift with the day the suite runs."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n")
    last = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%ct"],
                          check=True, capture_output=True, text=True).stdout.strip()
    stamp = f"{int(last) + 86400} +0000"
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", subject, "--no-gpg-sign"],
                   check=True, capture_output=True,
                   env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp,
                        "GIT_AUTHOR_NAME": "Fixture", "GIT_COMMITTER_NAME": "Fixture",
                        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
                        "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(root)})


def test_a_newline_in_a_filename_fabricates_no_path(tmp_path, scan):
    """Line-splitting git's output turns one such file into two invented paths — measured on the
    first version of this scan, which reported a directory named `"src` that never existed."""
    repo = build_repo(tmp_path / "hostile")
    _commit_file_named(repo, "src/eve\nil.py")
    code, doc = scan(repo)
    assert code == 0
    paths = [d["path"] for d in doc["liveness"]["directories"]]
    assert not any('"' in p for p in paths)
    assert not any(p.strip() == "" for p in paths)


def test_a_leading_newline_twin_inflates_no_real_files_count(tmp_path, scan):
    """git frames each commit's paths with exactly one newline after the header. Stripping any more
    folds a filename that itself begins with a newline onto the name after it — so committing a twin
    named "\\nsrc/real.py" credited its touches to `src/real.py`, letting a crafted name push any
    real file up the liveness ranking the drafting agent reads from."""
    repo = build_repo(tmp_path / "twin")
    _commit_file_named(repo, "src/real.py")
    _commit_file_named(repo, "\nsrc/real.py", subject="chore: twin")
    code, doc = scan(repo)
    assert code == 0
    counts = {f["path"]: f["touches"] for f in doc["liveness"]["top_files"]}
    assert counts.get("src/real.py") == 1  # its own commit, never the twin's
    # The twin keeps its own touch under its own name — spelled with its control character ESCAPED,
    # because the emit boundary makes every string inert. Escaped rather than stripped precisely so
    # the two names stay distinguishable here: dropping the newline would render both as
    # `src/real.py`, recreating by presentation the confusion this test exists to refuse.
    assert counts.get("\\x0asrc/real.py") == 1


def test_a_repository_setting_its_own_quoting_cannot_change_how_paths_are_read(tmp_path, scan):
    """`core.quotePath` lives in the repository's own config, so a scan that trusts the default is
    reading whatever the repository decided it should read."""
    repo = build_repo(tmp_path / "quoting")
    subprocess.run(["git", "-C", str(repo), "config", "core.quotePath", "true"],
                   check=True, capture_output=True)
    _commit_file_named(repo, "src/naïve.py")
    code, doc = scan(repo)
    assert code == 0
    # Asserted by PRESENCE, not by absence of escaping: a quoted path fails to match anything at
    # HEAD and is dropped as a ghost, so "no backslashes appear" would hold precisely when the file
    # had vanished from the report altogether.
    assert "src/naïve.py" in [f["path"] for f in doc["liveness"]["top_files"]]
    assert doc["liveness"]["ghost_touches_dropped"] == 1  # only the fixture's deliberate rename


def test_an_inherited_git_dir_cannot_redirect_the_scan(tmp_path, scan, monkeypatch):
    """GIT_DIR overrides git's own `-C` discovery. Inherited from the caller's shell, it would make
    every git question silently answer about a different repository than the one `--root` names —
    a wrong answer shaped exactly like a finding, the failure the module header calls the worst
    one."""
    target = build_repo(tmp_path / "target")
    other = build_repo(tmp_path / "other", base_epoch=1_800_000_000)
    # Resolved before the variables are set: the verifying command would be redirected too.
    head = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    code, doc = scan(target)
    assert code == 0
    assert doc["head"] == head


def test_a_commit_subject_reaches_the_document_only_as_bounded_evidence(tmp_path, scan):
    """Subjects are attacker-authored text on the way to a model that then writes files. The scope
    is where a subject actually reaches the document, so that is where the cap has to hold."""
    repo = build_repo(tmp_path / "injection")
    _commit_file_named(repo, "noisy.txt", subject="feat(" + "A" * 5000 + "): x")
    code, doc = scan(repo)
    assert code == 0
    scopes = next(f for f in doc["facts"]
                  if f["id"] == "hist.commit.convention")["value"]["scopes_seen"]
    assert scopes
    assert all(len(scope) <= 40 for scope in scopes)
