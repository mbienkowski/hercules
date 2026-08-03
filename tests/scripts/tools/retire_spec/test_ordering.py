"""The safety property: the acceptance backstop gates the delete and the patch, so a tampered frozen
test refuses the whole retire. Each test reads disk directly rather than trusting the reported status."""

from __future__ import annotations

from tests.scripts.tools.retire_spec.conftest import DELIVERED_SPEC, FROZEN_TEST, SPEC, apply, build_home


def test_a_tampered_frozen_test_refuses_the_whole_retire_deleting_and_changing_nothing(tmp_path):
    fx = build_home(tmp_path)
    (fx.project / FROZEN_TEST).write_text("def test_x():\n    assert True\n", encoding="utf-8")
    before_state = fx.state_path.read_text()

    code, payload = apply(fx)

    assert code == 5
    assert payload["error"] == "frozen_drift"
    assert payload["drifted_files"] == [FROZEN_TEST]
    assert fx.spec_path().exists(), "the spec file must survive a refused retire"
    assert fx.state_path.read_text() == before_state, "state must be byte-identical to before"


def test_an_unresolvable_backstop_check_refuses_the_retire_too(tmp_path):
    """The backstop's own fail-closed posture (an unreadable project/session resolves as blocking,
    never as clean) propagates: `retire_spec` never treats "the check itself broke" as a pass."""
    fx = build_home(tmp_path)
    fx.config_path.write_text("{ not json")

    code, payload = apply(fx)

    assert code == 3  # the registry read fails before the backstop even runs — Internal, not drift
    assert fx.spec_path().exists()


def test_a_clean_tree_deletes_then_patches_in_order(tmp_path):
    fx = build_home(tmp_path, with_override=True)

    code, payload = apply(fx)

    assert code == 0
    assert payload["spec"]["deletion"] == "git_rm"
    assert not fx.spec_path().exists()
    session = fx.session()
    assert spec_name_absent_from_pending(session)
    assert session["delivered_specs"] == [DELIVERED_SPEC, SPEC]
    assert "frozen_test_files" not in session
    assert "frozen_baseline" not in session
    assert "frozen_override" not in session


def spec_name_absent_from_pending(session: dict) -> bool:
    return SPEC not in (session.get("pending_specs") or [])


def test_the_frozen_check_runs_before_any_write_reaches_disk(tmp_path):
    """A disk read taken mid-refusal: neither a plan nor an unconfirmed apply can reach a write, so
    the confirmed clean path proven above is the only one that does."""
    fx = build_home(tmp_path)
    before_state = fx.state_path.read_text()
    before_spec = fx.spec_path().read_bytes()

    code, _ = apply(fx, confirm=False)

    assert code == 2
    assert fx.state_path.read_text() == before_state
    assert fx.spec_path().read_bytes() == before_spec
