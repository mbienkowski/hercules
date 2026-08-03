"""What each mode promises: `plan` only looks, `apply` only acts on a stated yes."""

from __future__ import annotations

from tests.scripts.tools.state_patch.conftest import TARGET_SESSION, apply, plan


def test_planning_changes_nothing_on_disk(fx):
    """A person may look as many times as they like. Looking is not a step toward patching."""
    before_state = fx.state_path.read_text()
    before_config = fx.config_path.read_text()
    plan(fx, "--set", "tier=high", "--unset", "current_spec_round")
    assert fx.state_path.read_text() == before_state
    assert fx.config_path.read_text() == before_config


def test_planning_reports_exactly_the_change_requested_and_nothing_more(fx):
    """The confirmation screen is rendered from this and nothing else, so it must be complete and
    exact — no field the request did not name."""
    _, payload = plan(fx, "--set", "tier=high", "--unset", "current_spec_round")
    assert payload["changes"]["set"] == {"tier": "high"}
    assert payload["changes"]["unset"] == ["current_spec_round"]
    assert payload["changes"]["set_repository"] == {}


def test_planning_names_the_resolved_project_and_session(fx):
    _, payload = plan(fx, "--set", "tier=high")
    assert payload["project"]["slug"] == fx.slug
    assert payload["session"]["id"] == TARGET_SESSION
    assert payload["session"]["current_phase"] == "build"


def test_applying_without_a_stated_yes_changes_nothing(fx):
    """Confirmation is the whole gate. Without it the tool refuses, and nothing it would have
    changed moved."""
    before = fx.state_path.read_text()
    code, payload = apply(fx, "--set", "tier=high", confirm=False)
    assert code == 2
    assert fx.state_path.read_text() == before
    assert payload["error"]


def test_applying_with_a_stated_yes_writes_exactly_what_was_planned(fx):
    _, planned = plan(fx, "--set", "tier=high", "--unset", "current_spec_round")
    code, applied = apply(fx, "--set", "tier=high", "--unset", "current_spec_round")
    assert code == 0
    assert applied["applied"] == planned["changes"]
    assert fx.session(TARGET_SESSION)["tier"] == "high"
    assert "current_spec_round" not in fx.session(TARGET_SESSION)


def test_the_reply_names_its_own_mode_so_a_caller_cannot_confuse_the_two(fx):
    """A confirmation rendered from an apply reply, or a result rendered from a plan reply, would
    both look plausible. The mode is what tells them apart."""
    _, plan_payload = plan(fx, "--set", "tier=high")
    _, apply_payload = apply(fx, "--set", "tier=high")
    assert plan_payload["mode"] == "plan"
    assert apply_payload["mode"] == "apply"
