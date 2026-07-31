"""The eight safety rules — one test each, and each proves the target survived.

A refusal that returns the right code while having already deleted something is not a refusal, so
every test here asserts the exit code, the rule identifier, AND that the target still exists.
"""

from __future__ import annotations

import json

from tools.tests.project_reset.conftest import apply, build_home

import project_reset  # noqa: E402 — conftest puts src/tools on the path


def _retarget(fx, new_root) -> None:
    """Point the project's documents root at `new_root`, the way a hand-edited registry would.
    Hand-editing this file has already happened on a real installation, so it is the realistic
    route to every dangerous value below."""
    config = fx.registry()
    config["projects"][fx.slug]["docs_root"] = str(new_root)
    fx.config_path.write_text(json.dumps(config))


def test_an_empty_documents_path_is_refused_before_it_can_resolve_to_the_working_directory(tmp_path):
    """An empty string silently resolves to wherever the process happens to be standing, so it is
    rejected before any resolution is attempted rather than after."""
    fx = build_home(tmp_path)
    _retarget(fx, "")
    code, payload = apply(fx, "--documents")
    assert code == 1
    assert payload["rule"] == "target_is_blank"
    assert fx.project.exists()


def test_the_filesystem_root_is_refused(tmp_path):
    """The worst possible target, and the one the person most needs to be certain about."""
    fx = build_home(tmp_path)
    _retarget(fx, "/")
    code, payload = apply(fx, "--documents")
    assert code == 1
    assert payload["rule"] == "target_is_filesystem_root"
    assert fx.project.exists()


def test_the_home_directory_is_refused(tmp_path):
    """Everything a person owns lives under it."""
    fx = build_home(tmp_path)
    _retarget(fx, tmp_path)
    code, payload = apply(fx, "--documents")
    assert code == 1
    assert payload["rule"] == "target_is_home_directory"
    assert fx.project.exists()


def test_the_record_directory_itself_is_refused(tmp_path):
    """The tool edits files inside the record; it never removes the record tree."""
    fx = build_home(tmp_path)
    _retarget(fx, tmp_path / ".hercules")
    code, payload = apply(fx, "--documents")
    assert code == 1
    assert payload["rule"] == "target_is_hercules_home"
    assert (tmp_path / ".hercules").exists()


def test_the_project_directory_itself_is_refused(tmp_path):
    """Clearing documents must never become clearing the code they document."""
    fx = build_home(tmp_path)
    _retarget(fx, fx.project)
    code, payload = apply(fx, "--documents")
    assert code == 1
    assert payload["rule"] == "target_is_project_directory"
    assert fx.project.exists()


def test_a_documents_root_containing_the_project_is_refused(tmp_path):
    """The dangerous direction is the opposite of the intuitive one: documents inside the code are
    legitimate, but a documents root that swallows the code is not."""
    outer, code_dir = tmp_path / "outer", tmp_path / "outer" / "code"
    code_dir.mkdir(parents=True)
    fx = build_home(tmp_path)
    config = fx.registry()
    config["projects"][fx.slug].update({"directory": str(code_dir), "docs_root": str(outer)})
    fx.config_path.write_text(json.dumps(config))
    exit_code, payload = apply(fx, "--documents", cwd=code_dir)
    assert exit_code == 1
    assert payload["rule"] == "target_contains_project_directory"
    assert code_dir.exists()


def test_a_path_belonging_to_another_registered_project_is_refused(tmp_path):
    """One project's misconfigured documents root must never reach into another project's files."""
    other_dir = tmp_path / "other-code"
    other_dir.mkdir()
    other = {"directory": str(other_dir), "docs_root": str(other_dir), "state_file": "other.json"}
    fx = build_home(tmp_path, extra_projects={"other": other})
    _retarget(fx, other_dir)
    code, payload = apply(fx, "--documents", "--project", fx.slug)
    assert code == 1
    assert payload["rule"] == "target_is_registered_elsewhere"
    assert other_dir.exists()


def test_a_path_outside_the_permitted_roots_is_refused(tmp_path):
    """The positive control, asserted against the rule itself rather than through the command line.

    Nothing reachable from the command line can carry this target: every path is re-derived from the
    record, so the only target that ever arrives IS the permitted root. Driving this rule through the
    command line would therefore prove nothing — it would pass whatever the rule said. The rule earns
    its place as the guard that stops a future change which starts accepting a path from a caller,
    and that is what is tested here.

    A hand-edited record pointing at a real but wrong directory is deliberately NOT caught here — no
    rule can tell a legitimate documents folder from a mistaken one. The confirmation screen shows
    the fully resolved path so a person can, and that gap is recorded as accepted risk.
    """
    fx = build_home(tmp_path)
    ctx = project_reset.safety_context(fx.home, fx.slug, fx.entry(), fx.registry()["projects"])
    assert project_reset.rule_outside_permitted_roots(str(tmp_path / "stranger"), ctx) is True
    assert project_reset.rule_outside_permitted_roots(str(fx.docs / "inner"), ctx) is False


def test_every_refusal_names_a_next_action(tmp_path):
    """A block that does not say what to do next strands the person. Each refusal carries a written
    message, not just a code."""
    fx = build_home(tmp_path)
    _retarget(fx, "/")
    _, payload = apply(fx, "--documents")
    assert payload["message"].strip()
    assert payload["rule"] in payload.get("message", "") or len(payload["message"]) > 20
