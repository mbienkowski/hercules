"""Delivery commands — shared contracts: naming/date/format, registry, CLAUDE.md and README pins."""

from __future__ import annotations

import re
import pytest
from tests.conftest import (
    ALL_COMMANDS as _ALL_COMMANDS,
    BUILD as _BUILD,
    DESIGN as _DESIGN,
    DISCOVER as _DISCOVER,
    SHIP as _SHIP,
    WORKFLOW as _WORKFLOW,
    section as _section,
)
from tests.commands.conftest import _BAD_DATE_RE, _ISO_DATE_RE, _LETTER_STEP_RE


def test_documentation_lists_exactly_the_commands_that_exist(repo_root, read_file):
    """CLAUDE.md must name every /hercules: command, and each named command must exist as a file."""
    # Given
    doc = read_file("dist/claude-code/CLAUDE.md")
    command_re = re.compile(r"/hercules:([a-z-]+)")
    doc_commands = {m.group(1) for m in command_re.finditer(doc)}

    # When / Then
    for name in doc_commands:
        cmd_file = repo_root / "dist" / "claude-code" / "commands" / f"{name}.md"
        assert cmd_file.exists(), (
            f"CLAUDE.md names /hercules:{name} but plugin/commands/{name}.md does not exist"
        )

    for step_file in [_DISCOVER, _DESIGN, _BUILD]:
        name = step_file.split("/")[-1].replace(".md", "")
        assert name in doc_commands, (
            f"dist/claude-code/commands/{name}.md exists in the workflow chain but is not documented in CLAUDE.md"
        )

def test_command_steps_use_integer_numbering(read_file):
    """Command step/section numbering must be integers only — no letter suffixes (4a, 1b)."""
    # Given / When / Then
    for rel in _ALL_COMMANDS:
        md = read_file(rel)
        hits = _LETTER_STEP_RE.findall(md)
        assert not hits, (
            f"{rel} uses letter-suffixed step numbering {hits} — use integers only (1, 2, 3, …)"
        )

def test_dates_in_commands_use_iso_hyphen_format(read_file):
    """Command files must use YYYY-MM-DD (ISO hyphen format), never the ambiguous YYYY-DD-MM."""
    # Given / When / Then — no command may use the ambiguous YYYY-DD-MM format.
    for rel in [_DISCOVER, _DESIGN, _BUILD]:
        md = read_file(rel)
        assert not _BAD_DATE_RE.search(md), (
            f"{rel} uses non-ISO date format YYYY-DD-MM — must be YYYY-MM-DD"
        )
    # Discover and Design write dated artifacts; Build ships code + tests (no dated file).
    for rel in [_DISCOVER, _DESIGN]:
        md = read_file(rel)
        assert _ISO_DATE_RE.search(md), (
            f"{rel} must use YYYY-MM-DD ISO format in artifact paths"
        )

def test_each_command_file_contains_its_own_trigger_phrase(read_file):
    """Each command file must contain its own /hercules:<name> trigger — a mutation that removes
    the trigger phrase from the file body would otherwise go undetected by the token budget gate."""
    # Given
    triggers = {
        _DISCOVER: "/hercules:discover",
        _DESIGN:   "/hercules:design",
        _BUILD:    "/hercules:build",
        _WORKFLOW: "/hercules:workflow",
        _SHIP:     "/hercules:ship",
    }

    # When / Then
    for file, trigger in triggers.items():
        md = read_file(file)
        assert trigger in md, (
            f"{file} must contain its own trigger phrase {trigger!r} "
            f"so users know which command to invoke"
        )

def test_session_artifact_paths_use_date_desc_naming_convention(read_file):
    """All command output paths must follow YYYY-MM-DD-desc-phase.md naming convention."""
    # Given / When / Then
    # Build no longer writes a file artifact — it ships code + tests, so it is not listed here.
    for rel, expected_suffix in [
        (_DISCOVER, "business-requirements.md"),
        (_DESIGN,   "-spec-"),
    ]:
        md = read_file(rel)
        assert expected_suffix in md, (
            f"{rel} output path must include {expected_suffix}"
        )
        assert "YYYY-MM-DD" in md, (
            f"{rel} must use YYYY-MM-DD ISO format in output path"
        )

