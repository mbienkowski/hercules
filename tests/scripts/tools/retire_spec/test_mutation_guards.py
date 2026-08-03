"""A lying `verified: true`, a dropped sibling, an unclassified crash: the CLI only ever sees the
tool's own report, never the raw file, so each is driven against the helper directly."""

from __future__ import annotations

import json

import pytest

from tests.scripts.tools.retire_spec.conftest import SPEC, apply, build_home

import retire_spec  # noqa: E402 — conftest puts src/scripts/tools on the path


def _write_state(path, sessions, active="a"):
    path.write_text(json.dumps({"schema_version": 1, "active_session": active,
                                "sessions": sessions}))


def test_verify_retired_session_reports_true_on_a_real_match(tmp_path):
    path = tmp_path / "state.json"
    _write_state(path, {"a": {"pending_specs": [], "delivered_specs": [SPEC]}, "b": {"tier": "low"}})
    before = {"schema_version": 1, "active_session": "a",
             "sessions": {"a": {"pending_specs": [SPEC], "delivered_specs": []},
                          "b": {"tier": "low"}}}
    assert retire_spec.verify_retired_session(path, "a", SPEC, before) is True


@pytest.mark.parametrize("stored,expected", [
    ({"a": {"pending_specs": [], "delivered_specs": [], "frozen_test_files": ["x"]},
     "b": {"tier": "low"}}, False),                                            # a frozen key survived
    ({"a": {"pending_specs": [SPEC], "delivered_specs": [SPEC]}, "b": {"tier": "low"}}, False),
    ({"a": {"pending_specs": [], "delivered_specs": []}, "b": {"tier": "low"}}, False),  # never delivered
    ({"a": {"pending_specs": [], "delivered_specs": [SPEC]}, "b": {"tier": "altered"}}, False),
], ids=["frozen_key_survived", "still_pending", "never_delivered", "sibling_altered"])
def test_verify_retired_session_reports_false_on_every_way_a_patch_can_lie(tmp_path, stored, expected):
    path = tmp_path / "state.json"
    _write_state(path, stored)
    before = {"schema_version": 1, "active_session": "a",
             "sessions": {"a": {"pending_specs": [SPEC], "delivered_specs": []},
                          "b": {"tier": "low"}}}
    assert retire_spec.verify_retired_session(path, "a", SPEC, before) is expected


def test_an_other_top_level_key_moving_also_fails_verification(tmp_path):
    path = tmp_path / "state.json"
    _write_state(path, {"a": {"pending_specs": [], "delivered_specs": [SPEC]}}, active="different")
    before = {"schema_version": 1, "active_session": "a",
             "sessions": {"a": {"pending_specs": [SPEC], "delivered_specs": []}}}
    assert retire_spec.verify_retired_session(path, "a", SPEC, before) is False


def test_an_unclassified_failure_during_apply_changes_nothing_and_is_reported(fx, monkeypatch):
    """The catch-all exists so an unanticipated error resolves to doing nothing; nothing in the
    normal flow raises one, so it could be narrowed to an unreachable type and no test would object."""
    monkeypatch.setattr(retire_spec, "delete_spec_file",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("unexpected")))
    before = fx.state_path.read_text()
    code, payload = apply(fx)
    assert code == 3
    assert fx.state_path.read_text() == before
    assert payload["message"].strip()


def test_a_verification_that_returns_false_escalates_to_the_internal_exit_code(fx, monkeypatch):
    """`verified: false` is never reported alongside a plain success code — the caller must be able
    to tell a proven retire from an unproven one by the exit code alone."""
    monkeypatch.setattr(retire_spec, "verify_retired_session", lambda *a, **kw: False)
    code, payload = apply(fx)
    assert code == 3
    assert payload["verified"] is False


def test_a_git_rm_that_refuses_is_reported_as_internal_and_changes_nothing(tmp_path):
    """A real git refusal (uncommitted local modifications) — not merely "not tracked" — is a
    distinct failure from an untracked file, and must halt before state is ever touched."""
    fx = build_home(tmp_path, git_tracked=True)
    fx.spec_path().write_text("locally modified, never staged\n", encoding="utf-8")
    before_state = fx.state_path.read_text()

    code, payload = apply(fx)

    assert code == 3
    assert payload["error"] == "internal"
    assert fx.spec_path().exists()
    assert fx.state_path.read_text() == before_state
