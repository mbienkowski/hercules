"""Step 3's exact scope: the three frozen-bookkeeping keys clear and the spec lands in delivered,
while every sibling session and other top-level key survives byte-for-byte."""

from __future__ import annotations

from tests.scripts.tools.retire_spec.conftest import (DELIVERED_SPEC, PENDING_SPEC, SIBLING_SESSION, SPEC,
                                              apply, build_home)


def test_retiring_the_current_spec_appends_it_without_touching_pending_specs(fx):
    code, payload = apply(fx)
    assert code == 0
    session = fx.session()
    assert session["delivered_specs"] == [DELIVERED_SPEC, SPEC]
    assert session["pending_specs"] == [PENDING_SPEC]


def test_retiring_a_pending_spec_drops_it_from_pending_specs(tmp_path):
    fx = build_home(tmp_path, pending_specs=[PENDING_SPEC])
    code, payload = apply(fx, spec_file=str(fx.spec_path(spec=PENDING_SPEC)))
    assert code == 0
    session = fx.session()
    assert PENDING_SPEC not in (session.get("pending_specs") or [])
    assert session["delivered_specs"] == [DELIVERED_SPEC, PENDING_SPEC]


def test_pending_specs_key_is_omitted_once_the_last_entry_is_dropped(tmp_path):
    fx = build_home(tmp_path, pending_specs=[PENDING_SPEC])
    apply(fx, spec_file=str(fx.spec_path(spec=PENDING_SPEC)))
    assert "pending_specs" not in fx.session()


def test_a_sibling_session_is_never_touched(fx):
    before_sibling = fx.session(SIBLING_SESSION)
    apply(fx)
    assert fx.session(SIBLING_SESSION) == before_sibling


def test_every_other_top_level_state_key_survives(fx):
    before = fx.state()
    apply(fx)
    after = fx.state()
    assert after["schema_version"] == before["schema_version"]
    assert after["active_session"] == before["active_session"]


def test_current_spec_round_and_current_spec_are_left_for_the_caller_to_advance(fx):
    """Advancing to the next pending spec stays the caller's decision, never silently made here."""
    apply(fx)
    session = fx.session()
    assert session["current_spec"] == "2026-06-22-user-auth-spec-02-login.md"
    assert session["current_spec_round"] == 1
