"""Tests that verify the specialist agent list is complete and follows the plugin contract."""

import json
import re
from pathlib import Path

import pytest

# Module-level list so tests can parametrize over each agent file (one cell per file).
_AGENT_PATHS = sorted((Path(__file__).resolve().parents[2] / "dist" / "claude-code" / "agents").glob("*.md"))


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
    """Every specialist advisor listed in the roster must ship as an actual agent file, and no
    stray, unlisted agent file may sneak in -- keeps the advertised set of advisors in sync with
    what actually gets installed."""
    # Given
    existing = {p.stem for p in (repo_root / "dist" / "claude-code" / "agents").glob("*.md")}

    # When
    missing = [n for n in _ADVISOR_AGENTS if n not in existing]
    extra = [n for n in existing if n not in _ADVISOR_AGENTS and n != _DEFAULT_AGENT]

    # Then
    assert not missing, f"Specialist advisors missing from agents/: {missing}"
    assert not extra, (
        f"agents/ has files that are neither a specialist advisor nor the default agent: {extra}"
    )
    assert (repo_root / "dist" / "claude-code" / "agents" / f"{_DEFAULT_AGENT}.md").is_file(), \
        "the default agent file must exist"


def test_all_agents_are_listed_in_the_project_documentation(repo_root):
    """Every specialist advisor's name must appear in the project's documentation, so someone
    reading the docs sees the exact same set of advisors that ships with the plugin -- prevents
    the documentation from silently going stale as advisors are added or removed."""
    # Given
    doc = (repo_root / "dist" / "claude-code" / "CLAUDE.md").read_text()

    # When
    missing = [name for name in _ADVISOR_AGENTS if name not in doc]

    # Then
    assert not missing, f"Advisors not documented in CLAUDE.md: {missing}"


@pytest.mark.parametrize("path", _AGENT_PATHS, ids=lambda p: p.stem)
def test_every_agent_file_declares_its_identity_and_how_it_replies(path):
    """Every shipped agent file must declare its name, a description, and which model it runs on,
    must tell the agent to read the project's code-of-conduct file, and must document a
    consistent reply format (status, content, next action). Skipping any of these would leave an
    agent without a clear identity or a predictable way to report back, breaking how the
    orchestrator and other agents interpret its results."""
    md = path.read_text()
    name = path.stem
    assert md.startswith("---"), f"{path.name} must open with YAML frontmatter"
    m = _AGENT_NAME_RE.search(md)
    assert m is not None, f"{path.name} frontmatter missing `name:`"
    assert m.group(1) == name, f"{path.name} frontmatter name={m.group(1)!r} must match filename {name!r}"
    assert "description:" in md, f"{path.name} frontmatter missing 'description:'"
    assert "model:" in md, f"{path.name} frontmatter missing 'model:'"
    assert "code-of-conduct" in md.lower(), \
        f"{path.name} must instruct the agent to read the project's code-of-conduct file (any capitalization)"
    assert "a2a-communication-protocol.md" in md, f"{path.name} must point to the A2A protocol"
    assert "STATUS | CONTENT | ACTION" in md, \
        f"{path.name} must state the A2A reply shape [TAG] STATUS | CONTENT | ACTION"


def test_agents_carry_no_framework_assumptions(repo_root, agent_files):
    """No shipped agent may name a specific framework, library, or stack (React, Django, Spring,
    and the like) -- any such assumption belongs in the project's own code-of-conduct file
    instead, so the same agent works unchanged across projects built on different stacks."""
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
def test_specialist_agents_stay_usable_outside_hercules_internals(path):
    """A reusable specialist advisor must never hardcode Hercules' own internal command names or
    state-tracking field names -- that information is handed to it fresh each time it's called.
    Only the orchestrator persona itself is allowed to know about those internals; if a
    specialist baked them in, it would silently break the moment it's reused in a different
    context."""
    if path.stem in _HERCULES_LITERAL_EXEMPT:
        pytest.skip("the orchestrator persona is not a reusable delegate")
    md = path.read_text()
    hits = [m.group() for pat in _HERCULES_INTERNAL_PATTERNS if (m := pat.search(md))]
    assert not hits, \
        f"{path.name} carries Hercules-internal literals {hits} — move them to the delegating command prompt"


def test_qa_never_writes_test_code(repo_root):
    """The QA advisor proposes test scenarios but must never carry the ability to write or edit
    code, and its own description must say so plainly. This guards against QA quietly turning
    into the thing writing (and thus grading) its own tests."""
    qa = (repo_root / "dist" / "claude-code" / "agents" / "senior-qa-engineer.md").read_text()
    tools_line = next(ln for ln in qa.splitlines() if ln.startswith("tools:"))
    assert "Edit" not in tools_line and "Write" not in tools_line, \
        f"senior-qa-engineer must not carry Edit/Write — it proposes scenarios (tools line: {tools_line!r})"
    assert "Never writes test code" in qa, \
        "senior-qa-engineer description must state QA never writes test code"


