"""Tests that verify the specialist agent list is complete and follows the plugin contract."""

import json
import re
from pathlib import Path

import pytest

# Module-level list so tests can parametrize over each agent file (one cell per file).
_AGENT_PATHS = sorted((Path(__file__).resolve().parents[2] / "plugin" / "agents").glob("*.md"))


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


@pytest.mark.parametrize("path", _AGENT_PATHS, ids=lambda p: p.stem)
def test_each_agent_file_has_the_required_structure_and_fields(path):
    """Every agent file declares frontmatter name/description/model and wires the A2A contract.
    (Delegates pin a model for cost control; `hercules` is exempt BY DESIGN — it runs every
    session and inherits the user's configured model. See README § Plugin permissions.)"""
    md = path.read_text()
    name = path.stem
    assert md.startswith("---"), f"{path.name} must open with YAML frontmatter"
    m = _AGENT_NAME_RE.search(md)
    assert m is not None, f"{path.name} frontmatter missing `name:`"
    assert m.group(1) == name, f"{path.name} frontmatter name={m.group(1)!r} must match filename {name!r}"
    assert "description:" in md, f"{path.name} frontmatter missing 'description:'"
    if name != "hercules":
        assert "model:" in md, f"{path.name} frontmatter missing 'model:'"
    assert "code-of-conduct" in md.lower(), \
        f"{path.name} must instruct the agent to read the project's code-of-conduct file (any capitalization)"
    assert "a2a-communication-protocol.md" in md, f"{path.name} must point to the A2A protocol"
    assert "STATUS | CONTENT | ACTION" in md, \
        f"{path.name} must state the A2A reply shape [TAG] STATUS | CONTENT | ACTION"


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


@pytest.mark.parametrize("path", _AGENT_PATHS, ids=lambda p: p.stem)
def test_specialist_agent_carries_no_hercules_internal_literals(path):
    """A reusable specialist agent must hardcode no Hercules-internal literals (`/hercules:` commands,
    state-schema field names, `*-spec-NN-*` patterns) — that knowledge is injected via the delegation
    prompt. Only `hercules.md` (the orchestrator persona) is exempt."""
    if path.stem in _HERCULES_LITERAL_EXEMPT:
        pytest.skip("the orchestrator persona is not a reusable delegate")
    md = path.read_text()
    hits = [m.group() for pat in _HERCULES_INTERNAL_PATTERNS if (m := pat.search(md))]
    assert not hits, \
        f"{path.name} carries Hercules-internal literals {hits} — move them to the delegating command prompt"


def test_qa_never_writes_test_code(repo_root):
    """QA proposes scenarios and never writes code — its tool list must carry no Edit/Write, and its
    description must say so (a specific, ongoing risk, not a bare absence check)."""
    qa = (repo_root / "plugin" / "agents" / "senior-qa-engineer.md").read_text()
    tools_line = next(ln for ln in qa.splitlines() if ln.startswith("tools:"))
    assert "Edit" not in tools_line and "Write" not in tools_line, \
        f"senior-qa-engineer must not carry Edit/Write — it proposes scenarios (tools line: {tools_line!r})"
    assert "Never writes test code" in qa, \
        "senior-qa-engineer description must state QA never writes test code"


@pytest.mark.parametrize("name", ["backend-engineer", "frontend-engineer"])
def test_engineer_authors_the_failing_tests(repo_root, name):
    """The engineers author the failing tests from QA's scenarios (positive companion to the QA rule)."""
    body = (repo_root / "plugin" / "agents" / f"{name}.md").read_text()
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


def test_persona_version_read_is_not_hardcoded(read_file):
    """The persona reports its version by reading plugin.json live, never from a baked-in
    literal — a hardcoded number would be a third source of truth and drift from
    pyproject.toml/plugin.json. Regression guard: born green (no literal today), fails the
    moment someone hardcodes one."""
    persona = read_file("plugin/agents/hercules.md")
    assert not re.search(r"\d+\.\d+\.\d+", persona), \
        "hercules.md carries a hardcoded version literal — read plugin.json live instead"


