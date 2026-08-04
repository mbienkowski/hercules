"""The document gate walked end to end as a SHIPPED program, the way a host actually runs it.

This is a supply-chain check, not a logic one: the unit suite drives `src/`, and would stay green if
the build dropped a file, renamed a tool, or shipped a `doc_rules.json` the gate cannot read. Here
nothing is imported — every step is a subprocess against `dist/`, with a scratch HOME, exactly as a
host spawns it. It walks the real sequence a session goes through:

    write the requirements  ->  try to advance  ->  write a lazy review  ->  write a real one

and asserts the door is shut for the middle two and open at the end. The failure it exists to catch
is a chain that passes in pieces and does not connect: the checker fine, the judge fine, and the
gate silently allowing everything because the tools directory moved.

Parametrised over every distribution that ships the gate, so an ecosystem whose build drops it fails
here rather than at a user's keyboard.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.scripts.tools.doc_lint.conftest import CLEAN_REQUIREMENTS, REQUIREMENTS_NAME
from tests.scripts.tools.doc_report.conftest import full_review

# Hardcoded, never imported from the gate, so a mutated primitive is killed rather than mirrored.
_ALLOW, _DENY = 0, 2
_DENY_MARKER = "Hercules:"

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DIST = _REPO_ROOT / "dist"
_SESSION = "2026-08-04-booking-reschedule"
_SLUG = "smoke"

# Derived from the tree, so an eighth distribution is covered with no new line here.
_SHIPPED = sorted(p.name for p in _DIST.iterdir()
                  if (p / "hooks" / "document_gate.py").is_file())


def _plant(tmp_path: Path):
    """A scratch HOME, a registry, a state file and a session folder — nothing touching a real one."""
    home, repo = tmp_path / "home", tmp_path / "repo"
    (repo / "docs" / _SESSION).mkdir(parents=True)
    (home / ".hercules" / "state").mkdir(parents=True)
    (home / ".hercules" / "config.json").write_text(json.dumps({
        "schema_version": 1,
        "projects": {_SLUG: {"directory": str(repo), "docs_root": "docs",
                             "state_file": "%s.json" % _SLUG, "repositories": {}}}}))
    (home / ".hercules" / "state" / ("%s.json" % _SLUG)).write_text(json.dumps({
        "schema_version": 1, "active_session": _SESSION,
        "sessions": {_SESSION: {"tier": "medium", "current_phase": "discover"}}}))
    document = repo / "docs" / _SESSION / REQUIREMENTS_NAME
    document.write_text(CLEAN_REQUIREMENTS, encoding="utf-8")
    return home, repo, document


def _run(ecosystem: str, mode: str, event: dict, home: Path):
    gate = _DIST / ecosystem / "hooks" / "document_gate.py"
    result = subprocess.run([sys.executable, str(gate), mode], input=json.dumps(event),
                            capture_output=True, text=True,
                            env={**os.environ, "HOME": str(home)})
    return result.returncode, result.stderr


def _advance_event(repo: Path) -> dict:
    return {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command":
            "python3 tools/state_patch.py apply --project-slug %s --session-id %s "
            "--set current_phase=design --confirm" % (_SLUG, _SESSION)}}


def test_the_gate_ships_somewhere():
    """An empty list would make every parametrised walk below vacuous."""
    assert _SHIPPED, "no distribution ships hooks/document_gate.py"


@pytest.mark.parametrize("ecosystem", _SHIPPED)
def test_a_session_walks_the_whole_chain_as_shipped(tmp_path, ecosystem):
    home, repo, document = _plant(tmp_path)
    report = document.with_name(document.stem + "-report.json")

    # 1. The document is written. A compliant one says nothing — silence is the clean signal.
    code, err = _run(ecosystem, "review",
                     {"tool_name": "Write", "cwd": str(repo),
                      "tool_input": {"file_path": str(document)}}, home)
    assert code == _ALLOW, "a compliant document must not be reported on: %s" % err
    assert err.strip() == ""

    # 2. Advancing with no review at all is refused.
    code, err = _run(ecosystem, "advance", _advance_event(repo), home)
    assert code == _DENY, "%s let a phase change through with no review" % ecosystem
    assert _DENY_MARKER in err
    assert "has no review" in err

    # 3. A review that skipped categories is refused, and names which ones.
    lazy = full_review()
    lazy["categories"] = lazy["categories"][:3]
    report.write_text(json.dumps(lazy), encoding="utf-8")
    code, err = _run(ecosystem, "advance", _advance_event(repo), home)
    assert code == _DENY, "%s accepted a review that skipped categories" % ecosystem
    assert "never a pass" in err, "the refusal must name the skipped categories, not just count them"

    # 4. A complete review opens the door.
    report.write_text(json.dumps(full_review()), encoding="utf-8")
    code, err = _run(ecosystem, "advance", _advance_event(repo), home)
    assert code == _ALLOW, "%s blocked a fully reviewed session: %s" % (ecosystem, err)


@pytest.mark.parametrize("ecosystem", _SHIPPED)
def test_the_shipped_gate_reports_a_real_defect(tmp_path, ecosystem):
    """The other direction: a document that HAS a problem must produce one, or the whole chain is
    decoration. Uses the containment rule, since a business document naming a class is the drift
    this standard was built for."""
    home, repo, document = _plant(tmp_path)
    document.write_text(CLEAN_REQUIREMENTS.replace(
        "- **Change wanted** — a customer moves an appointment without speaking to anyone.",
        "- **Change wanted** — the `BookingCalendar` table must be refactored for 2 people.", 1),
        encoding="utf-8")
    code, err = _run(ecosystem, "review",
                     {"tool_name": "Write", "cwd": str(repo),
                      "tool_input": {"file_path": str(document)}}, home)
    assert code == _DENY, "%s reported nothing on a document that drifted technical" % ecosystem
    assert "doc_rules.json" in err, "the report must say where the rules came from"
    assert ("DOC204" in err or "DOC206" in err)


@pytest.mark.parametrize("ecosystem", _SHIPPED)
def test_the_shipped_gate_leaves_unrelated_work_alone(tmp_path, ecosystem):
    """Fail-open, proven against the shipped copy: an ordinary edit and an ordinary command are not
    this gate's business, and a gate that blocks them is worse than no gate."""
    home, repo, _ = _plant(tmp_path)
    other = repo / "README.md"
    other.write_text("# hello\n", encoding="utf-8")

    code, err = _run(ecosystem, "review",
                     {"tool_name": "Write", "cwd": str(repo),
                      "tool_input": {"file_path": str(other)}}, home)
    assert (code, err.strip()) == (_ALLOW, "")

    code, _ = _run(ecosystem, "advance",
                   {"tool_name": "Bash", "cwd": str(repo),
                    "tool_input": {"command": "git status --porcelain"}}, home)
    assert code == _ALLOW


@pytest.mark.parametrize("ecosystem", _SHIPPED)
def test_the_shipped_gate_allows_when_it_cannot_resolve_anything(tmp_path, ecosystem):
    """No registry, no state, no idea — and therefore no opinion. A hook that guessed here would
    block people whose projects it has never heard of."""
    code, _ = _run(ecosystem, "advance",
                   {"tool_name": "Bash", "cwd": str(tmp_path),
                    "tool_input": {"command": "python3 tools/state_patch.py apply "
                                              "--set current_phase=design --confirm"}}, tmp_path)
    assert code == _ALLOW
