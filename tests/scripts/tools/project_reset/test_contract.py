"""The contract the command depends on: one output shape, one exit-code meaning, one version — and
the harness's own precondition, since everything else here asserts against a fixture tree."""

from __future__ import annotations

import json

import pytest

from tests.scripts.tools.project_reset.conftest import plan, run


def test_the_fixture_tree_is_real_and_writable(fx):
    """The guard on every other test here — an empty or read-only fixture would make the whole suite green while proving nothing."""
    assert fx.config_path.is_file() and fx.state_path.is_file()
    assert fx.docs.is_dir() and fx.project.is_dir()
    assert json.loads(fx.config_path.read_text())["projects"]
    (fx.docs / "probe.txt").write_text("writable\n")


def test_a_version_the_tool_does_not_understand_is_refused(fx):
    """A command from an older plugin must not be answered with a shape it cannot read."""
    code, payload = run(fx, "plan", "--contract", "99")
    assert code == 2
    assert payload["message"].strip()


def test_the_current_version_is_accepted(fx):
    """The companion to the check above, so the refusal proves something."""
    code, _ = plan(fx)
    assert code == 0


def test_every_reply_states_the_version_it_was_written_against(fx):
    """The command reads this to know it is talking to the tool it expects."""
    _, payload = plan(fx)
    assert payload["contract"] == 1


@pytest.mark.parametrize("argv,expected_code", [
    (("plan", "--contract", "1"), 0),
    (("plan", "--contract", "99"), 2),
    (("apply", "--contract", "1", "--documents"), 3),
])
def test_each_outcome_carries_its_own_exit_code_and_replies_in_the_one_shape(fx, argv, expected_code):
    """The command decides what to do next from the code alone, so the codes must not collide — and
    every outcome, including a refusal, replies in the same shape rather than a stack trace."""
    code, payload = run(fx, *argv)
    assert code == expected_code
    assert payload["contract"] == 1 and payload["mode"] in ("plan", "apply")


def test_an_unreadable_registry_refuses_instead_of_proceeding(fx):
    """The record is how the tool knows what it may touch. Without it, it may touch nothing."""
    fx.config_path.write_text("{ broken")
    code, payload = plan(fx)
    assert code in (4, 5)
    assert payload["message"].strip()
