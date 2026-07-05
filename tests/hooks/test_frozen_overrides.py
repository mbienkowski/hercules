"""Frozen-tests hook — user-granted frozen_override and the frozen_hook opt-out."""

from __future__ import annotations

import json
import os
import sys
import pytest

from tests.hooks.conftest import _HOOKS_DIR, _grant, _payload, _setup, main


def test_override_allows_edit_to_named_frozen_file_in_matching_round(tmp_path):
    """The user's explicit grant unblocks the named file, in the same round, no ceremony."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=["tests/test_login.py"])
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_override_with_stale_round_still_blocks(tmp_path):
    """Round advance is the override's machine expiry — a stale grant never re-validates."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=["tests/test_login.py"], round_=2)  # session round is 1
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_override_for_another_spec_still_blocks(tmp_path):
    """A grant left over from a different spec (round counters reset at retire) never leaks."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=["tests/test_login.py"], spec="spec-01-schema.md")
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_override_scopes_to_named_files_only(tmp_path):
    """A grant for file A must never disarm frozen file B — same state, both directions."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, frozen=("tests/test_a.py", "tests/test_b.py"))
    _grant(tmp_path, files=["tests/test_a.py"])
    assert main(_payload(project, "tests/test_b.py"), home=tmp_path) == 2
    assert main(_payload(project, "tests/test_a.py"), home=tmp_path) == 0


def test_override_covers_multiple_granted_files(tmp_path):
    """Grants accumulate across the files list — the first entry works, not just the last."""
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
def test_malformed_override_still_blocks(tmp_path, bad):
    """The override fails CLOSED: anything malformed leaves the block standing."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=[], extra=bad)
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_override_junk_entries_do_not_poison_a_valid_grant(tmp_path):
    """Junk file entries are skipped, never fatal — the valid entry in the same grant works."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=[123, "tests/test_login.py"])
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


def test_override_round_null_on_roundless_session_blocks(tmp_path):
    """None == None must never validate — the grant requires an explicit integer round."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    state = json.loads((hh / "state" / "proj.json").read_text())
    del state["sessions"]["s1"]["current_spec_round"]
    state["sessions"]["s1"]["frozen_override"] = {
        "files": ["tests/test_login.py"], "spec": "spec-02-login.md", "round": None}
    (hh / "state" / "proj.json").write_text(json.dumps(state))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_override_helper_fails_closed_when_candidates_raise(tmp_path, monkeypatch):
    """A raising resolver inside the override parser must block, never disarm the guard."""
    import frozen_tests as ft

    project = tmp_path / "proj"
    _setup(tmp_path, project)

    class _Boom(dict):
        def get(self, *_a, **_k):
            raise RuntimeError("session exploded")

    assert ft._override_allows(_Boom(), [], "x") is False


def test_override_end_to_end_as_a_script(tmp_path):
    """Real deployment shape: with a recorded grant the script exits 0 on the granted file."""
    import subprocess

    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=["tests/test_login.py"])
    env = {**os.environ, "HOME": str(tmp_path)}
    run = subprocess.run(
        [sys.executable, str(_HOOKS_DIR / "frozen_tests.py")],
        input=_payload(project, "tests/test_login.py"), capture_output=True, text=True, env=env,
    )
    assert run.returncode == 0


def test_frozen_hook_off_opt_out_allows_everything(tmp_path):
    """The per-project opt-out (`frozen_hook: "off"`) switches to prompt-only discipline."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    cfg["projects"]["proj"]["frozen_hook"] = "off"
    (hh / "config.json").write_text(json.dumps(cfg))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 0


@pytest.mark.parametrize("value", ["on", "OFF", "", None, True, 0])
def test_frozen_hook_other_values_keep_the_guard_armed(tmp_path, value):
    """Only the literal "off" disarms; absent or junk values keep the block."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    hh = tmp_path / ".hercules"
    cfg = json.loads((hh / "config.json").read_text())
    if value is not None:
        cfg["projects"]["proj"]["frozen_hook"] = value
    (hh / "config.json").write_text(json.dumps(cfg))
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2


def test_override_without_the_quoted_grant_fails_closed(tmp_path):
    """The override contract is files + spec + round + the user's quoted words; an override
    missing or blanking the quoted grant is malformed and must not unblock."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    for bad in ({"files": ["tests/test_login.py"], "spec": "spec-02-login.md", "round": 1},
                {"files": ["tests/test_login.py"], "spec": "spec-02-login.md", "round": 1,
                 "reason": ""},
                {"files": ["tests/test_login.py"], "spec": "spec-02-login.md", "round": 1,
                 "reason": "   "}):
        _grant(tmp_path, files=[], extra=bad)
        assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2, bad


def test_override_files_must_be_a_list(tmp_path):
    """A string (or any non-list) files value is malformed — iterating a string would
    'allow' per-character garbage; the guard must fail closed instead."""
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    _grant(tmp_path, files=[], extra={"files": "tests/test_login.py",
                                      "spec": "spec-02-login.md", "round": 1,
                                      "reason": "user: 'fix it'"})
    assert main(_payload(project, "tests/test_login.py"), home=tmp_path) == 2
