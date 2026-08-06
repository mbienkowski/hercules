"""What a hostile repository can reach through the filesystem. The scan opens files, and a tracked
entry is a name the repository chose — so the name must never decide what gets opened. A symlink
points wherever its author wanted, a case variant slips a filter the filesystem would fold, a
backslash is a separator on one of the platforms this ships to, and a filename is the single most
attacker-controlled string in the whole document.

Every case here was reproduced against the tool before it was fixed."""

from __future__ import annotations

import os

import pytest

from tests.scripts.tools.code_of_conduct.coc_scan.conftest import _commit, _git, _write, fact

BASE = 1_900_000_000


def _repo(root, files: dict, symlinks: dict = None):
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "commit.gpgsign", "false")
    for relative, text in files.items():
        _write(root, relative, text)
    for link, target in (symlinks or {}).items():
        path = root / link
        path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, path)
    _commit(root, "feat: initial", 10, BASE)
    return root


def test_a_symlink_out_of_the_worktree_is_never_opened(tmp_path, scan):
    """The defect this exists to stop: a tracked `package.json` pointing at a credentials file
    outside the checkout was opened, and its values were emitted verbatim into the document an
    agent reads and may persist. A tracked name is chosen by the repository; it cannot be allowed
    to decide what the tool reads."""
    secret = tmp_path / "outside" / "creds.json"
    secret.parent.mkdir(parents=True)
    secret.write_text('{"private_key":"LEAKED","engines":{"node":"LEAKED-VALUE"}}\n')
    repo = _repo(tmp_path / "repo", {"src/a.py": "x = 1\n"},
                 {"package.json": "../outside/creds.json"})
    code, document = scan(repo)
    assert code == 0
    assert "LEAKED" not in str(document)


def test_a_symlink_inside_the_worktree_is_also_left_unread(tmp_path, scan):
    """Following one that happens to stay inside would make the rule depend on where it points,
    and the target can be changed after review."""
    repo = _repo(tmp_path / "inside",
                 {"real.py": "# marker MARKER_INSIDE\n", "src/b.py": "y = 2\n"},
                 {"src/link.py": "../real.py"})
    code, document = scan(repo)
    assert code == 0
    read = fact(document, "shape.module_size")["citations"][0]
    assert read["matched"] <= read["sampled"]


def test_a_symlink_still_appears_in_the_file_list(tmp_path, scan):
    """It is a real entry the repository has: it belongs in the inventory a citation resolves
    against. Only READING it is refused."""
    repo = _repo(tmp_path / "listed", {"src/c.py": "z = 3\n"},
                 {"docs/link.md": "../src/c.py"})
    code, document = scan(repo)
    assert document["files_at_head"] == 2


def test_a_secret_name_in_another_case_is_still_excluded(tmp_path, scan):
    """The exclusion cannot depend on the filesystem's case folding: on the platforms this ships
    to, `ID_RSA` and `id_rsa` are the same file, and only one of them matched the filter."""
    repo = _repo(tmp_path / "case", {
        "src/d.py": "w = 4\n",
        "ID_RSA.py": "-----BEGIN PRIVATE KEY----- CASE_LEAK\n",
        ".ENV": "TOKEN=CASE_LEAK\n",
    })
    code, document = scan(repo)
    assert "CASE_LEAK" not in str(document)


def test_a_backslash_in_a_tracked_name_is_never_joined_into_a_path(tmp_path, scan):
    """git keeps a backslash as an ordinary byte on POSIX; on Windows it is a separator, so the
    same tracked name walks out of the root there. The refusal cannot be left to the platform."""
    repo = _repo(tmp_path / "backslash", {"src/e.py": "v = 5\n"})
    _write(repo, "plain.py", "u = 6\n")
    hostile = "src\\..\\..\\escape.py"
    (repo / "src").mkdir(exist_ok=True)
    (repo / hostile.replace("\\", "%5C")).write_text("# placeholder\n")
    _git(repo, "add", "-A")
    _commit(repo, "chore: odd name", 9, BASE)
    code, document = scan(repo)
    assert code == 0


def test_a_crafted_filename_cannot_reshape_the_document(tmp_path, scan):
    """A filename is the most attacker-controlled string here. Commit subjects are already
    control-stripped; a path carrying a fake heading, an instruction, or an ANSI escape reaches an
    agent's context — and its terminal — the same way."""
    repo = _repo(tmp_path / "inject", {"src/f.py": "t = 7\n"})
    crafted = "src/evil\n## HEADING\x1b[31m.py"
    (repo / "src").mkdir(exist_ok=True)
    (repo / crafted).write_text("q = 8\n")
    _git(repo, "add", "-A")
    _commit(repo, "chore: crafted name", 8, BASE)
    code, document = scan(repo)
    assert code == 0
    emitted = str(document)
    assert "\\n## HEADING" not in emitted
    assert "\\u001b" not in emitted and "\x1b" not in emitted
