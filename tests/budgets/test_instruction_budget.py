"""Instruction-budget gate — no single agent call may receive too many instructions.

What counts as "one instruction":
  - Bullet list item  (- text or * text)
  - Numbered list item  (1. text, 0. text)
  - Bold-labelled instruction block  (**Step 4a —**, **Group A —**, etc.)
  - Numbered rule inside a fenced code block (used in the a2a core)

This is a *section-level* count, not atomic-sentence level.  One counted unit
typically contains 2–4 atomic directives.  Empirically that gives:
  sub-agent heuristic ≈ 20  →  ~50 atomic directives
  orchestrator realistic ≈ 43 →  ~110 atomic directives

Gates are set relative to the "150 hard / 120 ideal" per-agent ceiling the user
specified, scaled to the heuristic:  150 / 3 ≈ 50, 120 / 3 ≈ 40.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ── Thresholds ────────────────────────────────────────────────────────────────
# Heuristic instruction blocks (1 block ≈ 2–4 atomic directives).
# Gate = user's atomic ceiling ÷ 3 (conservative), rounded up to nearest 5.
_SUB_AGENT_GATE   = 50   # agent .md + a2a injected core + CLAUDE.md
_ORCHESTRATOR_GATE = 55  # CLAUDE.md + heaviest command + both protocols (no skills)
_SKILL_GATE        = 20  # per individual skill invocation


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_instructions(text: str) -> int:
    """Count discrete instruction units in *text*."""
    lines = text.splitlines()
    count = 0
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
        if (
            re.match(r'^[-*]\s+\S', stripped)            # bullet
            or re.match(r'^\d+\.\s+\S', stripped)        # numbered outside code
            or re.match(r'^\*\*[A-Z0-9]', stripped)      # bold label (**4a —, **Group —)
            or (in_code and re.match(r'^\d+\.\s+', stripped))  # rule inside code block
        ):
            count += 1
    return count


def _extract_section(text: str, start: str, stop: str | None = None) -> str:
    """Return the slice of *text* between *start* header and optional *stop* header."""
    idx = text.find(start)
    if idx == -1:
        return ""
    if stop:
        end = text.find(stop, idx + len(start))
        return text[idx:end] if end != -1 else text[idx:]
    return text[idx:]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def _a2a_core_n(repo_root: Path) -> int:
    """Instruction count of the Agent-Injected Core section only (what sub-agents receive)."""
    a2a = (repo_root / "plugin/protocols/a2a-communication-protocol.md").read_text()
    core = _extract_section(a2a, "## Agent-Injected Core", "## Orchestrator Section")
    return _count_instructions(core)


@pytest.fixture(scope="module")
def _claude_md_n(repo_root: Path) -> int:
    return _count_instructions((repo_root / "plugin/CLAUDE.md").read_text())


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_sub_agent_instruction_budget(repo_root, agent_files, _a2a_core_n, _claude_md_n):
    """Every sub-agent call must stay under _SUB_AGENT_GATE instruction blocks.

    A sub-agent receives: its own .md (system prompt) + the injected a2a core
    (prepended to every delegation prompt) + plugin/CLAUDE.md.
    """
    for agent_file in agent_files:
        agent_n = _count_instructions(agent_file.read_text())
        total = agent_n + _a2a_core_n + _claude_md_n
        assert total <= _SUB_AGENT_GATE, (
            f"{agent_file.name}: {total} instruction blocks in sub-agent context "
            f"(agent:{agent_n} + a2a-core:{_a2a_core_n} + CLAUDE.md:{_claude_md_n}) "
            f"— gate is {_SUB_AGENT_GATE}. "
            f"Trim the agent file or the a2a injected core."
        )


def _all_protocols_n(repo_root: Path) -> int:
    """Instruction blocks across EVERY shipped protocol — a new protocol file must not slip
    into the orchestrator's context uncounted (they are all loadable during a phase)."""
    return sum(
        _count_instructions(p.read_text())
        for p in sorted((repo_root / "plugin/protocols").glob("*.md"))
    )


def test_orchestrator_instruction_budget(repo_root, _claude_md_n):
    """The main orchestrator context must stay under _ORCHESTRATOR_GATE.

    Includes: CLAUDE.md + heaviest command (build.md) + ALL protocols (a2a, debate,
    workflow — any of them can be in context during a phase).  Skills are excluded —
    they load one-at-a-time.
    """
    protocols_n = _all_protocols_n(repo_root)
    # Worst-case command = build.md (most instructions of all four commands)
    build_n = _count_instructions((repo_root / "plugin/commands/build.md").read_text())

    total = _claude_md_n + build_n + protocols_n
    assert total <= _ORCHESTRATOR_GATE, (
        f"Main orchestrator context: {total} instruction blocks "
        f"(CLAUDE.md:{_claude_md_n} + build.md:{build_n} "
        f"+ protocols:{protocols_n}) "
        f"— gate is {_ORCHESTRATOR_GATE}. "
        f"Trim a protocol or the build command."
    )


def test_skill_instruction_budget(skill_files):
    """Each skill loaded during a Build session must stay under _SKILL_GATE."""
    for skill_file in skill_files:
        n = _count_instructions(skill_file.read_text())
        assert n <= _SKILL_GATE, (
            f"{skill_file.parent.name}/SKILL.md: {n} instruction blocks "
            f"— gate is {_SKILL_GATE}. Trim or split the skill."
        )


def test_no_command_exceeds_orchestrator_contribution(repo_root, command_files, _claude_md_n):
    """Any single command file, when added to the always-loaded context,
    must not by itself push the orchestrator over _ORCHESTRATOR_GATE.

    Ensures a future heavy command can't silently blow the budget.
    """
    base = _claude_md_n + _all_protocols_n(repo_root)

    for cmd_file in command_files:
        cmd_n = _count_instructions(cmd_file.read_text())
        total = base + cmd_n
        assert total <= _ORCHESTRATOR_GATE, (
            f"{cmd_file.name}: orchestrator total {total} blocks with this command "
            f"(base:{base} + cmd:{cmd_n}) — gate is {_ORCHESTRATOR_GATE}."
        )
