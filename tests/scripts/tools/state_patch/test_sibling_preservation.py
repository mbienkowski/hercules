"""Integrity of the record around a patch — what must survive, byte for byte: the atomic write
mechanics themselves, and every session or project the patch did not name."""

from __future__ import annotations

import json
import os
import stat

import pytest

from tests.scripts.tools.state_patch.conftest import (
    SIBLING_SESSION, TARGET_SESSION, apply, build_home,
)
from tests.scripts.tools.tool_harness import read_only_directories_are_enforced


def test_the_target_session_is_patched_and_the_sibling_session_survives_unchanged(fx):
    """The worst outcome here is quietly rewriting a session asked to be left alone, so the sibling
    is compared value for value, not merely counted."""
    before_sibling = fx.session(SIBLING_SESSION)
    apply(fx, "--set", "tier=high")
    assert fx.session(TARGET_SESSION)["tier"] == "high"
    assert fx.session(SIBLING_SESSION) == before_sibling


def test_unsetting_a_key_removes_only_that_key(fx):
    apply(fx, "--unset", "current_spec_round")
    session = fx.session(TARGET_SESSION)
    assert "current_spec_round" not in session
    assert session["tier"] == "low" and session["current_phase"] == "build"


def test_every_other_top_level_state_key_survives_a_session_patch(fx):
    before = fx.state()
    apply(fx, "--set", "tier=high")
    after = fx.state()
    assert after["schema_version"] == before["schema_version"]
    assert after["active_session"] == before["active_session"]


def test_setting_a_repository_preserves_another_registered_projects_entry_byte_for_byte(tmp_path, fx):
    """Patching one project's repositories must never reach into another project's registry entry."""
    other_dir = tmp_path / "other-code"
    other_dir.mkdir()
    other = {"directory": str(other_dir), "docs_root": str(other_dir), "state_file": "other.json",
             "repositories": {"svc-x": "/somewhere"}}
    fx = build_home(tmp_path, extra_projects={"other": other})
    svc = tmp_path / "svc-auth"
    svc.mkdir()
    apply(fx, "--set-repository", f"svc-auth={svc}")
    assert fx.registry()["projects"]["other"] == other


def test_setting_a_repository_preserves_a_service_path_already_on_record(tmp_path, fx):
    existing = tmp_path / "svc-existing"
    existing.mkdir()
    fx = build_home(tmp_path, repositories={"svc-existing": str(existing)})
    svc = tmp_path / "svc-auth"
    svc.mkdir()
    apply(fx, "--set-repository", f"svc-auth={svc}")
    repos = fx.entry()["repositories"]
    assert repos["svc-existing"] == str(existing)
    assert repos["svc-auth"] == str(svc)


def test_setting_a_repository_preserves_the_same_projects_other_configurable_fields(tmp_path, fx):
    svc = tmp_path / "svc-auth"
    svc.mkdir()
    before_docs_root = fx.entry()["docs_root"]
    before_state_file = fx.entry()["state_file"]
    apply(fx, "--set-repository", f"svc-auth={svc}")
    assert fx.entry()["docs_root"] == before_docs_root
    assert fx.entry()["state_file"] == before_state_file


def test_a_session_change_and_a_repository_change_in_one_run_both_apply_independently(tmp_path, fx):
    svc = tmp_path / "svc-auth"
    svc.mkdir()
    code, payload = apply(fx, "--set", "tier=high", "--set-repository", f"svc-auth={svc}")
    assert code == 0
    assert payload["verified"] is True
    assert fx.session(TARGET_SESSION)["tier"] == "high"
    assert fx.entry()["repositories"]["svc-auth"] == str(svc)


@pytest.mark.parametrize("raw,expected", [
    ("high", "high"),         # not valid JSON -> the plain string
    ("true", True),           # valid JSON -> the real type
    ("2", 2),
    ('["a","b"]', ["a", "b"]),
])
def test_a_set_value_round_trips_through_the_type_it_actually_names(fx, raw, expected):
    apply(fx, "--set", f"probe={raw}")
    assert fx.session(TARGET_SESSION)["probe"] == expected


def test_the_records_permissions_survive_the_rewrite(fx):
    """A rewrite through a temporary file inherits the umask unless the mode is carried across."""
    os.chmod(fx.state_path, 0o600)
    os.chmod(fx.config_path, 0o640)
    apply(fx, "--set", "tier=high", "--set-repository",
          f"svc-auth={fx.project}")
    assert stat.S_IMODE(fx.state_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(fx.config_path.stat().st_mode) == 0o640


def test_a_record_that_cannot_be_parsed_is_refused_rather_than_half_edited(fx):
    fx.state_path.write_text("{ this is not json")
    code, _ = apply(fx, "--set", "tier=high")
    assert code == 3
    assert fx.state_path.read_text() == "{ this is not json"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
def test_a_record_that_cannot_be_written_leaves_the_original_intact(fx, tmp_path):
    """When the rewrite cannot land, the original must still be there — never a truncated file."""
    if not read_only_directories_are_enforced(tmp_path):
        pytest.skip("this machine writes into read-only directories, so no write here can fail")
    original = fx.state_path.read_text()
    os.chmod(fx.state_path.parent, 0o500)
    try:
        code, _ = apply(fx, "--set", "tier=high")
        assert code == 3
        assert fx.state_path.read_text() == original
    finally:
        os.chmod(fx.state_path.parent, 0o700)


def test_the_reported_json_shape_never_leaks_a_session_field_it_was_not_asked_to_touch(fx):
    """The plan echoes what it read to resolve the session — never the whole record — so a private
    field on the untouched sibling can never surface through a patch of the target."""
    _, payload = apply(fx, "--set", "tier=high")
    assert "a private note" not in json.dumps(payload)
