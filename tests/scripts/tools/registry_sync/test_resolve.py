"""`resolve --cwd <path>`, read-only: a unique match in the code, docs or cross-repo root, no match
at all, and two projects nesting so the deeper one ranks first."""

from __future__ import annotations

import json

from tests.scripts.tools.registry_sync.conftest import SLUG, build_home, resolve


def test_a_directory_inside_the_code_root_resolves(fx):
    code, payload = resolve(fx, fx.project)
    assert code == 0
    assert payload["resolved"]["slug"] == SLUG


def test_a_directory_inside_the_docs_root_also_resolves(fx):
    """`resolve`'s roots are the union `project_reset` and the guard's own resolver each track
    alone — a docs-only launch directory must still resolve, unlike the guard's narrower set."""
    code, payload = resolve(fx, fx.docs)
    assert code == 0
    assert payload["resolved"]["slug"] == SLUG


def test_a_directory_inside_a_cross_repo_service_resolves(tmp_path):
    svc = tmp_path / "svc-auth"
    svc.mkdir()
    fx = build_home(tmp_path, repositories={"svc-auth": str(svc)})
    code, payload = resolve(fx, svc)
    assert code == 0
    assert payload["resolved"]["slug"] == SLUG


def test_a_directory_matching_no_project_reports_no_resolution(tmp_path, fx):
    unrelated = tmp_path / "somewhere-else"
    unrelated.mkdir()
    code, payload = resolve(fx, unrelated)
    assert code == 1
    assert payload["resolved"] is None
    assert payload["candidates"] == []


def test_a_nested_project_lists_the_deeper_match_first(tmp_path):
    """A genuine ambiguity leaves `resolved` at `None` rather than guessing, but ranks the deeper,
    more specific root first."""
    outer = tmp_path / "code"
    outer.mkdir()
    inner = outer / "packages" / "inner"
    inner.mkdir(parents=True)
    fx = build_home(tmp_path, slug="outer")
    config = fx.registry()
    config["projects"]["inner"] = {"directory": str(inner), "docs_root": "", "state_file":
                                   "inner.json", "repositories": {}}
    fx.config_path.write_text(json.dumps(config))
    (fx.state_dir / "inner.json").write_text(json.dumps(
        {"schema_version": 1, "active_session": None, "sessions": {}}))

    code, payload = resolve(fx, inner)

    assert code == 1
    assert payload["resolved"] is None
    assert [c["slug"] for c in payload["candidates"]] == ["inner", "outer"]


def test_resolve_never_writes_anything(fx):
    before = fx.config_path.read_text()
    resolve(fx, fx.project)
    assert fx.config_path.read_text() == before


def test_a_missing_registry_resolves_to_nothing_rather_than_raising(tmp_path):
    fx = build_home(tmp_path, write_config=False)
    code, payload = resolve(fx, fx.project)
    assert code == 1
    assert payload["candidates"] == []
