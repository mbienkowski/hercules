"""Project registration must preserve recall without crossing project boundaries."""
import json
import sys

import pytest

from tests.scripts.tools.memory_core.conftest import capture, run, select

core = sys.modules["memory_core"]


def registry(fx, projects):
    (fx.home / ".hercules/config.json").write_text(json.dumps({"projects": projects}))


@pytest.mark.parametrize("reverse", [False, True])
def test_deepest_registered_project_owns_its_memory_regardless_of_registry_order(fx, reverse):
    child = fx.project / "child"
    child.mkdir()
    (child / ".git").mkdir()
    rows = [("parent", {"directory": str(fx.project)}), ("child", {"directory": str(child)})]
    registry(fx, dict(reversed(rows) if reverse else rows))
    assert core.resolve_slug(str(child), home=fx.home) == "child"
    core.capture_entry(str(child), "decision", "Child only.", home=fx.home)
    assert not core.select_context(str(fx.project), home=fx.home)["entries"]


def test_equally_specific_registrations_refuse_instead_of_arbitrarily_sharing_memory(fx):
    registry(fx, {s: {"directory": str(fx.project)} for s in ("one", "two")})
    with pytest.raises(core.Refused, match="Equally specific"):
        core.resolve_slug(str(fx.project), home=fx.home)


def test_relative_docs_root_never_resolves_against_the_callers_working_directory(fx, tmp_path, monkeypatch):
    registry(fx, {"proj": {"directory": str(fx.project), "docs_root": "docs"}})
    other = tmp_path / "other"
    (other / "docs").mkdir(parents=True)
    monkeypatch.chdir(other)
    assert core.resolve_slug(str(other / "docs"), home=fx.home) != "proj"
    assert core.resolve_slug(str(fx.project / "docs"), home=fx.home) == "proj"
    capture(fx, "decision", "Keep builds reproducible.")
    code, _ = run(fx, "promote", "--cwd", str(fx.project), "--id", "M:0001",
                  "--target", str(other / "docs/learnings.md"), "--confirm")
    assert code != 0 and not (other / "docs/learnings.md").exists()


def test_registering_a_project_preserves_its_existing_ordinary_chat_memory(fx):
    registry(fx, {})
    (fx.project / ".git").mkdir()
    capture(fx, "decision", "Prefer short responses.", pinned=True)
    before = core.resolve_slug(str(fx.project), home=fx.home)
    registry(fx, {"registered": {"directory": str(fx.project), "docs_root": "docs"}})
    assert core.resolve_slug(str(fx.project), home=fx.home) == before
    assert select(fx)[1]["entries"][0]["statement"] == "Prefer short responses."
    assert capture(fx, "decision", "Use reproducible builds.")[0] == 0


def test_preexisting_stores_are_not_silently_merged_or_discarded(fx):
    capture(fx, "decision", "Registered preference.")
    registry(fx, {})
    capture(fx, "decision", "Unregistered preference.")
    registry(fx, {"proj": {"directory": str(fx.project)}})
    with pytest.raises(core.Refused, match="Multiple pre-existing"):
        core.resolve_slug(str(fx.project), home=fx.home)


def test_hypotheses_cannot_be_evidence_for_governing_decisions(fx):
    assert capture(fx, "decision", "An unproven claim.", evidence='{"basis":"hypothesis"}')[0] != 0
    assert not select(fx)[1]["entries"]


def test_nested_registration_does_not_adopt_parent_repositorys_fallback_memory(fx):
    registry(fx, {})
    (fx.project / ".git").mkdir()
    capture(fx, "decision", "Parent preference.")
    child = fx.project / "child"
    child.mkdir()
    registry(fx, {"parent": {"directory": str(fx.project)}, "child": {"directory": str(child)}})
    assert core.resolve_slug(str(child), home=fx.home) == "child"
    assert not core.select_context(str(child), home=fx.home)["entries"]
