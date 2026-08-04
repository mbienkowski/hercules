"""Proves the document gate runs on the HOST's schedule and refuses a phase change the work has not
earned — and that it lets everything else past.

The failure this file exists to prevent: a gate that only fires when an instruction remembered to
mention it, which is what the standard had before. The second failure is the opposite one — a gate so
eager it blocks unrelated work, because the house rule is that a hook never bricks someone's editing.
Every fail-OPEN path below is a deliberate allow, not an accident of a missing test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[3] / "src" / "scripts" / "hooks"
_TOOLS = Path(__file__).resolve().parents[3] / "src" / "scripts" / "tools"
for _dir in (_HOOKS, _TOOLS):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import document_gate  # noqa: E402

from tests.scripts.tools.doc_lint.conftest import (  # noqa: E402
    CLEAN_REQUIREMENTS, CLEAN_SPEC, REQUIREMENTS_NAME, SPEC_NAME,
)
from tests.scripts.tools.doc_report.conftest import full_review, with_verdict  # noqa: E402

ALLOW, BLOCK = 0, 2
SESSION = "2026-08-04-booking-reschedule"
SLUG = "booking"


def build_project(tmp_path: Path, *, documents: dict, tier: str = "medium") -> Path:
    """A registry, a state file and a session folder — the shape the gate resolves against."""
    home = tmp_path / "home"
    project = tmp_path / "repo"
    folder = project / "docs" / SESSION
    folder.mkdir(parents=True)
    for name, text in documents.items():
        (folder / name).write_text(text, encoding="utf-8")
    (home / ".hercules" / "state").mkdir(parents=True)
    (home / ".hercules" / "config.json").write_text(json.dumps({
        "schema_version": 1,
        "projects": {SLUG: {"directory": str(project), "docs_root": "docs",
                            "state_file": "%s.json" % SLUG, "repositories": {}}},
    }))
    (home / ".hercules" / "state" / ("%s.json" % SLUG)).write_text(json.dumps({
        "schema_version": 1, "active_session": SESSION,
        "sessions": {SESSION: {"tier": tier, "current_phase": "discover"}},
    }))
    return home, project


def advance_event(project: Path, phase: str = "design") -> dict:
    return {"tool_name": "Bash", "cwd": str(project),
            "tool_input": {"command":
                           "python3 tools/state_patch.py apply --project-slug %s "
                           "--session-id %s --set current_phase=%s --confirm" % (SLUG, SESSION, phase)}}


def run(mode: str, event: dict, home: Path, capsys) -> tuple:
    code = document_gate.main([mode], stdin_text=json.dumps(event), home=str(home))
    return code, capsys.readouterr().err


def passing_review(kind="business-requirements", tier="medium") -> str:
    return json.dumps(full_review(kind=kind, tier=tier))


# ── the interlock ───────────────────────────────────────────────────────────────────────────────


def test_a_reviewed_document_lets_the_phase_change_through(tmp_path, capsys):
    home, project = build_project(tmp_path, documents={
        REQUIREMENTS_NAME: CLEAN_REQUIREMENTS,
        REQUIREMENTS_NAME.replace(".md", "-report.json"): passing_review(),
    })
    code, err = run("advance", advance_event(project), home, capsys)
    assert code == ALLOW, err


def test_a_document_with_no_review_cannot_advance(tmp_path, capsys):
    """The gate this whole design exists for: the work is skippable until something refuses to move
    without it."""
    home, project = build_project(tmp_path, documents={REQUIREMENTS_NAME: CLEAN_REQUIREMENTS})
    code, err = run("advance", advance_event(project), home, capsys)
    assert code == BLOCK
    assert "has no review" in err
    assert "-report.json" in err


def test_a_review_that_says_revise_cannot_advance(tmp_path, capsys):
    """A review is not a formality: its own verdict decides."""
    review = with_verdict(full_review(tier="critical"), "flow-coverage", "major")
    home, project = build_project(tmp_path, tier="critical", documents={
        REQUIREMENTS_NAME: CLEAN_REQUIREMENTS,
        REQUIREMENTS_NAME.replace(".md", "-report.json"): json.dumps(review),
    })
    code, err = run("advance", advance_event(project), home, capsys)
    assert code == BLOCK
    assert "revise" in err


def test_an_incomplete_review_cannot_advance(tmp_path, capsys):
    """Skipping a rubric category is how a review passes something nobody looked at."""
    review = full_review()
    review["categories"] = review["categories"][:3]
    home, project = build_project(tmp_path, documents={
        REQUIREMENTS_NAME: CLEAN_REQUIREMENTS,
        REQUIREMENTS_NAME.replace(".md", "-report.json"): json.dumps(review),
    })
    code, err = run("advance", advance_event(project), home, capsys)
    assert code == BLOCK
    assert "not answerable" in err


def test_a_dead_reference_cannot_advance(tmp_path, capsys):
    """The one thing the checker blocks on has to survive into the phase gate."""
    home, project = build_project(tmp_path, documents={
        REQUIREMENTS_NAME: CLEAN_REQUIREMENTS,
        SPEC_NAME: CLEAN_SPEC.replace("§Flows]", "§Nowhere]", 1),
        SPEC_NAME.replace(".md", "-report.json"): passing_review(kind="spec"),
    })
    code, err = run("advance", advance_event(project, phase="build"), home, capsys)
    assert code == BLOCK
    assert "DOC701" in err


def test_the_refusal_names_the_next_action(tmp_path, capsys):
    """§ Failure moments: a stop names what to do, never just what is wrong."""
    home, project = build_project(tmp_path, documents={REQUIREMENTS_NAME: CLEAN_REQUIREMENTS})
    _, err = run("advance", advance_event(project), home, capsys)
    assert "run the same command again" in err
    assert "rubric" in err


# ── what it must NOT block ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("command", [
    "git status",
    "python3 tools/state_patch.py apply --set current_spec_round=2 --confirm",
    "echo current_phase=design",
    "python3 tools/retire_spec.py apply --spec-file x.md --confirm",
])
def test_an_unrelated_command_is_never_gated(tmp_path, capsys, command):
    """A gate that fires on anything mentioning a phase would make the tool unusable."""
    home, project = build_project(tmp_path, documents={REQUIREMENTS_NAME: CLEAN_REQUIREMENTS})
    event = {"tool_name": "Bash", "cwd": str(project), "tool_input": {"command": command}}
    code, _ = run("advance", event, home, capsys)
    assert code == ALLOW


def test_moving_to_ship_is_not_gated(tmp_path, capsys):
    """Only the phases that rest on a document are gated; Ship rests on the build."""
    home, project = build_project(tmp_path, documents={REQUIREMENTS_NAME: CLEAN_REQUIREMENTS})
    code, _ = run("advance", advance_event(project, phase="shipped"), home, capsys)
    assert code == ALLOW


@pytest.mark.parametrize("event", [
    {}, {"tool_input": {}}, {"tool_input": {"command": None}}, {"cwd": "/nowhere"},
])
def test_an_unresolvable_event_allows(tmp_path, capsys, event):
    """Fail OPEN: a gate that cannot tell what is happening must not guess."""
    home, _ = build_project(tmp_path, documents={REQUIREMENTS_NAME: CLEAN_REQUIREMENTS})
    code, _ = run("advance", event, home, capsys)
    assert code == ALLOW


def test_an_unregistered_project_allows(tmp_path, capsys):
    """Someone else's repository is not evidence of an unreviewed document."""
    home, _ = build_project(tmp_path, documents={REQUIREMENTS_NAME: CLEAN_REQUIREMENTS})
    event = advance_event(tmp_path / "elsewhere")
    code, _ = run("advance", event, home, capsys)
    assert code == ALLOW