def test_persona_reads_plugin_json_live(read_file):
    """Asked its version, Hercules reads ${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json
    (the variable substitutes in agent content) and reports its version field — live and
    single-sourced, so a branch and a release show whatever plugin.json actually carries."""
    persona = read_file("plugin/agents/hercules.md")
    assert "${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json" in persona, \
        "hercules.md must point the version read at ${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json"
    assert "version" in persona, "hercules.md must report the plugin.json version field"


def test_persona_describes_its_capabilities(read_file):
    """Asked what it can do, Hercules names the four phases and the /hercules:* commands —
    a self-aware persona, not a black box."""
    persona = read_file("plugin/agents/hercules.md")
    for phase in ("Discover", "Design", "Build", "Ship"):
        assert phase in persona, f"hercules.md must name the {phase} phase as a capability"
    assert "/hercules:workflow" in persona, "hercules.md must name the guided workflow command"
    assert "/hercules:discover" in persona, "hercules.md must name the phase commands"


def test_plugin_declares_default_agent_with_persona(repo_root):
    """plugin/settings.json must declare a default agent whose file carries the Hercules persona —
    a plugin injects no root CLAUDE.md, so the persona rides on the default agent."""
    settings = json.loads((repo_root / "plugin" / "settings.json").read_text())
    agent_name = settings.get("agent")
    assert agent_name, "plugin/settings.json must declare a default 'agent'"
    agent_file = repo_root / "plugin" / "agents" / f"{agent_name}.md"
    assert agent_file.is_file(), f"default agent {agent_name!r} has no file at plugin/agents/{agent_name}.md"
    assert "You are **Hercules**" in agent_file.read_text(), \
        "the default agent must carry the Hercules persona marker"


def test_advisor_list_matches_plugin_settings(repo_root):
    """_ADVISOR_AGENTS and plugin/settings.json advisors[] must stay in sync."""
    settings = json.loads((repo_root / "plugin" / "settings.json").read_text())
    manifest = settings.get("advisors", [])
    assert sorted(manifest) == sorted(_ADVISOR_AGENTS), (
        "plugin/settings.json advisors[] and _ADVISOR_AGENTS are out of sync.\n"
        f"  In settings.json only: {sorted(set(manifest) - set(_ADVISOR_AGENTS))}\n"
        f"  In _ADVISOR_AGENTS only: {sorted(set(_ADVISOR_AGENTS) - set(manifest))}"
    )


def test_engineers_defer_unpassable_test_verdict_to_the_caller(repo_root):
    """G2 gives the user the decision (3 rounds, root-cause, menu); an engineer agent must
    report an unpassable test to its caller, never self-declare a spec gap and abort."""
    for name in ("backend-engineer", "frontend-engineer"):
        md = (repo_root / "plugin" / "agents" / f"{name}.md").read_text()
        assert "stop and re-enter" not in md, \
            f"{name} must not unilaterally exit the TDD loop — report the blocker to the caller"


def test_cynical_reviewer_spec_sync_is_report_only(read_file):
    """The role expectation is 'report dispositions to the caller'; an 'update the spec' branch
    can fire on a live spec during ship-each cross-checks, mutating a frozen artifact."""
    md = read_file("plugin/agents/cynical-reviewer.md")
    assert "update the spec" not in md.lower(), \
        "cynical-reviewer must report dispositions, never update a spec"


def test_first_run_gate_keys_on_something_the_recommended_setup_writes(read_file):
    """hercules.md gates onboarding on a registry entry, but its recommended setup step
    (code-of-conduct-generator) never writes one — the welcome block would re-trigger forever.
    The gate must also stand down when the CoC the setup DOES write is present."""
    persona = read_file("plugin/agents/hercules.md")
    generator = read_file("plugin/skills/code-of-conduct-generator/SKILL.md")
    if "config.json" in persona:
        assert "config.json" in generator or "setup already ran" in persona, \
            "the first-run gate re-triggers after setup — key it on the CoC file too"


def test_every_agent_reads_the_project_code_of_conduct(agent_files):
    """The project CoC is authoritative for stack, conventions, and the quality bar —
    every agent must carry the read-it-if-present contract, or a delegate silently
    ships defaults the project explicitly overrode."""
    for path in agent_files:
        assert "code-of-conduct" in path.read_text().lower(), \
            f"{path.name} never reads the project code-of-conduct.md"
