"""Tests that verify the specialist agent list is complete and follows the plugin contract."""

import json
import re

import pytest


_ADVISOR_AGENTS = [
    # code / process
    "challenger", "cynical-reviewer", "lead-architect", "security-expert",
    "senior-qa-engineer", "backend-engineer", "frontend-engineer", "devops-engineer",
    "ux-ui-designer", "source-checker", "maintainer",
    # non-code / universal
    "business-analyst", "copywriter", "document-specialist", "simplicity-advocate",
]
_DEFAULT_AGENT = "hercules"  # the plugin's default agent / orchestrator persona — NOT a specialist advisor

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

def test_all_specialist_agents_are_present(repo_root):
    """Every listed agent must have a corresponding file in agents/, and vice versa."""
    # Given
    existing = {p.stem for p in (repo_root / "plugin" / "agents").glob("*.md")}

    # When
    missing = [n for n in _ADVISOR_AGENTS if n not in existing]
    extra = [n for n in existing if n not in _ADVISOR_AGENTS and n != _DEFAULT_AGENT]

    # Then
    assert not missing, f"Specialist advisors missing from agents/: {missing}"
    assert not extra, (
        f"agents/ has files that are neither a specialist advisor nor the default agent: {extra}"
    )
    assert (repo_root / "plugin" / "agents" / f"{_DEFAULT_AGENT}.md").is_file(), \
        "the default agent file must exist"


def test_all_agents_are_listed_in_the_project_documentation(repo_root):
    """CLAUDE.md must mention every agent name so the docs don't drift from the shipped files."""
    # Given
    doc = (repo_root / "plugin" / "CLAUDE.md").read_text()

    # When
    missing = [name for name in _ADVISOR_AGENTS if name not in doc]

    # Then
    assert not missing, f"Advisors not documented in CLAUDE.md: {missing}"


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


def test_senior_qa_engineer_documents_bdd_for_frontend_scope(repo_root):
    """senior-qa-engineer must mention BDD/Gherkin and e2e tooling for frontend features."""
    # Given
    md = (repo_root / "plugin" / "agents" / "senior-qa-engineer.md").read_text()

    # When / Then
    assert "BDD" in md or "Gherkin" in md, \
        "senior-qa-engineer must mention BDD or Gherkin for frontend scope"
    assert "Cypress" in md or "Playwright" in md, \
        "senior-qa-engineer must name an e2e test tool for frontend scenarios"


def test_hercules_agent_has_first_run_detection(read_file):
    """Hercules must detect first-run sessions via hercules-config.json and show onboarding."""
    content = read_file("plugin/agents/hercules.md")
    assert "first-run" in content.lower() or "first run" in content.lower(), \
        "hercules.md must have first-run detection"
    assert "code-of-conduct-generator" in content, \
        "first-run onboarding must mention code-of-conduct-generator"
    assert "hercules-config.json" in content, \
        "first-run detection must reference hercules-config.json as the state file"


def test_hercules_agent_has_ambiguity_elimination(read_file):
    """Hercules must have explicit ambiguity-elimination behavior documented in its persona."""
    content = read_file("plugin/agents/hercules.md")
    assert "ambiguit" in content.lower(), \
        "hercules.md must address ambiguity elimination"
    assert "figure it out" in content.lower() or "tbd" in content.lower() or \
           "open question" in content.lower(), \
        "hercules.md must reject open questions / TBDs"


def test_plugin_declares_default_agent_with_persona(repo_root):
    """plugin/settings.json must declare a default agent whose file carries the Hercules persona.

    This is what keeps a marketplace-installed user in-character: a plugin does not auto-inject a
    root CLAUDE.md, so the persona must ride on the default agent.
    """
    # Given
    settings = json.loads((repo_root / "plugin" / "settings.json").read_text())

    # When
    agent_name = settings.get("agent")

    # Then
    assert agent_name, "plugin/settings.json must declare a default 'agent'"
    agent_file = repo_root / "plugin" / "agents" / f"{agent_name}.md"
    assert agent_file.is_file(), (
        f"default agent {agent_name!r} has no file at plugin/agents/{agent_name}.md"
    )
    assert "You are **Hercules**" in agent_file.read_text(), (
        "the default agent must carry the Hercules persona marker"
    )
