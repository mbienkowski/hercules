"""Frozen-tests hook — user-granted frozen_override and the frozen_hook opt-out."""

from __future__ import annotations

import json
import pytest

from tests.hooks.conftest import _grant, _payload, _setup, main


def test_override_allows_edit_to_named_frozen_file_in_matching_round(tmp_path):
    """When the user has explicitly approved editing a specific frozen file during the
    current round, that edit is allowed instead of blocked -- so a human-approved
    exception goes through without needing to formally unfreeze the file first."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=["tests/test_login.py"])
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_editing_a_frozen_file_stays_blocked_when_the_grant_round_does_not_match(tmp_path):
    """A permission grant recorded for a different round than the one currently in
    progress no longer applies -- the frozen file stays protected until the user gives
    a fresh approval that matches the current round."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=["tests/test_login.py"], round_=2)  # session round is 1
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_editing_a_frozen_file_stays_blocked_when_the_grant_was_for_a_different_spec(tmp_path):
    """A permission grant left over from working on a different spec must not carry
    forward and silently unlock files in the current one -- each spec's approvals are
    scoped to that spec only, so switching specs can't be used to sneak past a freeze."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=["tests/test_login.py"], spec="spec-01-schema.md")
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_a_grant_for_one_file_does_not_unblock_a_different_frozen_file(tmp_path):
    """Approving edits to one specific frozen file must not accidentally open up editing
    on a different frozen file -- each grant covers only the exact files the user named,
    checked in both directions."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_a.py", "tests/test_b.py"))
    _grant(tmp_path, files=["tests/test_a.py"])
    assert main(_payload(project, "tests/test_b.py"), home=tmp_path) == 2
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 0


def test_a_single_grant_can_unblock_several_named_files_at_once(tmp_path):
    """When the user approves edits to a list of frozen files in one grant, every file
    in that list becomes editable -- not just the first one listed or only the last."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_a.py", "tests/test_b.py"))
    _grant(tmp_path, files=["tests/test_a.py", "tests/test_b.py"])
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 0
    assert main(_payload(project, "tests/test_b.py"), home=tmp_path) == 0


@pytest.mark.parametrize("bad", [
    "yes",                                              # not a dict
    {"files": "tests/test_login.py", "round": 1, "spec": "spec-02-login.md"},  # files not a list
    {"round": 1, "spec": "spec-02-login.md"},           # files missing
    {"files": ["tests/test_login.py"], "spec": "spec-02-login.md"},            # round missing
    {"files": [], "round": 1, "spec": "spec-02-login.md"},                     # empty files
    {"files": [None, 123], "round": 1, "spec": "spec-02-login.md"},            # junk entries
    {"files": ["tests/test_login.py"], "round": "1", "spec": "spec-02-login.md"},  # str round
])
def test_a_broken_or_incomplete_grant_leaves_the_file_protected(tmp_path, bad):
    """If a recorded permission grant is missing required information, has the wrong
    data types, or is otherwise malformed, the frozen file must stay protected rather
    than being treated as approved -- broken data should never accidentally unlock a
    protection meant to require a real, explicit approval."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=[], extra=bad)
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_invalid_entries_in_a_grants_file_list_do_not_block_the_valid_ones(tmp_path):
    """A grant's list of approved files may contain a stray invalid entry alongside a
    correctly named file. Editing the correctly named file must still be allowed -- one
    piece of bad data in the list shouldn't disable an otherwise valid approval."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=[123, "tests/test_login.py"])
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_a_missing_round_number_never_matches_a_grant_with_no_round_recorded(tmp_path):
    """If the current work session has no round number set, and the stored grant also
    has no round number set, those two 'unset' values must not be treated as a match --
    an approval always requires an explicit, specific round to actually take effect."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    del state["sessions"]["s1"]["current_spec_round"]
    state["sessions"]["s1"]["frozen_override"] = {
        "files": ["tests/test_login.py"], "spec": "spec-02-login.md", "round": None}
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_an_internal_error_while_checking_a_grant_still_leaves_the_file_blocked(tmp_path, monkeypatch):
    """If something goes wrong internally while checking whether a grant applies, the
    file must remain protected rather than being let through by accident -- an error in
    the approval check must never be mistaken for an approval."""
    import frozen_tests as ft

    project = tmp_path / "proj"
    _setup(tmp_path, project)

    class _Boom(dict):
        def get(self, *_a, **_k):
            raise RuntimeError("session exploded")

    assert ft._override_allows(_Boom(), [], "x") is False


def test_turning_off_the_frozen_file_guard_for_a_project_allows_all_edits(tmp_path):
    """A project can opt out of automatic frozen-file protection by setting its guard to
    "off", relying on prompt discipline instead. Once that opt-out is set, edits to
    frozen files are no longer blocked."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"]["proj"]["frozen_hook"] = "off"
    (hh / "config.json").write_text(json.dumps(cfg))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


@pytest.mark.parametrize("value", ["on", "OFF", "", None, True, 0])
def test_only_the_exact_off_setting_disables_the_frozen_file_guard(tmp_path, value):
    """Anything other than the exact setting "off" -- including different
    capitalization, a blank value, or the setting being missing entirely -- must leave
    the frozen-file guard active, so a typo or misconfiguration can't accidentally turn
    off protection."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    if value is not None:
        cfg["projects"]["proj"]["frozen_hook"] = value
    (hh / "config.json").write_text(json.dumps(cfg))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_a_grant_without_the_users_own_words_of_approval_fails_closed(tmp_path):
    """A valid grant must include the user's own quoted reason for approving the edit.
    If that reason is missing or blank, the grant is incomplete and the frozen file
    stays protected -- this stops an edit from being waved through without the user
    having actually said something to approve it."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    for bad in ({"files": ["tests/test_login.py"], "spec": "spec-02-login.md", "round": 1},
                {"files": ["tests/test_login.py"], "spec": "spec-02-login.md", "round": 1,
                 "reason": ""},
                {"files": ["tests/test_login.py"], "spec": "spec-02-login.md", "round": 1,
                 "reason": "   "}):
        _grant(tmp_path, files=[], extra=bad)
        assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2, bad


def test_a_grant_with_a_single_file_name_instead_of_a_list_fails_closed(tmp_path):
    """A grant's list of approved files must actually be a list. If a single line of
    text is given instead, treating it as a list of file names could accidentally match
    unrelated files by their individual letters -- the guard rejects this malformed
    grant and keeps the file protected instead of following it literally."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=[], extra={"files": "tests/test_login.py",
                                      "spec": "spec-02-login.md", "round": 1,
                                      "reason": "user: 'fix it'"})
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2