def test_commands_maintain_session_index(read_file):
    """All main commands must reference INDEX.md to maintain cross-session continuity."""
    # Given / When / Then
    for rel in [_DISCOVER, _DESIGN, _BUILD]:
        md = read_file(rel)
        assert "INDEX.md" in md, (
            f"{rel} must reference INDEX.md to maintain session continuity"
        )

def test_no_session_md_lightweight_path(repo_root, read_file):
    """Regression guard: the workflow is one dynamic flow (the diagram is the source of truth).
    There is no separate `*-session.md` 'lightweight path' / 'lightweight shortcut' / 'fast pass'
    for trivial/low — every tier runs the same four phases and produces the same artifacts."""
    targets = [*_ALL_COMMANDS, "dist/claude-code/CLAUDE.md", "dist/claude-code/skills/session-summary/SKILL.md", "README.md"]
    for path in targets:
        text = read_file(path)
        lower = text.lower()
        assert "session.md" not in text, f"{path} must not reference the removed *-session.md artifact"
        assert "lightweight" not in lower, f"{path} must not describe a separate 'lightweight' path"
        assert "fast pass" not in lower, f"{path} must not describe a 'fast pass' shortcut"

def test_only_trivial_skips_advisors(read_file):
    """Discover's advisor recommendation scales with the tier and is NOT gated at medium+: only
    `trivial` skips advisors; `low` and up run a (scaled) advisor round."""
    md = read_file(_DISCOVER)
    lower = md.lower()
    assert "advisor recommendation (medium+)" not in lower, \
        "discover must not gate the advisor recommendation at medium+ (low gets a scaled round)"
    assert "trivial" in lower and "runs none" in lower, \
        "discover must say trivial runs no advisors"
    assert "reduced set" in lower, \
        "discover must give `low` a reduced advisor set (not zero, not the full set)"

def test_advisor_debate_step_is_operational(read_file):
    """Discover and Design must title the step 'Advisor debate' and invoke the debate protocol
    (not merely 'recommend' advisors)."""
    for rel in [_DISCOVER, _DESIGN]:
        md = read_file(rel)
        assert "Advisor debate" in md, f"{rel} must title the advisor step 'Advisor debate'"
        assert "debate-consensus-protocol.md" in md, \
            f"{rel} must invoke the debate per debate-consensus-protocol.md"

def test_spec_deletion_wording_consistent(repo_root, read_file):
    """Specs are deleted when delivered in code (during Build), not on merge to main. No shipped
    doc may describe spec deletion as happening on 'merge to main'."""
    targets = ["README.md", *(str(p.relative_to(repo_root)) for p in (repo_root / "dist" / "claude-code").rglob("*.md"))]
    for path in targets:
        lower = read_file(path).lower()
        assert "merge to main" not in lower, f"{path} must not say specs are deleted on 'merge to main'"
        assert "merged to main" not in lower, f"{path} must not say specs are deleted on 'merged to main'"

def test_readme_quality_thresholds_deferred_to_coc(read_file):
    """README must present coverage/mutation thresholds as the project code-of-conduct.md default
    (the plugin carries no numbers of its own), not as a hardcoded universal gate."""
    content = read_file("README.md")
    assert "Build gates on **≥90% branch coverage**" not in content, \
        "README must not hardcode ≥90% as an absolute gate — thresholds come from the CoC"
    assert "code-of-conduct.md` sets" in content, \
        "README must tie quality thresholds to the project's code-of-conduct.md"
    assert "suggests **≥90%**" in content, \
        "README must frame ≥90% as the suggested CoC default"
    assert "mandatory steps, not best-practices you skip" not in content.lower(), \
        "README must not call the (CoC-conditional) mutation gate unconditionally mandatory"
    assert "when the coc" in content.lower() or "when the code-of-conduct.md" in content.lower(), \
        "README must condition the mutation gate on the CoC defining a threshold"

def test_readme_no_auto_escalation_claim(read_file):
    """README must not claim a single dissent automatically escalates the tier — CLAUDE.md is
    explicit that Hercules never re-scores; dissent only surfaces as input to the user."""
    readme = read_file("README.md").lower()
    assert "escalates the tier" not in readme, \
        "README must not claim dissent auto-escalates the tier (contradicts CLAUDE.md's never-re-scores rule)"
    assert "never re-scores" in read_file("dist/claude-code/CLAUDE.md").lower(), \
        "sanity: CLAUDE.md must still state the never-re-scores rule this test pins README against"

