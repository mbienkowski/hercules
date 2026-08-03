"""A lying `verified: true` or a dropped sibling is invisible from the command line, which only sees
the tool's own report — so `verify_repair` is driven directly, stubbing the one seam it reads through."""

from __future__ import annotations

import json

import pytest

from tests.scripts.tools.registry_sync.conftest import repair_apply

import registry_sync  # noqa: E402 — conftest puts src/scripts/tools on the path


def _stub_read_json(monkeypatch, after_projects):
    monkeypatch.setattr(registry_sync, "read_json", lambda path: {"projects": after_projects})


def test_verify_repair_reports_true_on_a_real_match(monkeypatch):
    before = {"projects": {"p": {"state_file": "old.json"}, "other": {"state_file": "o.json"}}}
    fixes = [{"slug": "p", "from": "old.json", "to": "new.json"}]
    _stub_read_json(monkeypatch, {"p": {"state_file": "new.json"}, "other": {"state_file": "o.json"}})
    assert registry_sync.verify_repair(object(), fixes, before) is True


@pytest.mark.parametrize("after_projects,expected", [
    ({"p": {"state_file": "old.json"}, "other": {"state_file": "o.json"}}, False),  # fix never landed
    ({"p": {"state_file": "new.json"}, "other": {"state_file": "moved.json"}}, False),  # sibling moved
], ids=["fix_missing", "sibling_altered"])
def test_verify_repair_reports_false_on_every_way_a_patch_can_lie(monkeypatch, after_projects, expected):
    before = {"projects": {"p": {"state_file": "old.json"}, "other": {"state_file": "o.json"}}}
    fixes = [{"slug": "p", "from": "old.json", "to": "new.json"}]
    _stub_read_json(monkeypatch, after_projects)
    assert registry_sync.verify_repair(object(), fixes, before) is expected


def test_an_unclassified_failure_during_repair_apply_changes_nothing_and_is_reported(fx, monkeypatch):
    """The catch-all exists so an unanticipated error resolves to doing nothing; nothing in the
    normal flow raises one, so it could be narrowed to an unreachable type and no test would object."""
    config = fx.registry()
    config["projects"][fx.slug]["state_file"] = "old-name.json"
    fx.config_path.write_text(json.dumps(config))
    before = fx.config_path.read_text()

    monkeypatch.setattr(registry_sync, "atomic_write_json",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("unexpected")))
    code, payload = repair_apply(fx)
    assert code == 3
    assert fx.config_path.read_text() == before
    assert payload["message"].strip()


def test_a_verification_that_returns_false_escalates_to_the_internal_exit_code(fx, monkeypatch):
    config = fx.registry()
    config["projects"][fx.slug]["state_file"] = "old-name.json"
    fx.config_path.write_text(json.dumps(config))

    monkeypatch.setattr(registry_sync, "verify_repair", lambda *a, **kw: False)
    code, payload = repair_apply(fx)
    assert code == 3
    assert payload["verified"] is False
