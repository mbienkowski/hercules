"""The contract the command depends on: one output shape, one exit-code meaning, one version.

Also the harness's own precondition. Everything else in this package asserts against a fixture
tree; if that tree were empty or unwritable, those assertions would pass vacuously.
"""

from __future__ import annotations

import json

import pytest

from tools.tests.project_reset.conftest import build_home, plan, run


def test_the_fixture_tree_is_real_and_writable(tmp_path):
    """The guard on every other test in this package. An empty or read-only fixture would make the
    whole suite green while proving nothing."""
    fx = build_home(tmp_path)
    assert fx.config_path.is_file() and fx.state_path.is_file()
    assert fx.docs.is_dir() and fx.project.is_dir()
    assert json.loads(fx.config_path.read_text())["projects"]
    (fx.docs / "probe.txt").write_text("writable\n")


def test_a_version_the_tool_does_not_understand_is_refused(tmp_path):
    """A command from an older plugin must not be answered with a shape it cannot read."""
    fx = build_home(tmp_path)
    code, payload = run(fx, "plan", "--contract", "99")
    assert code == 2
    assert payload["message"].strip()


def test_the_current_version_is_accepted(tmp_path):
    """The companion to the check above, so the refusal proves something."""
    fx = build_home(tmp_path)
    code, _ = plan(fx)
    assert code == 0


def test_every_reply_states_the_version_it_was_written_against(tmp_path):
    """The command reads this to know it is talking to the tool it expects."""
    fx = build_home(tmp_path)
    _, payload = plan(fx)
    assert payload["contract"] == 1


@pytest.mark.parametrize("argv,expected", [
    (("plan", "--contract", "1"), 0),
    (("plan", "--contract", "99"), 2),
    (("apply", "--contract", "1", "--documents"), 3),
])
def test_each_outcome_carries_its_own_exit_code(tmp_path, argv, expected):
    """The command decides what to do next from the code alone, so the codes must not collide."""
    fx = build_home(tmp_path)
    code, _ = run(fx, *argv)
    assert code == expected


@pytest.mark.parametrize("argv", [
    ("plan", "--contract", "1"),
    ("plan", "--contract", "99"),
    ("apply", "--contract", "1", "--documents"),
])
def test_every_outcome_replies_in_the_one_shape(tmp_path, argv):
    """Including refusals. A command that has to guess whether it received data or a stack trace
    will eventually guess wrong at the worst moment."""
    fx = build_home(tmp_path)
    _, payload = run(fx, *argv)
    assert payload["contract"] == 1 and payload["mode"] in ("plan", "apply")


def test_an_unreadable_registry_refuses_instead_of_proceeding(tmp_path):
    """The record is how the tool knows what it may touch. Without it, it may touch nothing."""
    fx = build_home(tmp_path)
    fx.config_path.write_text("{ broken")
    code, payload = plan(fx)
    assert code in (4, 5)
    assert payload["message"].strip()