def test_high_risk_floor_list_consistent(read_file):
    """The high-risk surfaces that floor a feature at `high` must be stated identically in the
    README and plugin/CLAUDE.md (token-based, so minor wording differences elsewhere are fine)."""
    readme = read_file("README.md").lower()
    claude = read_file("dist/claude-code/CLAUDE.md").lower()
    canonical = ["auth", "secrets", "money", "migration", "deletion", "production config", "concurrency"]
    for token in canonical:
        assert token in claude, f"dist/claude-code/CLAUDE.md floor list must name '{token}'"
        assert token in readme, f"README high-risk floor rule must name '{token}'"

def test_index_md_schema_is_defined_in_claude_md(read_file):
    """CLAUDE.md must define the INDEX.md column schema so all commands write consistent rows."""
    md = read_file("dist/claude-code/CLAUDE.md")
    assert "Status" in md and "Tier" in md, "CLAUDE.md must define Status and Tier columns"
    # Pin the declared Status set on its actual declaration line so a command can't write a
    # status (discover/design) that CLAUDE.md later drops without failing here.
    status_line = next((ln for ln in md.splitlines() if "Status values" in ln), "")
    assert status_line, "CLAUDE.md must declare the INDEX 'Status values' set"
    for status in ("discover", "design", "build", "delivered", "abandoned"):
        assert status in status_line, f"CLAUDE.md 'Status values' must include '{status}'"

def test_commands_reference_artifact_root_resolution_rule(read_file):
    """The artifact-root resolution rule must be defined once in CLAUDE.md and used by commands."""
    claude_md = read_file("dist/claude-code/CLAUDE.md").lower()
    assert "artifact root resolution" in claude_md, \
        "CLAUDE.md must define the Artifact root resolution rule"
    assert "default to" in claude_md and "docs/" in claude_md, \
        "CLAUDE.md must state docs/ as the default artifact root"

def test_no_command_or_readme_references_removed_context_file(read_file):
    """Regression guard: docs/.context was removed. No command, the plugin CLAUDE.md, or the README
    may reference it or promise a 'gitignored, never committed' machine-local file — that claim was
    never enforced and risked leaking a local file into the user's repo."""
    targets = [*_ALL_COMMANDS, "dist/claude-code/CLAUDE.md", "dist/claude-code/skills/session-summary/SKILL.md", "README.md"]
    for path in targets:
        text = read_file(path)
        assert "docs/.context" not in text, f"{path} must not reference the removed docs/.context file"
        assert "gitignored, never committed" not in text.lower(), \
            f"{path} must not promise an untested 'gitignored, never committed' machine-local file"

def test_claude_md_documents_home_config_state_contract(read_file):
    """dist/claude-code/CLAUDE.md must document the split machine-local state: a registry config.json with a
    `projects` map (directory, state_file, repositories) plus per-project state/{slug}.json files."""
    md = read_file("dist/claude-code/CLAUDE.md")
    assert "config.json" in md, "CLAUDE.md must name the registry ~/.hercules/config.json"
    assert "state/" in md or "state_file" in md, \
        "CLAUDE.md must document the per-project state file (~/.hercules/state/{slug}.json)"
    assert "projects" in md, "CLAUDE.md must document the projects map"
    assert "directory" in md, "each project entry must carry a directory field"
    assert "repositories" in md, "CLAUDE.md must document the repositories (repo list) map"
    assert "frozen_override" in md, \
        "CLAUDE.md must document the user-granted frozen_override session field"
    assert "frozen_hook" in md, \
        "CLAUDE.md must document the per-project frozen_hook opt-out"
    # The JSON fragments show every field at once — an impossible combination in real state.
    # Both fences must say so, or an agent may treat the sample as a template to reproduce.
    assert md.count("// Example — illustrative values") >= 2, \
        "every CLAUDE.md JSON fragment must be annotated as an illustrative example"
    assert "real state omits fields that" in md, \
        "the state example must say real state omits fields that don't apply"

