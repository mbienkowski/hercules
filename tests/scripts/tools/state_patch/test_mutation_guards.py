"""A lying `verified: true` or a dropped sibling is invisible from the command line, which only sees
the tool's own report — so the verification helpers are driven directly."""

from __future__ import annotations

import json

import pytest

from tests.scripts.tools.state_patch.conftest import apply

import state_patch  # noqa: E402 — conftest puts src/scripts/tools on the path


def test_verify_session_patch_reports_true_on_a_real_match(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"schema_version": 1, "active_session": "a",
                                "sessions": {"a": {"tier": "high"}, "b": {"tier": "low"}}}))
    before = {"schema_version": 1, "active_session": "a",
             "sessions": {"a": {"tier": "low"}, "b": {"tier": "low"}}}
    changes = {"set": {"tier": "high"}, "unset": [], "set_repository": {}}
    assert state_patch.verify_session_patch(path, "a", changes, before) is True


@pytest.mark.parametrize("stored,expected", [
    ({"sessions": {"a": {"tier": "low"}, "b": {"tier": "low"}}}, False),   # the set key never landed
    ({"sessions": {"a": {"tier": "high"}, "b": {"tier": "altered"}}}, False),  # a sibling moved
    ({"active_session": "different", "sessions": {"a": {"tier": "high"}, "b": {"tier": "low"}}}, False),
], ids=["set_key_missing", "sibling_altered", "other_top_level_key_altered"])
def test_verify_session_patch_reports_false_on_every_way_a_patch_can_lie(tmp_path, stored, expected):
    path = tmp_path / "state.json"
    payload = {"schema_version": 1, "active_session": "a", "sessions": {}}
    payload.update(stored)
    path.write_text(json.dumps(payload))
    before = {"schema_version": 1, "active_session": "a",
             "sessions": {"a": {"tier": "low"}, "b": {"tier": "low"}}}
    changes = {"set": {"tier": "high"}, "unset": [], "set_repository": {}}
    assert state_patch.verify_session_patch(path, "a", changes, before) is expected


def test_verify_repository_patch_reports_true_on_a_real_match():
    before_projects = {"p": {"directory": "/d", "repositories": {"x": "/x"}}, "other": {"a": 1}}
    after_projects = {"p": {"directory": "/d", "repositories": {"x": "/x", "y": "/y"}}, "other": {"a": 1}}
    assert state_patch.verify_repository_patch(after_projects, "p", {"y": "/y"}, before_projects) is True


@pytest.mark.parametrize("mutate", [
    lambda after: after["p"]["repositories"].pop("y"),          # the set path never landed
    lambda after: after["p"].__setitem__("directory", "/moved"),  # an untouched field moved
    lambda after: after["p"]["repositories"].pop("x"),           # a pre-existing path was dropped
    lambda after: after.pop("other"),                             # another project vanished
], ids=["set_path_missing", "other_field_altered", "existing_path_dropped", "other_project_dropped"])
def test_verify_repository_patch_reports_false_on_every_way_a_patch_can_lie(mutate):
    before_projects = {"p": {"directory": "/d", "repositories": {"x": "/x"}}, "other": {"a": 1}}
    after_projects = {"p": {"directory": "/d", "repositories": {"x": "/x", "y": "/y"}}, "other": {"a": 1}}
    mutate(after_projects)
    assert state_patch.verify_repository_patch(after_projects, "p", {"y": "/y"}, before_projects) is False


def test_an_unclassified_failure_during_apply_changes_nothing_and_is_reported(fx, monkeypatch):
    """The catch-all exists so an unanticipated error resolves to doing nothing; nothing in the
    normal flow raises one, so it could be narrowed to an unreachable type and no test would object."""
    monkeypatch.setattr(state_patch, "atomic_write_json",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("unexpected")))
    before = fx.state_path.read_text()
    code, payload = apply(fx, "--set", "tier=high")
    assert code == 3
    assert fx.state_path.read_text() == before
    assert payload["message"].strip()


def test_a_verification_that_returns_false_escalates_to_the_internal_exit_code(fx, monkeypatch):
    """`verified: false` is never reported alongside a plain success code — the caller must be able
    to tell a proven patch from an unproven one by the exit code alone."""
    monkeypatch.setattr(state_patch, "verify_session_patch", lambda *a, **kw: False)
    code, payload = apply(fx, "--set", "tier=high")
    assert code == 3
    assert payload["verified"] is False
