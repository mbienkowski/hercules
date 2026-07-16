"""Independent review — the two true self-judgment gates (Design coverage, Build traceability)
are performed by a freshly-spawned `cynical-reviewer` reading the source directly, never by the
producing session. Pins the swap so a green suite can't hide a lingering self-review (QA panel Blocker).

Read against dist/claude-code (the reference tree; build-check keeps opencode consistent).
"""
import re
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
def test_coverage_gate_delegates_to_cynical_reviewer():
    s = _coverage_slice()
    assert "hercules:cynical-reviewer" in s, "coverage gate must spawn the cynical-reviewer"
    assert "workflow-protocol.md#packet" in s, "coverage gate must compose the delegation packet"
    assert "Independent review" in s, "coverage gate must reference § Independent review"
    assert "business-requirements" in s, "reviewer must read the requirements source directly"


def test_traceability_gate_delegates_to_cynical_reviewer():
    s = _traceability_slice()
    assert "hercules:cynical-reviewer" in s, "traceability gate must spawn the cynical-reviewer"
    assert "workflow-protocol.md#packet" in s, "traceability gate must compose the delegation packet"
    assert "Independent review" in s, "traceability gate must reference § Independent review"


# ── Negative: no self-judgment verb survives at either converted gate (the Blocker) ──
def test_no_self_review_verb_at_converted_gates():
    for name, s in (("coverage", _coverage_slice()), ("traceability", _traceability_slice())):
        low = s.lower()
        for v in _SELF_VERBS:
            assert v not in low, f"{name} gate still carries self-review verb {v!r}"


# ── The reviewer is a real, shared-across-ecosystems agent ───────────────────
def test_reviewer_agent_exists_in_both_trees():
    for tree in ("claude-code", "opencode"):
        assert (REPO / "dist" / tree / "agents" / "cynical-reviewer.md").is_file(), \
            f"cynical-reviewer must ship to dist/{tree}"


# ── The mechanism section exists and reconciles reviewers vs advisors ────────
def test_independent_review_section_present_and_distinct_from_consent():
    skill = (CC / "skills" / "hercules-reference" / "SKILL.md").read_text(encoding="utf-8")
    assert "## Independent review" in skill, "hercules-reference must carry § Independent review"
    assert "never spawns advisors silently" in skill, "the consent rule must stay verbatim"
    # Reviewers are a distinct category (mandatory at low+, recommend-and-ask at trivial).
    assert re.search(r"reviewer", skill, re.I), "consent must distinguish reviewers from advisors"
