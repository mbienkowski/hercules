"""The contract the command depends on: one output shape, one exit-code meaning per outcome — and
the harness's own precondition, since everything else here asserts against a fixture tree."""

from __future__ import annotations

import json

import pytest

from tests.scripts.tools.state_patch.conftest import apply, plan, run


def test_the_fixture_tree_is_real_and_writable(fx):
    """The guard on every other test here — an empty or read-only fixture would make the whole
    suite green while proving nothing."""
    assert fx.config_path.is_file() and fx.state_path.is_file()
    assert json.loads(fx.config_path.read_text())["projects"]
    (fx.project / "probe.txt").write_text("writable\n")


@pytest.mark.parametrize("mode", ["plan", "apply"])
def test_every_outcome_replies_in_the_one_shape(fx, mode):
    """The command decides what to do next from the code alone, so every outcome, including a
    refusal, replies in the same JSON shape rather than a stack trace."""
    if mode == "plan":
        _, payload = plan(fx, "--set", "tier=high")
    else:
        _, payload = apply(fx, "--set", "tier=high")
    assert isinstance(payload, dict)
    assert payload["mode"] == mode


def test_a_plan_call_reports_exit_zero_and_the_intended_change(fx):
    code, payload = plan(fx, "--set", "tier=high")
    assert code == 0
    assert payload["mode"] == "plan"
    assert payload["changes"]["set"] == {"tier": "high"}


def test_an_apply_call_without_confirm_is_refused_with_its_own_code(fx):
    """Confirmation is the whole gate. Without it the tool refuses, distinguishably from a safety
    refusal, so the command can tell the two apart."""
    code, payload = apply(fx, "--set", "tier=high", confirm=False)
    assert code == 2
    assert payload["error"] == "unconfirmed"
    assert payload["message"].strip()
    assert fx.session()["tier"] != "high"


def test_an_apply_call_with_confirm_reports_exit_zero_and_what_it_applied(fx):
    code, payload = apply(fx, "--set", "tier=high")
    assert code == 0
    assert payload["mode"] == "apply"
    assert payload["applied"]["set"] == {"tier": "high"}
    assert payload["verified"] is True


def test_arguments_the_parser_cannot_understand_are_refused_not_crashed(fx):
    """A missing required flag must not raise past `main` — it is exactly the kind of malformed
    call a real caller can make."""
    code, payload = run(fx, "plan", "--session-id", "2026-01-03-beta", "--set", "tier=high")
    assert code == 3
    assert payload["error"] == "usage"
