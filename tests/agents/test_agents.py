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

# Hercules-internal literals a reusable specialist agent must never hardcode — that knowledge belongs
# in the orchestrating command file, injected via the delegation prompt at call time.
_HERCULES_INTERNAL_PATTERNS = [
    re.compile(r"/hercules:"),                       # command references
    re.compile(r"\bbuild_progress\b"),
    re.compile(r"\bcurrent_spec(?:_round)?\b"),
    re.compile(r"\bpending_specs\b"),
    re.compile(r"\bdelivered_specs\b"),
    re.compile(r"\bcross_check_dispositions\b"),
    re.compile(r"\bfrozen_test_files\b"),
    re.compile(r"\bfrozen_override\b"),
    re.compile(r"\bfrozen_hook\b"),
    re.compile(r"\bconstraints_for_later_specs\b"),
    re.compile(r"\bhand(?:off_note|ed_off_by)\b"),
    re.compile(r"\bbuild_complete\b"),
    re.compile(r"-spec-\d"),                          # *-spec-NN-* artifact filename pattern
    re.compile(r"workflow-protocol"),                 # the protocol reaches agents only via the
                                                      # orchestrator-injected delegation packet
]

# The only agent allowed to reference Hercules internals: the orchestrator persona, not a delegate.
# Pinned explicitly (not implicit) so the exemption list can't rot silently as fields are added.
_HERCULES_LITERAL_EXEMPT = {"hercules"}

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


def test_specialist_agents_carry_no_hercules_internal_literals(agent_files):
    """Reusable specialist agents must hardcode no Hercules-internal literals (`/hercules:` commands,
    state-schema field names, or `*-spec-NN-*` artifact patterns). That knowledge belongs in the
    orchestrating command file and is injected via the delegation prompt. Only `hercules.md` (the
    orchestrator persona, not a delegate) is exempt. Positive, forward-looking invariant: it catches
    any future agent that regresses this without needing a new fix-specific test."""
    # Given
    violations = []

    # When
    for path in agent_files:
        if path.stem in _HERCULES_LITERAL_EXEMPT:
            continue
        md = path.read_text()
        for pattern in _HERCULES_INTERNAL_PATTERNS:
            hit = pattern.search(md)
            if hit:
                violations.append(f"{path.name}: matched {hit.group()!r}")

    # Then
    assert not violations, (
        "Specialist agents carry Hercules-internal literals — move them to the delegating command's "
        "prompt:\n" + "\n".join(f"  {v}" for v in violations)
    )


def test_qa_owns_scenarios_and_engineers_write_the_tests(repo_root):
    """The QA/engineer split must be coherent: QA proposes scenarios and never writes code, so its
    tool list carries no Edit/Write; the engineers author the tests from QA's scenarios. Positive
    assertions of the role model (not a bare absence check) — QA's redesigned role depends on it never
    gaining write access, so the tool-list check names that specific, ongoing risk."""
    # Given
    agents = repo_root / "plugin" / "agents"
    qa = (agents / "senior-qa-engineer.md").read_text()
    backend = (agents / "backend-engineer.md").read_text()
    frontend = (agents / "frontend-engineer.md").read_text()

    # When
    tools_line = next(ln for ln in qa.splitlines() if ln.startswith("tools:"))

    # Then — QA never writes test code
    assert "Edit" not in tools_line and "Write" not in tools_line, (
        f"senior-qa-engineer must not carry Edit/Write — its role is to propose scenarios, not write "
        f"tests (tools line: {tools_line!r})"
    )
    assert "Never writes test code" in qa, \
        "senior-qa-engineer description must state QA never writes test code"
    # And the engineers author the tests from QA's scenarios (the positive companion)
    for name, body in (("backend-engineer", backend), ("frontend-engineer", frontend)):
        assert "Write them yourself" in body, \
            f"{name} must state the engineer authors the failing tests (following QA's scenarios)"


def test_senior_qa_engineer_documents_bdd_for_frontend_scope(repo_root):
    """senior-qa-engineer must mention BDD/Gherkin and e2e tooling for frontend features."""
    # Given
    md = (repo_root / "plugin" / "agents" / "senior-qa-engineer.md").read_text()

    # When / Then
    assert "BDD" in md or "Gherkin" in md, \
        "senior-qa-engineer must mention BDD or Gherkin for frontend scope"
    assert "Cypress" in md or "Playwright" in md, \
        "senior-qa-engineer must name an e2e test tool for frontend scenarios"


def test_cynical_reviewer_spec_sync_is_caller_agnostic(read_file):
    """cynical-reviewer's mandatory spec-sync must be a reusable, caller-agnostic clause: when no
    editable live spec exists it *reports the disposition back to the caller* rather than naming any
    one caller's internal store. This is a positive assertion of the generic behaviour; the systemic
    no-literals scan separately guarantees no Hercules-internal literal leaks back in."""
    md = read_file("plugin/agents/cynical-reviewer.md")
    lower = md.lower()
    assert "spec-sync (mandatory last step)" in lower, \
        "cynical-reviewer must keep the mandatory spec-sync step"
    assert "report the disposition back to the caller" in lower, \
        "spec-sync must report the disposition back to the caller when no editable spec exists"


def test_hercules_agent_has_first_run_detection(read_file):
    """Hercules must detect first-run sessions via the registry config.json and show onboarding."""
    content = read_file("plugin/agents/hercules.md")
    assert "first-run" in content.lower() or "first run" in content.lower(), \
        "hercules.md must have first-run detection"
    assert "code-of-conduct-generator" in content, \
        "first-run onboarding must mention code-of-conduct-generator"
    assert "config.json" in content, \
        "first-run detection must reference the registry ~/.hercules/config.json"


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


def test_advisor_list_matches_plugin_settings(repo_root):
    """_ADVISOR_AGENTS and plugin/settings.json advisors[] must stay in sync."""
    settings = json.loads((repo_root / "plugin" / "settings.json").read_text())
    manifest = settings.get("advisors", [])
    assert sorted(manifest) == sorted(_ADVISOR_AGENTS), (
        "plugin/settings.json advisors[] and _ADVISOR_AGENTS are out of sync.\n"
        f"  In settings.json only: {sorted(set(manifest) - set(_ADVISOR_AGENTS))}\n"
        f"  In _ADVISOR_AGENTS only: {sorted(set(_ADVISOR_AGENTS) - set(manifest))}"
    )
