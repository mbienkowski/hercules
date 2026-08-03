"""Step 2's four outcomes: `git rm` when tracked, a plain unlink when not, `"kept"` under
`--keep-specs`, and `"already_absent"` for a retire resumed after an interrupted delete."""

from __future__ import annotations

import subprocess

from tests.scripts.tools.retire_spec.conftest import apply, build_home


def test_a_git_tracked_spec_is_removed_with_git_rm(tmp_path):
    fx = build_home(tmp_path, git_tracked=True)
    code, payload = apply(fx)
    assert code == 0
    assert payload["spec"]["deletion"] == "git_rm"
    assert not fx.spec_path().exists()
    listed = subprocess.run(["git", "-C", str(fx.docs), "ls-files"], capture_output=True, text=True)
    assert fx.spec_path().name not in listed.stdout, "git rm must stage the removal, not just unlink"


def test_an_untracked_spec_is_removed_with_a_plain_unlink(tmp_path):
    fx = build_home(tmp_path, git_tracked=False)
    code, payload = apply(fx)
    assert code == 0
    assert payload["spec"]["deletion"] == "unlink"
    assert not fx.spec_path().exists()


def test_keep_specs_skips_deletion_but_still_patches_state(tmp_path):
    fx = build_home(tmp_path, keep_specs=True)
    code, payload = apply(fx, "--keep-specs")
    assert code == 0
    assert payload["spec"]["deletion"] == "kept"
    assert fx.spec_path().exists()
    session = fx.session()
    assert "frozen_test_files" not in session


def test_a_spec_already_deleted_before_this_run_is_treated_as_satisfied(tmp_path):
    """A retire resumed after an interrupted delete (build.md's own resume case) finds the file
    already gone and still completes the state patch."""
    fx = build_home(tmp_path, git_tracked=False)
    fx.spec_path().unlink()
    code, payload = apply(fx)
    assert code == 0
    assert payload["spec"]["deletion"] == "already_absent"
    session = fx.session()
    assert "frozen_test_files" not in session
