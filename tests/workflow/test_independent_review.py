"""Independent review — the two true self-judgment gates (Design coverage, Build traceability)
are performed by a freshly-spawned `cynical-reviewer` reading the source directly, never by the
producing session. Pins the swap so a green suite can't hide a lingering self-review (QA panel Blocker).

Read against dist/claude-code (the reference tree; build-check keeps opencode consistent).
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CC = REPO / "dist" / "claude-code"

# Self-judgment verbs that would mean the MAIN agent still judges its own artifact at the gate.
_SELF_VERBS = ("self-scan", "you verify", "you check", "self-review")


def _slice(text: str, start: str, end: str | None) -> str:
    i = text.index(start)
    j = text.index(end, i) if end else len(text)
    return text[i:j]


def _coverage_slice() -> str:
    md = (CC / "commands" / "design.md").read_text(encoding="utf-8")
    step7 = _slice(md, "## Step 7", "## Step 8")
    # Coverage is the portion after the (in-session, mechanical) implementability check.
    return _slice(step7, "coverage", None)


def _traceability_slice() -> str:
    md = (CC / "commands" / "build.md").read_text(encoding="utf-8")
    # The per-spec traceability gate paragraph (bolded "Traceability.").
    para = next(p for p in md.split("\n") if "**Traceability" in p or "Traceability." in p)
    return para


# ── Positive: the judgment is delegated to a fresh reviewer reading source ────
def test_design_coverage_is_judged_by_a_fresh_reviewer_not_the_author():
    """When a design is checked for full requirement coverage, that check must be done by a
    newly-spawned reviewer reading the requirements and source directly, not by the same session
    that wrote the design. This stops an author from grading its own work and calling it
    verified."""
    s = _coverage_slice()
    assert "hercules:cynical-reviewer" in s, "coverage gate must spawn the cynical-reviewer"
    assert "workflow-protocol.md#packet" in s, "coverage gate must compose the delegation packet"
    assert "Independent review" in s, "coverage gate must reference § Independent review"
    assert "business-requirements" in s, "reviewer must read the requirements source directly"


def test_build_traceability_is_judged_by_a_fresh_reviewer_not_the_author():
    """When finished code is checked for traceability back to its spec, that check must be done
    by a newly-spawned reviewer reading the source directly, not by the session that wrote the
    code. This stops the implementer from being the one who signs off on its own build."""
    s = _traceability_slice()
    assert "hercules:cynical-reviewer" in s, "traceability gate must spawn the cynical-reviewer"
    assert "workflow-protocol.md#packet" in s, "traceability gate must compose the delegation packet"
    assert "Independent review" in s, "traceability gate must reference § Independent review"


# ── Negative: no self-judgment verb survives at either converted gate (the Blocker) ──
def test_neither_gate_can_slip_back_into_self_judgment():
    """Neither the coverage check nor the traceability check may contain wording that tells the
    author to verify or scan its own work. If such wording crept back in, the two independent
    checks would quietly become self-certification again, undoing the whole safeguard."""
    for name, s in (("coverage", _coverage_slice()), ("traceability", _traceability_slice())):
        low = s.lower()
        for v in _SELF_VERBS:
            assert v not in low, f"{name} gate still carries self-review verb {v!r}"


# ── The reviewer is a real, shared-across-ecosystems agent ───────────────────
def test_independent_reviewer_is_available_wherever_hercules_ships():
    """The independent reviewer that both gates depend on must actually be present in every
    packaged edition of Hercules, not just one. If it were missing from an edition, that
    edition's coverage and traceability checks would have nothing real to delegate to."""
    for tree in ("claude-code", "opencode"):
        assert (REPO / "dist" / tree / "agents" / "cynical-reviewer.md").is_file(), \
            f"cynical-reviewer must ship to dist/{tree}"

