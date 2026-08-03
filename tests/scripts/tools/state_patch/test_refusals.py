"""Every way a requested patch is rejected before anything is touched — malformed shapes, a request
naming nothing, a missing repository, an unknown project or session — each proving nothing moved."""

from __future__ import annotations

import json

import pytest

from tests.scripts.tools.state_patch.conftest import apply, plan


@pytest.mark.parametrize("raw,rule", [
    ("tier", "malformed_set"),        # no '='
    ("=high", "malformed_set"),       # blank key
], ids=["missing_equals", "blank_key"])
def test_a_malformed_set_argument_is_refused(fx, raw, rule):
    code, payload = plan(fx, "--set", raw)
    assert code == 1
    assert payload["rule"] == rule
    assert payload["message"].strip()


def test_a_blank_unset_argument_is_refused(fx):
    code, payload = plan(fx, "--unset", "   ")
    assert code == 1
    assert payload["rule"] == "malformed_unset"


@pytest.mark.parametrize("raw,rule", [
    ("svc-auth", "malformed_set_repository"),       # no '='
    ("=/tmp", "malformed_set_repository"),           # blank service
], ids=["missing_equals", "blank_service"])
def test_a_malformed_set_repository_argument_is_refused(fx, raw, rule):
    code, payload = plan(fx, "--set-repository", raw)
    assert code == 1
    assert payload["rule"] == rule


def test_a_set_repository_with_a_blank_path_is_refused(fx):
    code, payload = plan(fx, "--set-repository", "svc-auth=")
    assert code == 1
    assert payload["rule"] == "malformed_set_repository"


def test_a_repository_directory_that_does_not_exist_is_refused(tmp_path, fx):
    missing = tmp_path / "does-not-exist"
    code, payload = apply(fx, "--set-repository", f"svc-auth={missing}")
    assert code == 1
    assert payload["rule"] == "repository_path_missing"
    assert str(missing) in payload["message"]
    assert "repositories" not in fx.entry() or fx.entry()["repositories"] == {}


def test_a_repository_directory_that_exists_is_accepted(tmp_path, fx):
    svc = tmp_path / "svc-auth"
    svc.mkdir()
    code, payload = apply(fx, "--set-repository", f"svc-auth={svc}")
    assert code == 0
    assert fx.entry()["repositories"]["svc-auth"] == str(svc)


def test_a_key_named_in_both_set_and_unset_is_refused(fx):
    code, payload = plan(fx, "--set", "tier=high", "--unset", "tier")
    assert code == 1
    assert payload["rule"] == "key_set_and_unset"
    assert "tier" in payload["message"]


def test_a_request_naming_no_change_at_all_is_refused(fx):
    """A run naming nothing to set, unset, or set-repository is a usage mistake, not a silent
    no-op — this tool exists to patch something."""
    code, payload = plan(fx)
    assert code == 1
    assert payload["rule"] == "no_changes_requested"


def test_a_project_that_does_not_exist_is_refused_naming_the_registered_ones(fx):
    """A slug is checked for membership in the registry, so an invented name is never joined into
    a path."""
    code, payload = plan(fx, "--set", "tier=high", "--project-slug", "../../etc")
    assert code == 4
    assert payload["error"] == "ambiguous"
    assert [c["slug"] for c in payload["candidates"]] == [fx.slug]


def test_a_session_that_does_not_exist_is_refused_naming_the_recorded_ones(fx):
    code, payload = plan(fx, "--set", "tier=high", session="no-such-session")
    assert code == 4
    assert payload["error"] == "ambiguous"
    assert sorted(c["id"] for c in payload["candidates"]) == \
        ["2026-01-02-alpha", "2026-01-03-beta"]


def test_an_unreadable_state_file_is_refused_rather_than_patched(fx):
    fx.state_path.write_text("{ broken")
    code, payload = plan(fx, "--set", "tier=high")
    assert code == 3
    assert payload["message"].strip()


def test_a_state_file_pointer_that_escapes_the_record_directory_is_refused(fx):
    """A `state_file` containing a path separator would resolve outside `~/.hercules/state`; the
    name is used as a bare filename, never joined into an escaping path."""
    config = fx.registry()
    config["projects"][fx.slug]["state_file"] = "../../etc/passwd"
    fx.config_path.write_text(json.dumps(config))
    code, payload = plan(fx, "--set", "tier=high")
    assert code == 3
    assert "escapes" in payload["message"]


def test_an_unreadable_registry_is_refused_rather_than_patched(fx):
    fx.config_path.write_text("{ broken")
    code, payload = plan(fx, "--set", "tier=high")
    assert code == 3
    assert payload["message"].strip()


def test_no_refusal_ever_leaves_a_half_written_file(tmp_path, fx):
    """Every refusal above happens before any write; this asserts it directly against the raw
    bytes on disk, not just the reported outcome."""
    before_state = fx.state_path.read_text()
    before_config = fx.config_path.read_text()
    apply(fx, "--set-repository", f"svc-auth={tmp_path / 'missing'}")
    apply(fx, "--set", "tier=high", "--unset", "tier")
    assert fx.state_path.read_text() == before_state
    assert fx.config_path.read_text() == before_config