def test_unparseable_stdin_allows(tmp_path):
    code = document_gate.main(["advance"], stdin_text="{not json", home=str(tmp_path))
    assert code == ALLOW


def test_an_unknown_mode_allows(tmp_path):
    code = document_gate.main(["sideways"], stdin_text="{}", home=str(tmp_path))
    assert code == ALLOW


# ── review: findings come back without being asked for ──────────────────────────────────────────


def test_writing_a_document_returns_its_findings(tmp_path, capsys):
    """The half that saves the model reading the rules: it never asked for this."""
    home, project = build_project(tmp_path, documents={})
    folder = project / "docs" / SESSION
    document = folder / REQUIREMENTS_NAME
    document.write_text(CLEAN_REQUIREMENTS.replace(
        "- **Change wanted** — a customer moves an appointment without speaking to anyone.",
        "- **Change wanted** — the `BookingCalendar` table must be refactored for 2 people.", 1),
        encoding="utf-8")
    event = {"tool_name": "Write", "cwd": str(project),
             "tool_input": {"file_path": str(document)}}
    code, err = run("review", event, home, capsys)
    assert code == BLOCK
    assert "DOC204" in err or "DOC206" in err
    assert "doc_rules.json" in err


def test_a_clean_document_returns_nothing(tmp_path, capsys):
    """Silence when there is nothing to say — otherwise the gate becomes noise people learn to skip."""
    home, project = build_project(tmp_path, documents={})
    document = project / "docs" / SESSION / REQUIREMENTS_NAME
    document.write_text(CLEAN_REQUIREMENTS, encoding="utf-8")
    event = {"tool_name": "Write", "cwd": str(project),
             "tool_input": {"file_path": str(document)}}
    code, err = run("review", event, home, capsys)
    assert code == ALLOW
    assert err == ""