def test_cynical_reviewer_reports_missing_specs_back_to_whoever_called_it(read_file):
    """When cynical-reviewer finds no editable, up-to-date requirements to check work against, it
    must report that fact back to whichever process invoked it, rather than assuming one
    particular caller's own storage. This keeps the reviewer reusable by any caller instead of
    silently coupling it to a single workflow."""
    md = read_file("dist/claude-code/agents/cynical-reviewer.md")
    lower = md.lower()
    assert "spec-sync (mandatory last step)" in lower, \
        "cynical-reviewer must keep the mandatory spec-sync step"
    assert "report the disposition back to the caller" in lower, \
        "spec-sync must report the disposition back to the caller when no editable spec exists"


def test_hercules_agent_has_first_run_detection(read_file):
    """The first time Hercules is used in a project, it must recognize this from the user's saved
    configuration and walk them through onboarding, including generating a code-of-conduct file
    -- so a brand-new user is guided through setup instead of dropped straight into a blank
    workflow."""
    content = read_file("dist/claude-code/agents/hercules.md")
    assert "first-run" in content.lower() or "first run" in content.lower(), \
        "hercules.md must have first-run detection"
    assert "code-of-conduct-generator" in content, \
        "first-run onboarding must mention code-of-conduct-generator"
    assert "config.json" in content, \
        "first-run detection must reference the registry ~/.hercules/config.json"


def test_persona_version_read_is_not_hardcoded(read_file):
    """Hercules must report its version by reading it live from the plugin's own metadata file,
    never from a number typed directly into the agent file. A typed-in number would drift out of
    sync with the real release version the moment the plugin is updated; this test starts
    passing with no such number present today and would catch the very first one introduced."""
    persona = read_file("dist/claude-code/agents/hercules.md")
    assert not re.search(r"\d+\.\d+\.\d+", persona), \
        "hercules.md carries a hardcoded version literal — read plugin.json live instead"


def test_persona_reads_plugin_json_live(read_file):
    """When asked its version, Hercules must read it from the plugin's own metadata file at a
    fixed, predictable location rather than from a copy or a guess -- so the version it reports
    always matches whatever the actual installed release carries, on any branch."""
    persona = read_file("dist/claude-code/agents/hercules.md")
    assert ".claude-plugin/" in persona and "plugin.json" in persona, \
        "hercules.md must instruct reading plugin.json from the .claude-plugin/ folder"
    assert "version" in persona, "hercules.md must report the plugin.json version field"


def test_persona_describes_its_capabilities(read_file):
    """When asked what it can do, Hercules must name all four workflow phases (Discover, Design,
    Build, Ship) and the commands that start them, so a user can discover the full workflow just
    by asking the assistant rather than needing to go read external documentation."""
    persona = read_file("dist/claude-code/agents/hercules.md")
    for phase in ("Discover", "Design", "Build", "Ship"):
        assert phase in persona, f"hercules.md must name the {phase} phase as a capability"
    assert "/hercules:workflow" in persona, "hercules.md must name the guided workflow command"
    assert "/hercules:discover" in persona, "hercules.md must name the phase commands"


def test_plugin_declares_default_agent_with_persona(repo_root):
    """The plugin's settings must name a default agent, and that agent's file must actually carry
    the Hercules persona -- since a plugin has no way to inject a root instructions file, the
    default agent is the only place the persona can live, and this catches it silently going
    missing."""
    settings = json.loads((repo_root / "dist" / "claude-code" / "settings.json").read_text())
    agent_name = settings.get("agent")
    assert agent_name, "dist/claude-code/settings.json must declare a default 'agent'"
    agent_file = repo_root / "dist" / "claude-code" / "agents" / f"{agent_name}.md"
    assert agent_file.is_file(), f"default agent {agent_name!r} has no file at dist/claude-code/agents/{agent_name}.md"
    assert "You are **Hercules**" in agent_file.read_text(), \
        "the default agent must carry the Hercules persona marker"


def test_advisor_roster_matches_what_the_plugin_actually_ships(repo_root):
    """The internal list of specialist advisors and the advisor list declared in the plugin's own
    settings must always name the exact same set of agents. If they drifted apart, a user could
    be told about an advisor that isn't actually wired up, or use one that isn't tracked
    anywhere else."""
    settings = json.loads((repo_root / "dist" / "claude-code" / "settings.json").read_text())
    manifest = settings.get("advisors", [])
    assert sorted(manifest) == sorted(_ADVISOR_AGENTS), (
        "dist/claude-code/settings.json advisors[] and _ADVISOR_AGENTS are out of sync.\n"
        f"  In settings.json only: {sorted(set(manifest) - set(_ADVISOR_AGENTS))}\n"
        f"  In _ADVISOR_AGENTS only: {sorted(set(_ADVISOR_AGENTS) - set(manifest))}"
    )
