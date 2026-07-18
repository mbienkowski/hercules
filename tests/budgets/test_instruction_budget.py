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

Gates are set relative to the ~150-directive per-agent adherence ceiling, scaled to the
heuristic (÷3) — and the delegate gate reserves the 30–40 directives the project
code-of-conduct spends on top of shipped content: (150 − 40) / 3 ≈ 35.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ── Thresholds ────────────────────────────────────────────────────────────────
# Heuristic instruction blocks (1 block ≈ 2–4 atomic directives).
# Gate = user's atomic ceiling ÷ 3 (conservative), rounded up to nearest 5.
_SUB_AGENT_GATE   = 35   # agent .md + delegation packet + a2a injected core (CoC reserved)
_ORCHESTRATOR_GATE = 55  # CLAUDE.md + heaviest command + both protocols (no skills)
_SKILL_GATE        = 20  # per individual skill invocation


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_instruction_blocks(text: str) -> int:
    # Deliberately DIFFERENT semantics from tests/metrics/markdown_metrics.count_instructions:
    # this budget counts numbered items inside fences and bold labels too, because a fenced
    # example still costs the runtime agent attention. Keep the names distinct.
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
    a2a = (repo_root / "dist/claude-code/protocols/a2a-communication-protocol.md").read_text()
    core = _extract_section(a2a, "## Agent-Injected Core", "## Orchestrator Section")
    return _count_instruction_blocks(core)


@pytest.fixture(scope="module")
def _claude_md_n(repo_root: Path) -> int:
    return _count_instruction_blocks((repo_root / "dist/claude-code/CLAUDE.md").read_text())


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_a_single_helper_agent_is_never_handed_too_many_instructions(repo_root, agent_files, _a2a_core_n, _claude_md_n):
    """When work is delegated to a helper agent, everything it is given to read -- its own
    briefing, the material that gets attached to every delegated task, and the shared project
    rules -- is added up and must stay under the safe limit. Past that point a helper agent
    starts missing or ignoring some of what it was told to do."""
    for agent_file in agent_files:
        agent_n = _count_instruction_blocks(agent_file.read_text())
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
        _count_instruction_blocks(p.read_text())
        for p in sorted((repo_root / "dist/claude-code/protocols").glob("*.md"))
    )


def test_the_main_controller_is_never_handed_too_many_instructions_at_once(repo_root, _claude_md_n):
    """The main controller's worst-case reading load -- the project's always-on rules, its
    heaviest single command, and every set of process rules that could be active during a
    run -- must stay under the safe instruction limit. Skills are left out of this count
    because they are only loaded one at a time, never all together. Crossing the limit means
    the controller can start losing track of its own rules mid-run."""
    protocols_n = _all_protocols_n(repo_root)
    # Worst-case command = build.md (most instructions of all four commands)
    build_n = _count_instruction_blocks((repo_root / "dist/claude-code/commands/build.md").read_text())

    total = _claude_md_n + build_n + protocols_n
    assert total <= _ORCHESTRATOR_GATE, (
        f"Main orchestrator context: {total} instruction blocks "
        f"(CLAUDE.md:{_claude_md_n} + build.md:{build_n} "
        f"+ protocols:{protocols_n}) "
        f"— gate is {_ORCHESTRATOR_GATE}. "
        f"Trim a protocol or the build command."
    )


def test_each_individually_loaded_skill_stays_within_its_own_limit(skill_files):
    """Every skill that could be loaded on demand during a work session is checked on its own,
    since only one skill is ever loaded at a time. A skill that grows past the safe limit
    risks having some of its steps skipped or garbled when it is actually put to use."""
    for skill_file in skill_files:
        n = _count_instruction_blocks(skill_file.read_text())
        assert n <= _SKILL_GATE, (
            f"{skill_file.parent.name}/SKILL.md: {n} instruction blocks "
            f"— gate is {_SKILL_GATE}. Trim or split the skill."
        )


def test_adding_any_single_command_never_pushes_the_controller_past_its_limit(repo_root, command_files, _claude_md_n):
    """Every command is checked one at a time against the instructions that are always loaded,
    to confirm that no single command could, by itself, push the main controller past its safe
    instruction limit. This catches a future heavyweight command silently blowing the budget
    before anyone notices."""
    base = _claude_md_n + _all_protocols_n(repo_root)

    for cmd_file in command_files:
        cmd_n = _count_instruction_blocks(cmd_file.read_text())
        total = base + cmd_n
        assert total <= _ORCHESTRATOR_GATE, (
            f"{cmd_file.name}: orchestrator total {total} blocks with this command "
            f"(base:{base} + cmd:{cmd_n}) — gate is {_ORCHESTRATOR_GATE}."
        )
