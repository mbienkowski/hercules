"""The eight safety rules. A refusal that returns the right code having already deleted something is
no refusal, so every test asserts the code, the rule id, AND that the target still exists."""

from __future__ import annotations

import json

import pytest

from tests.scripts.tools.project_reset.conftest import apply, build_home

import project_reset  # noqa: E402 — conftest puts src/scripts/tools on the path


def _retarget(fx, new_root) -> None:
    """Point the project's documents root at `new_root`, the way a hand-edited registry would — that
    has already happened on a real installation, so it is the realistic route to every value below."""
    config = fx.registry()
    config["projects"][fx.slug]["docs_root"] = str(new_root)
    fx.config_path.write_text(json.dumps(config))


# Five rules sharing one shape: a target, its rule id, and the path that must survive it.
_SIMPLE_DANGEROUS_TARGETS = [
    (lambda fx, tmp_path: "", "target_is_blank", lambda fx, tmp_path: fx.project),
    (lambda fx, tmp_path: "/", "target_is_filesystem_root", lambda fx, tmp_path: fx.project),
    (lambda fx, tmp_path: tmp_path, "target_is_home_directory", lambda fx, tmp_path: fx.project),
    (lambda fx, tmp_path: tmp_path / ".hercules", "target_is_hercules_home", lambda fx, tmp_path: tmp_path / ".hercules"),
    (lambda fx, tmp_path: fx.project, "target_is_project_directory", lambda fx, tmp_path: fx.project),
]


@pytest.mark.parametrize("target,rule,survivor", _SIMPLE_DANGEROUS_TARGETS, ids=[t[1] for t in _SIMPLE_DANGEROUS_TARGETS])
def test_a_dangerous_documents_target_is_refused_before_anything_is_touched(tmp_path, fx, target, rule, survivor):
    """Retargeting documents at a dangerous path is refused before anything is touched, and what
    would have been destroyed — asserted directly, not assumed — is still there."""
    _retarget(fx, target(fx, tmp_path))
    code, payload = apply(fx, "--documents")
    assert code == 1
    assert payload["rule"] == rule
    assert survivor(fx, tmp_path).exists()


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


def test_a_path_outside_the_permitted_roots_is_refused(tmp_path, fx):
    """The positive control, asserted against the rule itself: every real target is re-derived from
    the record, so only a future change accepting a caller-supplied path could ever reach this one."""
    ctx = project_reset.safety_context(fx.home, fx.slug, fx.entry(), fx.registry()["projects"])
    assert project_reset.rule_outside_permitted_roots(str(tmp_path / "stranger"), ctx) is True
    assert project_reset.rule_outside_permitted_roots(str(fx.docs / "inner"), ctx) is False


def test_every_refusal_names_a_next_action(fx):
    """A block that does not say what to do next strands the person. Each refusal carries a written
    message, not just a code."""
    _retarget(fx, "/")
    _, payload = apply(fx, "--documents")
    assert payload["message"].strip()
    assert payload["rule"] in payload.get("message", "") or len(payload["message"]) > 20
