"""Tests that verify the skill list is complete and follows the plugin contract."""

import json
import re

import pytest


_SKILL_LIST = [
    "solution-complexity-scoring", "code-of-conduct-generator",
    "learnings", "write-test-scenarios", "session-summary",
]

_ACTIVE_SKILLS = frozenset({
    "solution-complexity-scoring", "code-of-conduct-generator", "learnings",
    "write-test-scenarios", "session-summary",
})

_SKILL_NAME_RE = re.compile(r"(?m)^name:\s*(\S+)\s*$")

_STACK_LITERAL_PATTERNS = [
    re.compile(r"\bSpring\b"), re.compile(r"\bHibernate\b"),
    re.compile(r"\bLiquibase\b"), re.compile(r"\bFlyway\b"),
    re.compile(r"\bMapStruct\b"), re.compile(r"\bLombok\b"),
    re.compile(r"\bReact\b"), re.compile(r"\bZustand\b"),
    re.compile(r"\bRedux\b"), re.compile(r"\bPinia\b"),
    re.compile(r"\bJotai\b"), re.compile(r"\bDjango\b"),
    re.compile(r"\bRails\b"), re.compile(r"\bSQLAlchemy\b"),
    re.compile(r"\bPrisma\b"), re.compile(r"\bActiveRecord\b"),
    re.compile(r"@anthropic-ai"),
]

_BARE_SUBCOMMAND_RE = re.compile(r"hercules\s+(origin-trace|sessions)\b")


def test_all_five_skills_are_present(repo_root):
    """All 5 listed skills must have a corresponding SKILL.md in skills/."""
    # Given
    existing = {p.parent.name for p in (repo_root / "plugin" / "skills").glob("*/SKILL.md")}

    # When
    missing = [n for n in _SKILL_LIST if n not in existing]
    extra = [n for n in existing if n not in _SKILL_LIST]

    # Then
    assert not missing, f"Listed skills missing from skills/: {missing}"
    assert not extra, (
        f"skills/ contains directories not in the canonical list: {extra}"
    )


def test_each_skill_file_declares_its_purpose_and_preconditions(repo_root, skill_files):
    """Every skill must declare its use-case and active skills must define a precondition stop clause."""
    # Given / When / Then
    for path in skill_files:
        md = path.read_text()
        lower = md.lower()
        name = path.parent.name

        assert md.startswith("---"), f"{path.parent.name}/SKILL.md must open with YAML frontmatter"

        m = _SKILL_NAME_RE.search(md)
        assert m is not None, f"{path.parent.name}/SKILL.md frontmatter missing `name:`"
        assert m.group(1) == name, (
            f"{path.parent.name}/SKILL.md frontmatter name={m.group(1)!r} must match directory {name!r}"
        )
        assert "description:" in md, f"{path.parent.name}/SKILL.md frontmatter missing `description:`"

        desc_m = re.search(r"(?m)^description:\s*(.+)$", md)
        assert desc_m, f"{path.parent.name}/SKILL.md frontmatter missing a description value"
        desc = desc_m.group(1).lower()
        assert any(t in desc for t in ("use ", "use in", "use on", "use when", "use to")), (
            f"{path.parent.name}/SKILL.md description must state WHEN to use the skill"
        )
        assert "code-of-conduct.md" in md, (
            f"{path.parent.name}/SKILL.md must reference code-of-conduct.md"
        )

        if name in _ACTIVE_SKILLS:
            assert "precondition" in lower, (
                f"{path.parent.name}/SKILL.md (active skill) must declare a Preconditions clause"
            )
            assert re.search(r"\bstop\b", lower), (
                f"{path.parent.name}/SKILL.md (active skill) must hard-stop on precondition miss"
            )


def test_skills_carry_no_framework_assumptions(repo_root, skill_files):
    """No shipped skill must name a concrete framework or stack — skills stay generic."""
    # Given
    violations = []

    # When
    for path in skill_files:
        md = path.read_text()
        for pattern in _STACK_LITERAL_PATTERNS:
            hit = pattern.search(md)
            if hit:
                violations.append(f"{path.parent.name}/SKILL.md: matched {hit.group()!r}")

    # Then
    assert not violations, (
        "Skills contain stack literals:\n" + "\n".join(f"  {v}" for v in violations)
    )


