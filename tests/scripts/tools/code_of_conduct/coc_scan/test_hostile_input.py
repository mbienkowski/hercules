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


def test_a_secret_bearing_path_is_never_read(tmp_path, scan):
    """Structure may be recorded; contents never. The document is fed to a model and persisted.
    The file is given a code suffix deliberately: a `.env` would be skipped for not being code at
    all, which would let this pass while the exclusion it names did nothing."""
    repo = build_repo(tmp_path / "secrets")
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "credentials.py").write_text("TOKEN = 'super-secret'\n# TODO: rotate\n")
    _commit_file_named(repo, "keep.txt", subject="chore: add credentials")
    code, doc = scan(repo)
    assert code == 0
    assert "super-secret" not in json.dumps(doc)
    density = next(f for f in doc["facts"] if f["id"] == "shape.marker_density")
    # Its marker is not counted, and it is absent from the sample's denominator too — the file was
    # never a candidate, rather than a candidate that happened to be skipped when opened.
    assert density["value"]["markers"] == 1  # the fixture's own marker, not this file's
    citation = density["citations"][0]
    assert citation["matched"] == citation["sampled"]


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
