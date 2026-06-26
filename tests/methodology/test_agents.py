"""Tests that verify the specialist agent list is complete and follows the plugin contract."""

import re

import pytest

from hercules.methodology.token_counter import count_tokens


_AGENT_LIST = [
    # code / process
    "challenger", "cynical-reviewer", "lead-architect", "security-expert",
    "senior-qa-engineer", "backend-engineer", "frontend-engineer", "devops-engineer",
    "ux-ui-designer", "source-checker", "maintainer",
    # non-code / universal
    "business-analyst", "copywriter", "document-specialist",
    "simplicity-advocate",
]

_AGENT_NAME_RE = re.compile(r"(?m)^name:\s*(\S+)\s*$")

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

_AGENT_TOKEN_LIMIT = 800
_AGENT_TOKEN_WARN = 650


def test_all_specialist_agents_are_present(repo_root):
    """Every listed agent must have a corresponding file in agents/, and vice versa."""
    # Given
    existing = {p.stem for p in (repo_root / "plugin" / "agents").glob("*.md")}

    # When
    missing = [n for n in _AGENT_LIST if n not in existing]
    extra = [n for n in existing if n not in _AGENT_LIST]

    # Then
    assert not missing, f"Listed agents missing from agents/: {missing}"
    assert not extra, (
        f"agents/ contains files not in the canonical list: {extra} "
        "(add them to _AGENT_LIST + CLAUDE.md)"
    )


def test_all_agents_are_listed_in_the_project_documentation(repo_root):
    """CLAUDE.md must mention every agent name so the docs don't drift from the shipped files."""
    # Given
    doc = (repo_root / "plugin" / "CLAUDE.md").read_text()

    # When
    missing = [name for name in _AGENT_LIST if name not in doc]

    # Then
    assert not missing, f"Agents not documented in CLAUDE.md: {missing}"


def test_each_agent_file_has_the_required_structure_and_fields(repo_root, agent_files):
    """Every agent must declare frontmatter name/description/model and wire the A2A contract."""
    # Given / When / Then
    for path in agent_files:
        md = path.read_text()
        name = path.stem

        assert md.startswith("---"), f"{path.name} must open with YAML frontmatter"

        m = _AGENT_NAME_RE.search(md)
        assert m is not None, f"{path.name} frontmatter missing `name:`"
        assert m.group(1) == name, (
            f"{path.name} frontmatter name={m.group(1)!r} must match filename {name!r}"
        )
        for field in ["description:", "model:"]:
            assert field in md, f"{path.name} frontmatter missing {field!r}"

        assert "code-of-conduct.md" in md, (
            f"{path.name} must instruct the agent to read code-of-conduct.md"
        )
        assert "a2a-communication-protocol.md" in md, (
            f"{path.name} must point to the A2A protocol"
        )
        assert "STATUS | CONTENT | ACTION" in md, (
            f"{path.name} must state the A2A reply shape [TAG] STATUS | CONTENT | ACTION"
        )


def test_agents_carry_no_framework_assumptions(repo_root, agent_files):
    """No shipped agent must name a concrete framework or stack — all variance goes in code-of-conduct.md."""
    # Given
    violations = []

    # When
    for path in agent_files:
        md = path.read_text()
        for pattern in _STACK_LITERAL_PATTERNS:
            hit = pattern.search(md)
            if hit:
                violations.append(f"{path.name}: matched {hit.group()!r}")

    # Then
    assert not violations, (
        "Agents contain stack literals — move them to code-of-conduct.md:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_all_agents_stay_within_their_token_budget(repo_root, agent_files):
    """Each agent file must stay under {_AGENT_TOKEN_LIMIT} tokens (cl100k_base)."""
    # Given
    over_budget = []

    # When
    for path in agent_files:
        n = count_tokens(path.read_text())
        if n > _AGENT_TOKEN_LIMIT:
            over_budget.append(f"{path.name}: {n} tokens (limit {_AGENT_TOKEN_LIMIT})")

    # Then
    assert not over_budget, (
        "Agent files over token budget:\n" + "\n".join(f"  {v}" for v in over_budget)
    )


def test_senior_qa_engineer_documents_bdd_for_frontend_scope(repo_root):
    """senior-qa-engineer must mention BDD/Gherkin and e2e tooling for frontend features."""
    # Given
    md = (repo_root / "plugin" / "agents" / "senior-qa-engineer.md").read_text()

    # When / Then
    assert "BDD" in md or "Gherkin" in md, \
        "senior-qa-engineer must mention BDD or Gherkin for frontend scope"
    assert "Cypress" in md or "Playwright" in md, \
        "senior-qa-engineer must name an e2e test tool for frontend scenarios"