def test_hercules_commands_use_double_dash_prefix(repo_root, command_files, skill_files, agent_files):
    """All plugin docs must use 'hercules --<subcommand>', never the bare form.

    The bare form is forwarded to claude as a prompt instead of running natively.
    This test walks commands/, skills/, AND agents/ so none can drift.
    """
    # Given
    all_files = list(command_files) + list(skill_files) + list(agent_files)
    violations = []

    # When
    for path in all_files:
        md = path.read_text()
        hit = _BARE_SUBCOMMAND_RE.search(md)
        if hit:
            violations.append(f"{path.relative_to(repo_root)}: {hit.group()!r}")

    # Then
    assert not violations, (
        "Files using bare subcommand form (should be 'hercules --<name>'):\n"
        + "\n".join(f"  {v}" for v in violations)
    )



def test_session_summary_skill_exists(repo_root):
    """session-summary must exist as a plugin skill for team handoff support."""
    skill_file = repo_root / "plugin" / "skills" / "session-summary" / "SKILL.md"
    assert skill_file.exists(), "plugin/skills/session-summary/SKILL.md must exist"


def test_session_summary_skill_covers_handoff_fields(repo_root):
    """session-summary SKILL.md must reference delivered_specs and handoff context."""
    md = (repo_root / "plugin" / "skills" / "session-summary" / "SKILL.md").read_text()
    assert "delivered_specs" in md, \
        "session-summary must read delivered_specs from the per-project state file"
    assert "~/.hercules/" in md and "state" in md, \
        "session-summary must read machine-local state from ~/.hercules/ (the per-project state file)"
    assert "docs/.context" not in md, \
        "session-summary must not reference the removed docs/.context file"
    assert "handoff" in md.lower(), \
        "session-summary must produce a handoff note"


def test_skill_list_matches_plugin_settings(repo_root):
    """_SKILL_LIST and plugin/settings.json skills[] must stay in sync."""
    settings = json.loads((repo_root / "plugin" / "settings.json").read_text())
    manifest = settings.get("skills", [])
    assert sorted(manifest) == sorted(_SKILL_LIST), (
        "plugin/settings.json skills[] and _SKILL_LIST are out of sync.\n"
        f"  In settings.json only: {sorted(set(manifest) - set(_SKILL_LIST))}\n"
        f"  In _SKILL_LIST only: {sorted(set(_SKILL_LIST) - set(manifest))}"
    )


_COC_GENERATOR = "plugin/skills/code-of-conduct-generator/SKILL.md"


def test_code_of_conduct_generator_uses_plan_mode(repo_root):
    """code-of-conduct-generator must use plan mode so the user reviews the full CoC before it is written."""
    md = (repo_root / _COC_GENERATOR).read_text()
    assert "EnterPlanMode" in md, \
        "code-of-conduct-generator must call EnterPlanMode to present the CoC draft for review"
    assert "ExitPlanMode" in md, \
        "code-of-conduct-generator must call ExitPlanMode after the user approves"


def test_code_of_conduct_generator_asks_minimum_questions(repo_root):
    """code-of-conduct-generator must ask at least 5 questions in a single batch — not a trickle."""
    md = (repo_root / _COC_GENERATOR).read_text()
    lower = md.lower()
    assert "5" in md or "five" in lower, \
        "code-of-conduct-generator must ask at least 5 questions"
    assert "batch" in lower or "single" in lower or "at once" in lower or "trickle" in lower, \
        "code-of-conduct-generator must send all questions in one message, not trickle them"


def test_code_of_conduct_generator_prohibits_attribution(repo_root):
    """The generated CoC must not contain Hercules/AI attribution — the skill must state this explicitly."""
    md = (repo_root / _COC_GENERATOR).read_text()
    lower = md.lower()
    has_prohibition = (
        "no hercules" in lower
        or "no ai" in lower
        or "no generator" in lower
        or "no credit" in lower
        or "no mention" in lower
        or "attribution" in lower
    )
    assert has_prohibition, \
        "code-of-conduct-generator must explicitly prohibit AI/Hercules attribution in the output file"