def test_claude_md_defines_development_principles(read_file):
    """CLAUDE.md must contain a Development principles section with the fixed project rules."""
    md = read_file("dist/claude-code/CLAUDE.md")
    assert "Development principles" in md, \
        "CLAUDE.md must define a '## Development principles' section"
    assert "hercules" in md.lower(), \
        "Development principles must state the canonical app name 'hercules'"
    assert "business-requirements" in md, \
        "Development principles must reference permanent business-requirements files"
    assert "temporary" in md.lower() or "deleted" in md.lower(), \
        "Development principles must state that spec files are temporary"

def test_claude_md_documents_current_phase_semantics(read_file):
    """Both hooks arm/disarm on current_phase — the session-field prose must document it and
    its full value set like every other field."""
    md = read_file("dist/claude-code/CLAUDE.md")
    prose = md[md.index("Session object (in the state file):"):]
    assert "`current_phase`" in prose, "session prose must document current_phase"
    for v in ('"discover"', '"design"', '"build"', '"shipped"'):
        assert v in prose, f"current_phase value set must enumerate {v}"

def test_claude_md_documents_keep_specs(read_file):
    """The registry prose must document keep_specs, and principle 3 must carry the carve-out."""
    md = read_file("dist/claude-code/CLAUDE.md")
    assert "keep_specs" in md, "CLAUDE.md must document the keep_specs registry field"
    principles = md[md.index("## Development principles"):md.index("## Persona")]
    assert "keep" in principles.lower() and "code-of-conduct" in principles.lower(), \
        "principle 3 must state the CoC can keep specs (refreshed at delivery)"

def test_spec_template_deletion_note_acknowledges_keep_override(read_file):
    """The template's Deletion note is embedded in every generated spec — a kept spec carrying
    an unconditional 'Delete this file' instruction contradicts the keep_specs lifecycle for
    its whole life. The note must acknowledge the code-of-conduct keep override."""
    md = read_file(_DESIGN)
    note = md[md.index("## Deletion note"):]
    note = note[:note.index("```")]
    assert "git rm" in note, "deletion must remain the template's stated default"
    assert "code-of-conduct" in note, \
        "the note must say a code-of-conduct keep directive overrides the delete"

def test_claude_md_principle_8_survives_keep_specs(read_file):
    """Principle 8's close-out gate must be phrased for both retire modes: 'deleted only after
    delivery is proven' is false under keep_specs, where a proven spec is refreshed, not deleted."""
    md = read_file("dist/claude-code/CLAUDE.md")
    principles = md[md.index("## Development principles"):md.index("## Persona")]
    p8 = next(line for line in principles.splitlines() if line.startswith("8."))
    assert "retired" in p8, \
        "principle 8 must gate on retire (covers delete and keep-refresh), not delete alone"

def test_commands_declare_frontmatter(read_file):
    """Commands without frontmatter fall back to first-paragraph descriptions and are
    auto-invocable by the model mid-task — a four-phase wizard (or a commit wizard)
    must only ever start on an explicit /hercules:* invocation."""
    for rel in (_DISCOVER, _DESIGN, _BUILD, _SHIP, _WORKFLOW):
        md = read_file(rel)
        assert md.startswith("---\n"), f"{rel} must open with YAML frontmatter"
        head = md[:md.index("\n---", 3)]
        assert "description:" in head, f"{rel} frontmatter must carry a description"
        assert "disable-model-invocation: true" in head, \
            f"{rel} must not be auto-invocable mid-task"

def test_no_command_carries_the_fake_skill_dir_variable(read_file):
    """${CLAUDE_SKILL_DIR} is not a documented Claude Code variable — it never substitutes,
    so a command body citing it ships a literal the agent cannot resolve. The real install-root
    variable is ${CLAUDE_PLUGIN_ROOT}. Unconditional guard: fails the instant the dead variable
    returns to any command."""
    for rel in _ALL_COMMANDS:
        assert "${CLAUDE_SKILL_DIR}" not in read_file(rel), \
            f"{rel} cites the fake ${{CLAUDE_SKILL_DIR}} variable — use ${{CLAUDE_PLUGIN_ROOT}}"


