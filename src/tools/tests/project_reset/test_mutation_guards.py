"""Tests that exist because a mutation campaign proved the suite could not see these properties.

Each one here killed a mutant that survived the first pass. They are written against the helpers
directly, because the behaviours they pin are invisible from the command line: a lying verification
still reports success, a preserved permission bit matches whatever the temporary file happened to
get, and a crossed filesystem boundary cannot be staged through the normal flow.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from tools.tests.project_reset.conftest import apply, build_home

import project_reset  # noqa: E402 — conftest puts src/tools on the path


def test_verification_reports_failure_when_a_key_it_should_have_removed_survived(tmp_path):
    """The first campaign showed `verified: true` could be hard-coded and nothing would notice — the
    original test asserted the flag, which a lying implementation satisfies just as well. This asserts
    the flag against a file where the removal did NOT happen, so only a real check can pass."""
    path = tmp_path / "state.json"
    path.write_text('{"sessions": {"a": 1, "b": 2}}')
    before = {"sessions": {"a": 1, "b": 2}}
    assert project_reset.verify_removed(path, ["a"], "sessions", before) is False


def test_verification_reports_failure_when_an_untouched_key_was_altered(tmp_path):
    """The other half of the same property: removing the right key is not enough if a neighbour
    changed on the way past."""
    path = tmp_path / "state.json"
    path.write_text('{"sessions": {"b": 99}}')
    before = {"sessions": {"a": 1, "b": 2}}
    assert project_reset.verify_removed(path, ["a"], "sessions", before) is False


def test_verification_reports_success_only_when_the_file_really_matches(tmp_path):
    """The positive companion — without it the two checks above would pass against a function that
    always returns False."""
    path = tmp_path / "state.json"
    path.write_text('{"sessions": {"b": 2}}')
    assert project_reset.verify_removed(path, ["a"], "sessions", {"sessions": {"a": 1, "b": 2}}) is True


def test_a_rewrite_carries_the_original_permission_bits(tmp_path):
    """The original test chose 0o600 — exactly what `mkstemp` produces on its own — so it passed
    whether or not the code copied anything. This uses a mode the temporary file never gets by
    accident, which is the only way the assertion means something."""
    path = tmp_path / "state.json"
    path.write_text("{}")
    os.chmod(path, 0o640)
    project_reset.atomic_write_json(path, {"kept": True})
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_a_symlink_is_removed_as_a_link_and_its_target_is_left_alone(tmp_path):
    """Walking without following links is not the same as refusing to follow one. This removes a
    tree whose only content is a link to a populated directory and proves the directory survives
    with its contents — the link is unlinked, never walked."""
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
    """Removing a link never touches what it points at, so where it points must not decide whether
    it can go. Judging a link by its target's filesystem would strand it in a tree the person asked
    to be cleared — and the first campaign showed the guard against that was invisible to the suite,
    because every link in it happened to point somewhere on the same volume."""
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


def test_an_unclassified_failure_deletes_nothing_and_reports_it(tmp_path, monkeypatch):
    """The catch-all exists so an error nobody anticipated resolves to doing nothing. Nothing in the
    normal flow raises one, so the campaign showed it could be narrowed to an unreachable type and no
    test would object."""
    fx = build_home(tmp_path)
    monkeypatch.setattr(project_reset, "delete_tree",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("unexpected")))
    code, payload = apply(fx, "--documents")
    assert code == 4
    assert fx.docs.exists()
    assert payload["message"].strip()


@pytest.mark.parametrize("mode", ["plan", "apply"])
def test_the_reply_names_its_mode_so_a_caller_cannot_confuse_the_two(tmp_path, mode):
    """A confirmation rendered from an apply reply, or a result rendered from a plan reply, would
    both look plausible. The mode is what tells them apart."""
    fx = build_home(tmp_path)
    from tools.tests.project_reset.conftest import run
    argv = ("apply", "--contract", "1", "--confirm") if mode == "apply" else ("plan", "--contract", "1")
    _, payload = run(fx, *argv)
    assert payload["mode"] == mode


def test_the_folder_count_names_features_not_every_directory(tmp_path):
    """The number is rendered to a person as "N feature folders", so it must mean that. A documents
    folder that is its own repository — the arrangement the requirement calls out by name — carries a
    `.git` directory, and counting it reports one more feature than exists. Nothing in the first pass
    of this suite touched this value, so it shipped wrong and green."""
    docs = tmp_path / "docs"
    (docs / "2026-01-01-alpha").mkdir(parents=True)
    (docs / "2026-01-02-beta").mkdir()
    (docs / ".git").mkdir()
    row = project_reset.documents_row({"docs_root": str(docs), "directory": str(tmp_path / "code")})
    assert row["folders"] == 2