def test_code_of_conduct_generator_defines_required_sections(repo_root):
    """code-of-conduct-generator must define Architecture, Testing, Quality Gates, and Delivery as required
    sections, each with a 'why' explanation before the bullets."""
    md = (repo_root / _COC_GENERATOR).read_text()
    lower = md.lower()
    assert "architecture" in lower, \
        "code-of-conduct-generator must include an Architecture section in the output structure"
    assert "testing" in lower, \
        "code-of-conduct-generator must include a Testing section in the output structure"
    assert "quality" in lower or "gate" in lower, \
        "code-of-conduct-generator must include a Quality Gates section (name may vary)"
    assert "mutation" in lower, \
        "code-of-conduct-generator must mention mutation testing in the Quality Gates section"
    assert "delivery" in lower, \
        "code-of-conduct-generator must include a Delivery section in the output structure"
    assert "pattern" in lower, \
        "code-of-conduct-generator must scan for and document design patterns in Architecture"
    assert "why" in lower or "reason" in lower or "explain" in lower, \
        "code-of-conduct-generator must instruct sections to open with a 'why' explanation"


def test_code_of_conduct_generator_detects_file_naming_convention(repo_root):
    """The generator writes the ONE filename every command and agent reads — always the
    lowercase `code-of-conduct.md`; a casing-detection rule would produce a file nobody reads."""
    md = (repo_root / _COC_GENERATOR).read_text()
    assert "Always `code-of-conduct.md`" in md, \
        "the generator must always write code-of-conduct.md — the only name consumers read"
    assert "uppercase stems" not in md, \
        "no casing detection: an uppercase output filename would be ignored by every consumer"


def test_code_of_conduct_generator_handles_existing_coc_safely(repo_root):
    """When CoC exists, generator must update incrementally — never restructure or delete content."""
    md = (repo_root / _COC_GENERATOR).read_text()
    lower = md.lower()
    assert "existing" in lower or "re-run" in lower or "update mode" in lower, \
        "code-of-conduct-generator must describe behaviour when a CoC already exists"
    assert "never" in lower and any(w in lower for w in ("reorder", "restructure", "delete", "rename")), \
        "code-of-conduct-generator must explicitly prohibit restructuring an existing CoC"
    assert "gap" in lower or "missing" in lower or "conflict" in lower, \
        "code-of-conduct-generator must perform gap analysis when re-running against an existing CoC"
    assert "addition" in lower or "append" in lower or "insert" in lower, \
        "code-of-conduct-generator must describe the additions-only update strategy"


def test_coc_generator_output_filename_is_one_the_plugin_reads(read_file):
    """Every command and agent reads the literal `code-of-conduct.md`; the generator must never
    propose an uppercase output filename no consumer looks for."""
    skill = read_file("plugin/skills/code-of-conduct-generator/SKILL.md")
    assert "→ `CODE_OF_CONDUCT.md`" not in skill, \
        "generator must never PROPOSE an uppercase output filename — no consumer reads it"
    assert "Always `code-of-conduct.md`" in skill, \
        "the output filename rule must be the lowercase name every consumer reads"


def test_learnings_skill_names_the_phase_that_invokes_it(read_file):
    """build.md invokes learnings at Build close-out (every tier); a 'ship time' trigger routes
    the model to Ship — which never invokes it and runs prompt-free — so nothing gets written."""
    skill = read_file("plugin/skills/learnings/SKILL.md")
    if "ship time" in skill.lower():
        assert "learnings" in read_file("plugin/commands/ship.md"), \
            "learnings anchors to 'ship time' but only Build invokes it — rephrase the trigger"


def test_generator_states_the_directive_budget(read_file):
    """Every agent reads the whole project CoC on top of its ~100-directive base load,
    and instruction-following degrades measurably past ~150 total — the generator must
    aim for 30–40 directives, allow up to 50 for big repos, and never exceed 70."""
    skill = read_file("plugin/skills/code-of-conduct-generator/SKILL.md")
    assert "30" in skill and "40" in skill, "the generator must state the 30–40 sweet spot"
    assert "50" in skill, "…the conditional ceiling for big repos"
    assert "70" in skill, "…and the hard never-exceed line"