def test_commands_cite_bundled_plugin_files_generically(read_file):
    """Plugin CLAUDE.md and protocols/ are NOT loaded into consumer sessions (per the plugins
    reference: 'A CLAUDE.md file at the plugin root is not loaded as project context') and
    relative paths resolve against the consumer's repo. Every command locates them GENERICALLY —
    in this plugin's own directory (the parent of the folder holding the command file) — without
    depending on a path variable substituting, so it works whether or not any variable expands."""
    for rel in _ALL_COMMANDS:
        md = read_file(rel)
        assert "this plugin's directory" in md, \
            f"{rel} must locate plugin files in this plugin's directory (generic, no variable)"


def test_agent_facing_prose_uses_no_path_variable(repo_root):
    """Agent-facing instructions (commands, agents, skills) locate plugin files by a generic
    plain-language approach, never by depending on a ${CLAUDE_PLUGIN_ROOT}/${CLAUDE_SKILL_DIR}
    substitution — a variable that may not expand in this context. Path variables are only for
    runtime hook configs (hooks.json / hook code), which this guard deliberately excludes."""
    md_files = [
        *(repo_root / "dist" / "claude-code" / "commands").glob("*.md"),
        *(repo_root / "dist" / "claude-code" / "agents").glob("*.md"),
        *(repo_root / "dist" / "claude-code" / "skills").glob("*/SKILL.md"),
    ]
    for path in md_files:
        text = path.read_text()
        for var in ("${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_SKILL_DIR}"):
            assert var not in text, \
                f"{path.name} depends on {var} substituting — use the generic locate instead"


def test_cited_plugin_paths_resolve_under_plugin(repo_root):
    """The plugin files that commands and the persona tell the agent to read must exist under
    plugin/ — a relayout that moved or renamed one would silently break resolution. This is the
    static half; the agent locates them generically (by directory + search) at runtime."""
    plugin = repo_root / "dist" / "claude-code"
    must_exist = [
        "CLAUDE.md",
        ".claude-plugin/plugin.json",
        "protocols/a2a-communication-protocol.md",
        "protocols/workflow-protocol.md",
        "commands/discover.md", "commands/design.md",
        "commands/build.md", "commands/ship.md", "commands/workflow.md",
    ]
    for rel in must_exist:
        assert (plugin / rel).exists(), f"cited plugin path missing: plugin/{rel}"

def _documented_and_referenced_state_fields(read_file):
    """(documented set, referenced set, commands text) for the CLAUDE.md↔commands schema guard.
    snake_case only — a loose pattern drags in backticked value literals (`false`); the two
    single-word fields (tier, cadence) are named explicitly so they stay guarded."""
    md = read_file("dist/claude-code/CLAUDE.md")
    prose = (_section(md, "Session object (in the state file):", "\n\n")
             + _section(md, "Registry entry:", "\n\n"))
    documented = set(re.findall(r"`([a-z]+(?:_[a-z]+)+)`", prose))
    documented |= {f for f in ("tier", "cadence") if f"`{f}`" in prose}
    commands = "".join(read_file(f) for f in _ALL_COMMANDS)
    referenced = set(re.findall(r"`([a-z]+(?:_[a-z]+)+)`", commands))
    return documented, referenced, commands


def test_every_documented_state_field_is_referenced_by_a_command(read_file):
    """Schema guard, doc→command direction: a field CLAUDE.md documents but no command references
    is drift — the dropped field fails here instead of rotting."""
    documented, _referenced, commands = _documented_and_referenced_state_fields(read_file)
    orphan_docs = {f for f in documented if f"`{f}`" not in commands}
    assert not orphan_docs, f"documented in CLAUDE.md but referenced by no command: {sorted(orphan_docs)}"


def test_every_command_referenced_state_field_is_documented(read_file):
    """Schema guard, command→doc direction: a snake_case field a command references but CLAUDE.md
    never documents is the next invented field drifting. File-level JSON keys are exempt."""
    documented, referenced, _commands = _documented_and_referenced_state_fields(read_file)
    allowed_file_level = {"active_session", "schema_version"}
    undocumented = referenced - documented - allowed_file_level
    assert not undocumented, f"state-shaped fields referenced by commands but undocumented: {sorted(undocumented)}"