def test_an_ordinary_file_is_ignored(tmp_path, capsys):
    """Only delivery documents are the gate's business."""
    home, project = build_project(tmp_path, documents={})
    other = project / "README.md"
    other.write_text("# hello\n", encoding="utf-8")
    event = {"tool_name": "Write", "cwd": str(project), "tool_input": {"file_path": str(other)}}
    code, err = run("review", event, home, capsys)
    assert code == ALLOW
    assert err == ""


def test_review_never_reports_on_a_file_that_is_not_there(tmp_path, capsys):
    """An edit that failed leaves nothing to check, and inventing a verdict would be worse."""
    home, project = build_project(tmp_path, documents={})
    event = {"tool_name": "Write", "cwd": str(project),
             "tool_input": {"file_path": str(project / "docs" / SESSION / REQUIREMENTS_NAME)}}
    code, _ = run("review", event, home, capsys)
    assert code == ALLOW


# ── probes: a spec cannot be written before its assumptions are falsified ───────────────────────


def write_event(project: Path, filename: str) -> dict:
    return {"tool_name": "Write", "cwd": str(project),
            "tool_input": {"file_path": str(project / "docs" / SESSION / filename)}}


def _probe_record(folder: Path, label: str, verdict: str) -> None:
    (folder / "probes").mkdir(parents=True, exist_ok=True)
    (folder / "probes" / ("probe-%s.json" % label)).write_text(
        json.dumps({"label": label, "verdict": verdict, "record": {"argv": ["true"]}}))


def test_a_spec_cannot_be_written_with_no_probes_run(tmp_path, capsys):
    """The gap this fix exists to close: nothing else in the chain would have caught an agent that
    skipped Design's falsification step entirely."""
    home, project = build_project(tmp_path, documents={}, tier="medium")
    code, err = run("probes", write_event(project, SPEC_NAME), home, capsys)
    assert code == BLOCK
    assert "cannot be written yet" in err
    assert "no probes have been run" in err


def test_a_spec_can_be_written_once_the_tier_s_probes_verify(tmp_path, capsys):
    home, project = build_project(tmp_path, documents={}, tier="medium")
    folder = project / "docs" / SESSION
    _probe_record(folder, "one", "PASS")
    _probe_record(folder, "two", "PASS")
    code, err = run("probes", write_event(project, SPEC_NAME), home, capsys)
    assert (code, err) == (ALLOW, "")


def test_a_spec_is_still_refused_if_a_probe_contradicted_the_plan(tmp_path, capsys):
    home, project = build_project(tmp_path, documents={}, tier="medium")
    folder = project / "docs" / SESSION
    _probe_record(folder, "one", "PASS")
    _probe_record(folder, "two", "FAIL")
    code, err = run("probes", write_event(project, SPEC_NAME), home, capsys)
    assert code == BLOCK
    assert "contradicted" in err


def test_trivial_tier_needs_no_probes_at_all(tmp_path, capsys):
    """Depth scales — a typo does not owe a feasibility pass."""
    home, project = build_project(tmp_path, documents={}, tier="trivial")
    code, err = run("probes", write_event(project, SPEC_NAME), home, capsys)
    assert (code, err) == (ALLOW, "")


def test_an_ordinary_document_is_not_gated_by_the_probe_check(tmp_path, capsys):
    """Only spec files owe a probe — business requirements are Discover's business, not Design's."""
    home, project = build_project(tmp_path, documents={}, tier="medium")
    code, err = run("probes", write_event(project, REQUIREMENTS_NAME), home, capsys)
    assert (code, err) == (ALLOW, "")


def test_a_write_outside_the_session_folder_is_never_gated(tmp_path, capsys):
    """A file that merely matches the spec filename pattern, but sits outside this session's own
    folder, must not be treated as this session's spec — the resolver checks containment, not just
    the name."""
    home, project = build_project(tmp_path, documents={}, tier="medium")
    (project / "elsewhere").mkdir()
    event = {"tool_name": "Write", "cwd": str(project),
             "tool_input": {"file_path": str(project / "elsewhere" / SPEC_NAME)}}
    code, err = run("probes", event, home, capsys)
    assert (code, err) == (ALLOW, "")


def test_an_unregistered_project_is_never_gated_by_a_coincidental_filename(tmp_path, capsys):
    """Fail open: a spec-shaped filename in a repository Hercules has never heard of is not
    evidence that anything was skipped."""
    home, _ = build_project(tmp_path, documents={})
    elsewhere = tmp_path / "unrelated"
    (elsewhere / "docs" / SESSION).mkdir(parents=True)
    event = {"tool_name": "Write", "cwd": str(elsewhere),
             "tool_input": {"file_path": str(elsewhere / "docs" / SESSION / SPEC_NAME)}}
    code, err = run("probes", event, home, capsys)
    assert (code, err) == (ALLOW, "")
