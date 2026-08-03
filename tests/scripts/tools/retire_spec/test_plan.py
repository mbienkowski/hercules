"""`plan` runs the same backstop as `apply` (useful preview, since hashing is a read) but writes
nothing under any outcome — clean, tampered, or a spec that would only be kept."""

from __future__ import annotations

from tests.scripts.tools.retire_spec.conftest import FROZEN_TEST, SPEC, build_home, plan


def test_plan_on_a_clean_tree_reports_no_drift_and_the_would_retire_shape(fx):
    code, payload = plan(fx)
    assert code == 0
    assert payload["frozen_check"]["drifted_files"] == []
    assert payload["spec"]["name"] == SPEC
    assert payload["would_retire"]["delete_spec_file"] is True
    assert payload["would_retire"]["appends_to_delivered_specs"] == SPEC


def test_plan_surfaces_drift_without_refusing_or_writing(tmp_path):
    fx = build_home(tmp_path)
    (fx.project / FROZEN_TEST).write_text("def test_x():\n    assert True\n", encoding="utf-8")
    before_state = fx.state_path.read_text()

    code, payload = plan(fx)

    assert code == 0  # plan reports; it never refuses — apply is where drift blocks
    assert payload["frozen_check"]["drifted_files"] == [FROZEN_TEST]
    assert fx.spec_path().exists()
    assert fx.state_path.read_text() == before_state


def test_keep_specs_is_reflected_in_the_plan_shape(fx):
    code, payload = plan(fx, "--keep-specs")
    assert code == 0
    assert payload["spec"]["keep_specs"] is True
    assert payload["would_retire"]["delete_spec_file"] is False
