"""`repair plan|apply` — fail closed, and honest about what a registry can recover: a stale
`state_file` pointer is fixed, but an orphan with no `directory` is reported, never fabricated."""

from __future__ import annotations

import json

from tests.scripts.tools.registry_sync.conftest import SLUG, build_home, repair_apply, repair_plan


def test_a_stale_state_file_pointer_is_named_in_the_plan(fx):
    config = fx.registry()
    config["projects"][SLUG]["state_file"] = "old-name.json"
    fx.config_path.write_text(json.dumps(config))

    code, payload = repair_plan(fx)

    assert code == 0
    assert payload["pointer_fixes"] == [{"slug": SLUG, "from": "old-name.json",
                                        "to": f"{SLUG}.json"}]
    assert fx.config_path.read_text() == json.dumps(config)  # plan never writes


def test_apply_corrects_the_stale_pointer_and_verifies_it(fx):
    config = fx.registry()
    config["projects"][SLUG]["state_file"] = "old-name.json"
    fx.config_path.write_text(json.dumps(config))

    code, payload = repair_apply(fx)

    assert code == 0
    assert payload["written"] is True
    assert payload["verified"] is True
    assert fx.entry()["state_file"] == f"{SLUG}.json"


def test_apply_leaves_every_other_field_and_project_untouched(tmp_path):
    fx = build_home(tmp_path)
    config = fx.registry()
    config["projects"][SLUG]["state_file"] = "old-name.json"
    config["projects"][SLUG]["frozen_hook"] = "off"
    config["projects"]["sibling"] = {"directory": "/somewhere/else", "docs_root": "",
                                     "state_file": "sibling.json", "repositories": {}}
    fx.config_path.write_text(json.dumps(config))

    repair_apply(fx)

    entry = fx.entry()
    assert entry["frozen_hook"] == "off"
    assert entry["directory"] == config["projects"][SLUG]["directory"]
    assert fx.entry("sibling") == config["projects"]["sibling"]


def test_an_orphaned_state_file_is_reported_but_never_turned_into_a_registry_entry(fx):
    (fx.state_dir / "ghost.json").write_text(json.dumps(
        {"schema_version": 1, "active_session": None, "sessions": {}}))

    code, payload = repair_plan(fx)
    assert payload["orphaned_state_files"] == ["ghost.json"]

    repair_apply(fx)
    assert "ghost" not in fx.registry()["projects"]


def test_a_missing_config_file_is_rebuilt_as_a_valid_empty_registry(tmp_path):
    fx = build_home(tmp_path, write_config=False)

    plan_code, plan_payload = repair_plan(fx)
    assert plan_code == 0
    assert plan_payload["config_readable"] is False

    code, payload = repair_apply(fx)

    assert code == 0
    assert payload["written"] is True
    assert fx.registry() == {"schema_version": 1, "projects": {}}


def test_a_corrupt_config_file_is_treated_the_same_as_a_missing_one(fx):
    fx.config_path.write_text("{ not json")
    code, payload = repair_apply(fx)
    assert code == 0
    assert fx.registry() == {"schema_version": 1, "projects": {}}


def test_nothing_to_repair_leaves_the_registry_untouched(fx):
    before = fx.config_path.read_text()
    code, payload = repair_apply(fx)
    assert code == 0
    assert payload["written"] is False
    assert fx.config_path.read_text() == before


def test_apply_without_confirm_changes_nothing(fx):
    config = fx.registry()
    config["projects"][SLUG]["state_file"] = "old-name.json"
    fx.config_path.write_text(json.dumps(config))
    before = fx.config_path.read_text()

    code, payload = repair_apply(fx, confirm=False)

    assert code == 2
    assert payload["error"] == "unconfirmed"
    assert fx.config_path.read_text() == before


def test_a_pointer_escaping_the_state_directory_is_never_auto_corrected(fx):
    config = fx.registry()
    config["projects"][SLUG]["state_file"] = "../../etc/passwd"
    fx.config_path.write_text(json.dumps(config))
    code, payload = repair_plan(fx)
    assert payload["pointer_fixes"] == []
