"""What a lying verification, a dropped permission bit, or a crossed filesystem boundary looks like
— all invisible from the command line, so each is written against the helper directly."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from tests.scripts.tools.project_reset.conftest import apply, run

import project_reset  # noqa: E402 — conftest puts src/scripts/tools on the path


@pytest.mark.parametrize("stored,expected", [
    ({"sessions": {"a": 1, "b": 2}}, False),  # the key that should have been removed survived
    ({"sessions": {"b": 99}}, False),  # the right key is gone, but an untouched neighbour was altered
    ({"sessions": {"b": 2}}, True),  # the positive companion — a real match
], ids=["key-survived", "neighbour-altered", "real-match"])
def test_verification_reports_whether_the_file_really_matches_the_claimed_removal(tmp_path, stored, expected):
    """`verified: true` could be hard-coded and unnoticed if only the flag were asserted — this checks
    it against a file where the removal did, and did not, happen."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps(stored))
    before = {"sessions": {"a": 1, "b": 2}}
    assert project_reset.verify_removed(path, ["a"], "sessions", before) is expected


def test_a_rewrite_carries_the_original_permission_bits(tmp_path):
    """0o600 is exactly what `mkstemp` produces on its own, so it would pass either way; this uses a
    mode the temporary file never gets by accident, which is the only way the assertion means something."""
    path = tmp_path / "state.json"
    path.write_text("{}")
    os.chmod(path, 0o640)
    project_reset.atomic_write_json(path, {"kept": True})
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_a_symlink_is_removed_as_a_link_and_its_target_is_left_alone(tmp_path):
    """Walking without following a link is not the same as refusing to follow one."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("survives\n")
    tree = tmp_path / "tree"
    tree.mkdir()
    os.symlink(outside, tree / "link")
    assert project_reset.delete_tree(tree) == []
    assert not tree.exists()
    assert (outside / "keep.txt").read_text() == "survives\n"


def test_an_entry_on_another_filesystem_is_left_where_it_is(tmp_path, monkeypatch):
    """A mount swapped in under the tree must stop the walk rather than be removed with it. A real
    mount cannot be staged in a unit test, so the device identity is what is varied."""
    tree = tmp_path / "tree"
    (tree / "inner").mkdir(parents=True)
    (tree / "inner" / "foreign.txt").write_text("on another volume\n")
    real_stat = Path.stat

    def lying_stat(self, *a, **kw):
        result = real_stat(self, *a, **kw)
        # A real mount carries its whole subtree on the foreign device, not just its root.
        if "inner" in self.parts:
            return os.stat_result(tuple(result)[:2] + (result.st_dev + 1,) + tuple(result)[3:])
        return result

    monkeypatch.setattr(Path, "stat", lying_stat)
    project_reset.delete_tree(tree)
    assert (tree / "inner" / "foreign.txt").exists()


def test_a_symlink_pointing_at_another_volume_is_still_removed(tmp_path, monkeypatch):
    """Removing a link never touches what it points at, so judging it by the target's filesystem would
    strand it in a tree the person asked to be cleared."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    tree = tmp_path / "tree"
    tree.mkdir()
    os.symlink(outside, tree / "link")
    real_stat = Path.stat

    def foreign_target(self, *a, **kw):
        result = real_stat(self, *a, **kw)
        if self.name == "link":  # follows the link, so this is the TARGET's device
            return os.stat_result(tuple(result)[:2] + (result.st_dev + 1,) + tuple(result)[3:])
        return result

    monkeypatch.setattr(Path, "stat", foreign_target)
    project_reset.delete_tree(tree)
    assert not tree.exists()
    assert outside.is_dir()


def test_an_unclassified_failure_deletes_nothing_and_reports_it(fx, monkeypatch):
    """The catch-all exists so an unanticipated error resolves to doing nothing; nothing in the normal
    flow raises one, so it could be narrowed to an unreachable type and no test would object."""
    monkeypatch.setattr(project_reset, "delete_tree",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("unexpected")))
    code, payload = apply(fx, "--documents")
    assert code == 4
    assert fx.docs.exists()
    assert payload["message"].strip()


@pytest.mark.parametrize("mode", ["plan", "apply"])
def test_the_reply_names_its_mode_so_a_caller_cannot_confuse_the_two(fx, mode):
    """A confirmation rendered from an apply reply, or a result rendered from a plan reply, would
    both look plausible. The mode is what tells them apart."""
    argv = ("apply", "--contract", "1", "--confirm") if mode == "apply" else ("plan", "--contract", "1")
    _, payload = run(fx, *argv)
    assert payload["mode"] == mode


def test_the_folder_count_names_features_not_every_directory(tmp_path):
    """Rendered to a person as "N feature folders", so it must mean that: a documents folder that is
    its own repository carries a `.git` directory, and counting it would report one feature too many."""
    docs = tmp_path / "docs"
    (docs / "2026-01-01-alpha").mkdir(parents=True)
    (docs / "2026-01-02-beta").mkdir()
    (docs / ".git").mkdir()
    row = project_reset.documents_row({"docs_root": str(docs), "directory": str(tmp_path / "code")})
    assert row["folders"] == 2
