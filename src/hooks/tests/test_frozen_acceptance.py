"""The phase-acceptance backstop — ``frozen_tests.frozen_drift``.

Tool-time hooks can be evaded, and on an advisory IDE (integrated development environment) path they
are deliberately non-blocking. ``frozen_drift`` is the deterministic check run *before a spec is
retired*: it re-hashes each frozen test against the baseline recorded at freeze time and reports any
that changed or vanished without a live ``frozen_override``. These pin it directly, independent of any
host's edit path.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from frozen_tests import frozen_drift  # noqa: E402
from hercules_state import canon  # noqa: E402


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _session(proj: Path, baseline: dict, override=None) -> tuple[dict, list]:
    session = {
        "current_phase": "build", "current_spec": "spec-1.md", "current_spec_round": 1,
        "frozen_test_files": list(baseline), "frozen_baseline": baseline,
    }
    if override is not None:
        session["frozen_override"] = override
    return session, [canon(str(proj))]


def _freeze(proj: Path, rel: str, content: str) -> str:
    p = proj / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return _sha(content)


def test_no_drift_when_the_file_still_matches_its_baseline(tmp_path):
    proj = tmp_path / "proj"
    h = _freeze(proj, "tests/test_frozen.py", "def test_x():\n    assert real()\n")
    session, roots = _session(proj, {"tests/test_frozen.py": h})
    assert frozen_drift(session, roots) == []


def test_a_tampered_frozen_test_is_reported_as_drift(tmp_path):
    """The acceptance test was weakened after freeze (no override) — the retire gate must catch it."""
    proj = tmp_path / "proj"
    baseline = _freeze(proj, "tests/test_frozen.py", "def test_x():\n    assert real()\n")
    (proj / "tests" / "test_frozen.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    session, roots = _session(proj, {"tests/test_frozen.py": baseline})
    assert frozen_drift(session, roots) == ["tests/test_frozen.py"]


def test_a_sanctioned_override_edit_is_not_drift(tmp_path):
    """A change the user explicitly sanctioned via ``frozen_override`` is legitimate, not tampering."""
    proj = tmp_path / "proj"
    baseline = _freeze(proj, "tests/test_frozen.py", "def test_x():\n    assert status == 200\n")
    (proj / "tests" / "test_frozen.py").write_text("def test_x():\n    assert status == 201\n",
                                                    encoding="utf-8")
    override = {"files": ["tests/test_frozen.py"], "spec": "spec-1.md", "round": 1,
                "reason": "user: 'the expected status is 201 not 200 — fix the test'"}
    session, roots = _session(proj, {"tests/test_frozen.py": baseline}, override=override)
    assert frozen_drift(session, roots) == []


def test_a_deleted_frozen_test_counts_as_drift_failclosed(tmp_path):
    """Deleting the acceptance test is tampering too — a vanished frozen file fails closed."""
    proj = tmp_path / "proj"
    baseline = _freeze(proj, "tests/test_frozen.py", "def test_x():\n    assert real()\n")
    (proj / "tests" / "test_frozen.py").unlink()
    session, roots = _session(proj, {"tests/test_frozen.py": baseline})
    assert frozen_drift(session, roots) == ["tests/test_frozen.py"]


def test_no_baseline_recorded_means_no_drift(tmp_path):
    """A session with no ``frozen_baseline`` (older state, or nothing frozen) yields no drift — the
    gate is additive and never invents a failure."""
    proj = tmp_path / "proj"
    session = {"current_phase": "build", "current_spec": "spec-1.md", "current_spec_round": 1}
    assert frozen_drift(session, [canon(str(proj))]) == []


def test_multiple_frozen_files_report_only_the_drifted_one(tmp_path):
    proj = tmp_path / "proj"
    a = _freeze(proj, "tests/test_a.py", "A-original\n")
    b = _freeze(proj, "tests/test_b.py", "B-original\n")
    (proj / "tests" / "test_a.py").write_text("A-tampered\n", encoding="utf-8")
    session, roots = _session(proj, {"tests/test_a.py": a, "tests/test_b.py": b})
    assert frozen_drift(session, roots) == ["tests/test_a.py"]


def test_multi_root_tamper_under_any_root_is_drift_failclosed(tmp_path):
    """Monorepo/multi-service: the same frozen path resolves under more than one root. Tampering ONE
    root's copy must be caught even though the OTHER still matches — fail-closed, matching
    frozen_candidates' "under any root counts" rule."""
    root_a, root_b = tmp_path / "svcA", tmp_path / "svcB"
    h = _freeze(root_a, "tests/test_frozen.py", "def test_x():\n    assert real()\n")
    _freeze(root_b, "tests/test_frozen.py", "def test_x():\n    assert real()\n")  # identical baseline
    (root_b / "tests" / "test_frozen.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    session = {"current_phase": "build", "current_spec": "spec-1.md", "current_spec_round": 1,
               "frozen_test_files": ["tests/test_frozen.py"],
               "frozen_baseline": {"tests/test_frozen.py": h}}
    assert frozen_drift(session, [canon(str(root_a)), canon(str(root_b))]) == ["tests/test_frozen.py"]


