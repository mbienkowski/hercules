"""Independent review — the two true self-judgment gates (Design coverage, Build traceability)
are performed by a freshly-spawned `cynical-reviewer` reading the source directly, never by the
producing session. Pins the swap so a green suite can't hide a lingering self-review (QA panel Blocker).

Checked across EVERY shipped edition (claude-code, opencode, cursor). Each edition names the reviewer
with its own agent namespace (`hercules:` on Claude Code, bare elsewhere), so the assertions are
namespace-aware rather than hardcoded to the Claude tree.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TREES = ("claude-code", "opencode", "cursor")

# Self-judgment verbs that would mean the MAIN agent still judges its own artifact at the gate.
_SELF_VERBS = ("self-scan", "you verify", "you check", "self-review")


def _dist(tree: str) -> Path:
    return REPO / "dist" / tree


def _agent_ns(tree: str) -> str:
    cfg = json.loads((REPO / "src" / "targets" / tree / "config.json").read_text(encoding="utf-8"))
    return cfg["vars"]["agent_ns"]


def _slice(text: str, start: str, end: str | None) -> str:
    i = text.index(start)
    j = text.index(end, i) if end else len(text)
    return text[i:j]


def _coverage_slice(tree: str) -> str:
    md = (_dist(tree) / "commands" / "design.md").read_text(encoding="utf-8")
    step7 = _slice(md, "## Step 7", "## Step 8")
    # Coverage is the portion after the (in-session, mechanical) implementability check.
    return _slice(step7, "coverage", None)


def _traceability_slice(tree: str) -> str:
    md = (_dist(tree) / "commands" / "build.md").read_text(encoding="utf-8")
    return next(p for p in md.split("\n") if "**Traceability" in p or "Traceability." in p)


# ── Positive: the judgment is delegated to a fresh reviewer reading source ────
@pytest.mark.parametrize("tree", TREES)
def test_design_coverage_is_judged_by_a_fresh_reviewer_not_the_author(tree):
    """When a design is checked for full requirement coverage, that check must be done by a
    newly-spawned reviewer reading the requirements and source directly, not by the same session
    that wrote the design. Holds in every edition Hercules ships."""
    s = _coverage_slice(tree)
    reviewer = f"{_agent_ns(tree)}cynical-reviewer"
    assert reviewer in s, f"{tree}: coverage gate must spawn {reviewer}"
    assert "workflow-protocol.md#packet" in s, f"{tree}: coverage gate must compose the delegation packet"
    assert "Independent review" in s, f"{tree}: coverage gate must reference § Independent review"
    assert "business-requirements" in s, f"{tree}: reviewer must read the requirements source directly"


@pytest.mark.parametrize("tree", TREES)
def test_build_traceability_is_judged_by_a_fresh_reviewer_not_the_author(tree):
    """When finished code is checked for traceability back to its spec, that check must be done by a
    newly-spawned reviewer reading the source directly, not by the session that wrote the code."""
    s = _traceability_slice(tree)
    reviewer = f"{_agent_ns(tree)}cynical-reviewer"
    assert reviewer in s, f"{tree}: traceability gate must spawn {reviewer}"
    assert "workflow-protocol.md#packet" in s, f"{tree}: traceability gate must compose the delegation packet"
    assert "Independent review" in s, f"{tree}: traceability gate must reference § Independent review"


# ── Negative: no self-judgment verb survives at either converted gate (the Blocker) ──
@pytest.mark.parametrize("tree", TREES)
def test_neither_gate_can_slip_back_into_self_judgment(tree):
    """Neither the coverage check nor the traceability check may contain wording that tells the
    author to verify or scan its own work — else the independent checks quietly become
    self-certification again."""
    for name, s in (("coverage", _coverage_slice(tree)), ("traceability", _traceability_slice(tree))):
        low = s.lower()
        for v in _SELF_VERBS:
            assert v not in low, f"{tree} {name} gate still carries self-review verb {v!r}"


# ── The reviewer is a real, shared-across-ecosystems agent ───────────────────
@pytest.mark.parametrize("tree", TREES)
def test_independent_reviewer_is_available_wherever_hercules_ships(tree):
    """The independent reviewer that both gates depend on must actually be present in every packaged
    edition — as an agent file (Claude/OpenCode) or a Cursor subagent, both under agents/."""
    assert (_dist(tree) / "agents" / "cynical-reviewer.md").is_file(), \
        f"cynical-reviewer must ship to dist/{tree}/agents/"


# ── Cursor: the reviewer is an isolated SUBAGENT (not a same-context rule) ────
def test_cursor_reviewer_is_a_read_locked_subagent_not_a_rule():
    """On Cursor the guarantee only holds if the reviewer is a real subagent (isolated context) —
    a rule would load into the authoring context and become self-review. Structurally: it lives at
    agents/ (never rules/), carries no alwaysApply, and is read-locked."""
    agent = _dist("cursor") / "agents" / "cynical-reviewer.md"
    text = agent.read_text(encoding="utf-8")
    assert text.startswith("---\nname: cynical-reviewer\n"), "must be a subagent with a name"
    assert "readonly: true" in text, "reviewer subagent must be read-locked"
    assert "alwaysApply" not in text, "a reviewer is a subagent, not an always-applied rule"
    assert not (_dist("cursor") / "rules" / "cynical-reviewer.mdc").exists(), \
        "the reviewer must not also ship as a same-context rule"


def test_cursor_gates_demand_a_handshake_or_halt():
    """Cursor cannot force the spawn, so both gates must require an explicit reviewer handshake and
    HALT if it is absent — turning a silent self-review into a loud stop."""
    for cmd in ("design", "build"):
        text = (_dist("cursor") / "commands" / f"{cmd}.md").read_text(encoding="utf-8")
        assert "@cynical-reviewer" in text, f"cursor {cmd}: must instruct an explicit reviewer spawn"
        assert "HALT and tell the user" in text, f"cursor {cmd}: must HALT when the handshake is missing"
