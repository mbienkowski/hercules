"""Tests that verify the skill list is complete and follows the plugin contract."""

import re

import pytest

from hercules.methodology.token_counter import count_tokens


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

_SKILL_TOKEN_LIMIT = 900
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

        assert "use " in lower or "use in" in lower, (
            f"{path.parent.name}/SKILL.md description must say when to use the skill"
        )
        assert "code-of-conduct.md" in md, (
            f"{path.parent.name}/SKILL.md must reference code-of-conduct.md"
        )

        if name in _ACTIVE_SKILLS:
            assert "precondition" in lower, (
                f"{path.parent.name}/SKILL.md (active skill) must declare a Preconditions clause"
            )
            assert "stop" in lower, (
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


def test_all_skills_stay_within_their_token_budget(repo_root, skill_files):
    """Each skill file must stay under {_SKILL_TOKEN_LIMIT} tokens (cl100k_base)."""
    # Given
    over_budget = []

    # When
    for path in skill_files:
        n = count_tokens(path.read_text())
        if n > _SKILL_TOKEN_LIMIT:
            over_budget.append(f"{path.parent.name}/SKILL.md: {n} tokens (limit {_SKILL_TOKEN_LIMIT})")

    # Then
    assert not over_budget, (
        "Skill files over token budget:\n" + "\n".join(f"  {v}" for v in over_budget)
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
        "session-summary must read delivered_specs from the home-config project entry"
    assert "hercules-config.json" in md, \
        "session-summary must read machine-local state from ~/.hercules/hercules-config.json"
    assert ".context" not in md, \
        "session-summary must not reference the removed docs/.context file"
    assert "handoff" in md.lower(), \
        "session-summary must produce a handoff note"