def test_a_frozen_file_with_no_baseline_hash_is_drift_when_the_backstop_is_active(tmp_path):
    """A path in ``frozen_test_files`` but missing from a non-empty ``frozen_baseline`` cannot be
    checked at all, so it counts as drift rather than silently passing."""
    proj = tmp_path / "proj"
    a = _freeze(proj, "tests/test_a.py", "A-original\n")
    _freeze(proj, "tests/test_b.py", "B-original\n")  # exists, but never baselined
    session = {"current_phase": "build", "current_spec": "spec-1.md", "current_spec_round": 1,
               "frozen_test_files": ["tests/test_a.py", "tests/test_b.py"],
               "frozen_baseline": {"tests/test_a.py": a}}  # test_b.py absent
    assert frozen_drift(session, [canon(str(proj))]) == ["tests/test_b.py"]


# --- The sanctioned correct-the-test path (build.md Step 5 re-baseline + Step 10 mandatory clear) ---
# The behaviour is doctrine-level (build.md); these pin the frozen_drift contract it rests on: the
# grant->edit->clear-override->retire path, and the list(baseline) fallback that makes clearing
# frozen_baseline mandatory.

def test_a_sanctioned_correction_that_rebaselined_is_not_drift(tmp_path):
    """After a sanctioned grant, Build re-baselines the corrected file in the same atomic write that
    CLEARS the override (build.md Step 5). At retire the override is gone, so only the re-baselined hash
    stands between a legitimate correction and a false HALT."""
    proj = tmp_path / "proj"
    _freeze(proj, "tests/test_frozen.py", "def test_x():\n    assert status == 200\n")
    corrected = "def test_x():\n    assert status == 201\n"
    (proj / "tests" / "test_frozen.py").write_text(corrected, encoding="utf-8")
    session, roots = _session(proj, {"tests/test_frozen.py": _sha(corrected)})  # re-based; override cleared
    assert frozen_drift(session, roots) == []


def test_a_correction_left_unrebaselined_would_false_halt(tmp_path):
    """If Build edits under a sanctioned override but FAILS to re-baseline before clearing it, retire
    sees corrected bytes against a stale baseline with no active override — a false "tampered acceptance
    test" HALT. Pins that failure mode so a dropped Step-5 re-baseline is caught."""
    proj = tmp_path / "proj"
    baseline = _freeze(proj, "tests/test_frozen.py", "def test_x():\n    assert status == 200\n")
    (proj / "tests" / "test_frozen.py").write_text("def test_x():\n    assert status == 201\n",
                                                    encoding="utf-8")
    session, roots = _session(proj, {"tests/test_frozen.py": baseline})  # baseline NOT updated, no override
    assert frozen_drift(session, roots) == ["tests/test_frozen.py"]


def test_a_stale_baseline_left_after_retire_rechecks_retired_paths(tmp_path):
    """Why clearing frozen_baseline at retire is MANDATORY: frozen_drift falls back to
    list(frozen_baseline) when frozen_test_files is empty, so a stale baseline makes the NEXT spec
    re-check a retired path and false-HALT."""
    proj = tmp_path / "proj"
    old = _freeze(proj, "tests/test_retired.py", "def test_x():\n    assert real()\n")
    (proj / "tests" / "test_retired.py").write_text("def test_x():\n    assert real2()\n",
                                                     encoding="utf-8")  # retired test evolved with the code
    session = {"current_phase": "build", "current_spec": "spec-2.md", "current_spec_round": 1,
               "frozen_test_files": [],                              # next spec hasn't frozen yet
               "frozen_baseline": {"tests/test_retired.py": old}}    # stale — not cleared at retire
    assert frozen_drift(session, [canon(str(proj))]) == ["tests/test_retired.py"]
