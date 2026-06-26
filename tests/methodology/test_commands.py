"""Tests that verify the Hercules delivery command files follow the methodology contracts."""

import re

import pytest


_DISCOVER  = "plugin/commands/discover.md"
_DESIGN    = "plugin/commands/design.md"
_BUILD     = "plugin/commands/build.md"
_WORKFLOW  = "plugin/commands/workflow.md"
_ALL_COMMANDS = [_DISCOVER, _DESIGN, _BUILD, _WORKFLOW]

_BAD_DATE_RE = re.compile(r"YYYY-DD-MM")
_ISO_DATE_RE = re.compile(r"YYYY-MM-DD")
# Letter-suffixed step labels (Step 4a, ## 1b, **4a —). Single letter + boundary so prose
# like "3am" (two letters, no boundary) is never flagged.
_LETTER_STEP_RE = re.compile(r"\bStep \d+[a-z]\b|^#+\s*\d+[a-z]\b|^\s*\*\*\d+[a-z]\b", re.MULTILINE)


def test_each_delivery_step_points_forward_to_the_next(read_file):
    """Each command in the workflow chain must reference the next step so the user can follow the flow."""
    # Given
    chain = [
        (_DISCOVER, "/hercules:design"),
        (_DESIGN,   "/hercules:build"),
    ]

    # When / Then
    for file, next_step in chain:
        md = read_file(file)
        assert next_step in md, f"{file} must point forward to the next step {next_step!r}"


def test_documentation_lists_exactly_the_commands_that_exist(repo_root, read_file):
    """CLAUDE.md must name every /hercules: command, and each named command must exist as a file."""
    # Given
    doc = read_file("plugin/CLAUDE.md")
    command_re = re.compile(r"/hercules:([a-z-]+)")
    doc_commands = {m.group(1) for m in command_re.finditer(doc)}

    # When / Then
    for name in doc_commands:
        cmd_file = repo_root / "plugin" / "commands" / f"{name}.md"
        assert cmd_file.exists(), (
            f"CLAUDE.md names /hercules:{name} but plugin/commands/{name}.md does not exist"
        )

    for step_file in [_DISCOVER, _DESIGN, _BUILD]:
        name = step_file.split("/")[2].replace(".md", "")
        assert name in doc_commands, (
            f"plugin/commands/{name}.md exists in the workflow chain but is not documented in CLAUDE.md"
        )


def test_discover_step_guides_the_user_through_discovery(read_file):
    """The discover command must accept rich upfront context and guide through discovery groups."""
    # Given
    md = read_file(_DISCOVER)
    lower = md.lower()

    # When / Then
    assert "wait for" in lower, "discover command must instruct Claude to wait for user answers"
    assert "classif" in lower, "discover command must classify complexity"
    assert "confirm or override" in lower, "discover command must ask user to confirm the classification"
    assert "approved" in lower, "discover command must require 'approved' before writing"
    assert "do not create the file until" in lower, "discover command must gate file creation on approval"
    assert "docs/" in md, "discover command must use docs/ as the default artifact root"
    assert "business-requirements.md" in md, \
        "discover command must name the output file with -business-requirements.md suffix"
    for section in ["## Goal", "## Users", "## Scope", "## Constraints", "## Success criteria"]:
        assert section in md, f"discover output template must include section {section!r}"
    assert "stakeholders approved" in md, \
        "discover must include the 'stakeholders approved' trigger phrase"
    assert "skip stakeholder review" in lower, \
        "discover must offer the 'skip stakeholder review' escape phrase"
    assert "API contracts" in md, \
        "discover Group D must ask about existing API contracts and ADRs"
    assert "plan mode" in lower, \
        "discover must enforce plan mode at the top"
    assert ("PRD" in md or "ADR" in md), \
        "discover must explicitly accept rich upfront context (PRDs, ADRs)"
    assert "business language" in lower, \
        "discover must constrain business-requirements to business language (no code/classes)"


def test_design_step_produces_a_complete_technical_artifact(read_file):
    """The design command must perform evidence-based requirements coverage before writing."""
    # Given
    md = read_file(_DESIGN)
    lower = md.lower()

    # When / Then
    assert "business-requirements.md" in md, \
        "design command must read the *-business-requirements.md artifact"
    assert "docs/" in md, "design command must use docs/ as the default session root"
    assert "classif" in lower, "design command must classify complexity"
    assert "confirm or override" in lower
    assert "approved" in lower
    assert "do not" in lower, "design command must block writing until approval"
    assert ("quote" in lower or "cite" in lower), "design command must cite coverage evidence"
    assert "coverage" in lower, "design command must perform requirements coverage check"
    assert ("not covered" in lower or "uncovered" in lower), "design command must name uncovered items"
    assert "n-1" in lower, "design command must document the n-1 collapse"
    assert "-spec-" in md, "design command must emit numbered sub-spec files (no separate design.md)"
    assert "design.md" not in md, "design command must not produce a *-design.md artifact"
    assert "stakeholders approved" in md, \
        "design must include the 'stakeholders approved' trigger phrase"
    assert "skip stakeholder review" in lower, \
        "design must offer the 'skip stakeholder review' escape phrase"
    assert "API contracts" in md, \
        "design Group A must ask about existing API contracts before new architecture questions"
    assert "ADR" in md, \
        "design Group A must mention ADRs"
    assert "plan mode" in lower, \
        "design must enforce plan mode at the top"
    assert ("spec-" in lower or "spec-01" in lower or "delivery order" in lower), \
        "design must produce numbered sub-spec files with a delivery order section"
    assert "git rm" in md or "delete" in lower, \
        "design must instruct that spec files are deleted after delivery"
    assert "satisfies" in lower, \
        "design gate must tie every requirement to a sub-spec via its satisfies header"


def test_build_step_defines_its_execution_contract(read_file):
    """The build command must read design and spec artifacts and gate close-out on evidence."""
    # Given
    md = read_file(_BUILD)
    lower = md.lower()

    # When / Then
    assert "business-requirements.md" in md, "build command must read *-business-requirements.md"
    assert "design.md" not in md, "build command must not read a *-design.md artifact (it no longer exists)"
    assert "spec" in lower, "build command must read and iterate over spec files"
    assert "docs/" in md
    assert "classif" in lower
    assert "confirm or override" in lower
    assert "coverage" in lower
    assert "evidence" in lower, "build command must require evidence for delivered specs"
    assert "failing test" in lower, \
        "build command must enforce TDD (failing tests first)"
    assert ("frozen" in lower or "scope lock" in lower), \
        "build command must enforce scope lock after red tests"
    assert "write-test-scenarios" in md, \
        "build command must reference write-test-scenarios skill"
    assert "cynical-reviewer" in md, \
        "build command must invoke cynical-reviewer at medium+"
    assert "learnings" in md, \
        "build command must invoke learnings skill at high/critical"
    assert "branch" in lower, \
        "build verify step must require branch coverage"
    assert "90%" in md, \
        "build must state the branch coverage threshold (90%)"
    assert "mutation" in lower, \
        "build must require mutation testing"
    assert "kill rate" in lower, \
        "build must state the mutation kill rate requirement"
    assert ("frontend" in lower or "Gherkin" in md or "BDD" in md), \
        "build must suggest BDD/Gherkin e2e for frontend scope"
    assert "git rm" in md, \
        "build must delete each spec file after delivery via git rm"
    assert "traceab" in lower, \
        "build close-out must verify requirement→spec→code/test traceability"
    assert "drift" in lower, \
        "build close-out must check for reverse scope-drift"
    assert "build.md" not in lower, \
        "build must not produce a *-build.md artifact — code + tests + git history are the record"
    assert lower.rindex("git rm") > lower.index("traceab"), \
        "spec deletion (git rm) must come after the traceability check, not before it"


def test_command_steps_use_integer_numbering(read_file):
    """Command step/section numbering must be integers only — no letter suffixes (4a, 1b)."""
    # Given / When / Then
    for rel in _ALL_COMMANDS:
        md = read_file(rel)
        hits = _LETTER_STEP_RE.findall(md)
        assert not hits, (
            f"{rel} uses letter-suffixed step numbering {hits} — use integers only (1, 2, 3, …)"
        )


def test_workflow_command_runs_all_three_phases_in_sequence(read_file):
    """The workflow command must orchestrate all three phases with guided transitions."""
    # Given
    md = read_file(_WORKFLOW)
    lower = md.lower()

    # When / Then
    for phase in ["discover", "design", "build"]:
        assert phase in lower, f"workflow must reference the {phase} phase"
    assert "move to" in lower, "workflow must use 'move to [phase]' transition prompts"
    assert "plan mode" in lower, "workflow must enforce plan mode"
    assert "not yet" in lower, "workflow must offer 'not yet' to stay in the current phase"


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


def test_discover_implements_lightweight_path_for_trivial_low(read_file):
    """Discover must implement the trivial/low single-pass path producing a session file."""
    # Given
    md = read_file(_DISCOVER)
    lower = md.lower()

    # When / Then
    assert "session.md" in md, \
        "discover must produce a *-session.md for trivial/low"
    assert ("trivial" in lower or "lightweight" in lower), \
        "discover must name the lightweight path"
    assert "## Requirements" in md, \
        "session template must include ## Requirements section"


def test_build_discovers_both_session_formats(read_file):
    """Build must find trivial/low sessions (*-session.md) as well as medium+ spec-based sessions."""
    # Given
    md = read_file(_BUILD)

    # When / Then
    assert "session.md" in md, \
        "build must handle trivial/low sessions (*-session.md, not separate files)"


def test_discover_writes_no_machine_local_file_into_repo(read_file):
    """discover must NOT write machine-local state into the user's repo — no docs/.gitignore
    and no docs/.context. State lives only in the home config (hercules-config.json)."""
    md = read_file(_DISCOVER)
    assert ".gitignore" not in md, "discover must not create a docs/.gitignore for machine-local state"
    assert ".context" not in md, "discover must not write docs/.context into the repo"
    assert "hercules-config.json" in md, \
        "discover must record session state in ~/.hercules/hercules-config.json"


def test_build_offers_resume_from_home_config(read_file):
    """Build (not all commands) must read the home-config project state and offer to resume by spec."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "resume" in lower, "build must offer resume from the home-config project state"
    assert "hercules-config.json" in lower, \
        "build must reference ~/.hercules/hercules-config.json for resume"
    assert ".context" not in lower, "build must not reference the removed docs/.context file"


def test_build_prompts_for_service_paths_on_multi_service_design(read_file):
    """Build must ask for local paths when the design names multiple services."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "local path" in lower or "service path" in lower or "service-path" in lower, \
        "build must prompt for service local paths"


def test_index_md_schema_is_defined_in_claude_md(read_file):
    """CLAUDE.md must define the INDEX.md column schema so all commands write consistent rows."""
    md = read_file("plugin/CLAUDE.md")
    assert "Status" in md and "Tier" in md, "CLAUDE.md must define Status and Tier columns"
    assert "delivered" in md.lower(), "CLAUDE.md must list 'delivered' as a valid Status value"


def test_context_tracks_spec_progress(read_file):
    """Build must track spec delivery progress via current_spec and delivered_specs in the
    project's home-config entry."""
    md = read_file(_BUILD)
    assert "current_spec" in md, \
        "build must track the in-progress spec via current_spec in the home-config entry"
    assert "delivered_specs" in md, \
        "build must maintain delivered_specs array in the home-config entry"


def test_discover_resolves_artifact_root(read_file):
    """discover Step 0 must resolve the artifact root from code-of-conduct.md, defaulting to docs/."""
    md = read_file(_DISCOVER)
    lower = md.lower()
    assert "artifact root" in lower, "discover must resolve the artifact root in Step 0"
    assert "code-of-conduct.md" in lower, "discover must let code-of-conduct.md override the docs location"
    assert "docs_root" in md, "discover must record the resolved path as docs_root in the home-config entry"


def test_commands_reference_artifact_root_resolution_rule(read_file):
    """The artifact-root resolution rule must be defined once in CLAUDE.md and used by commands."""
    claude_md = read_file("plugin/CLAUDE.md").lower()
    assert "artifact root resolution" in claude_md, \
        "CLAUDE.md must define the Artifact root resolution rule"
    assert "default to" in claude_md and "docs/" in claude_md, \
        "CLAUDE.md must state docs/ as the default artifact root"


def test_build_offers_handoff_prompt(read_file):
    """Build Step 6 must offer to record a handoff note in the home-config entry."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "taking over" in lower or "handoff" in lower, \
        "build Step 6 must prompt for handoff recording before close-out"


def test_no_command_or_readme_references_removed_context_file(read_file):
    """Regression guard: docs/.context was removed. No command, the plugin CLAUDE.md, or the README
    may reference it or promise a 'gitignored, never committed' machine-local file — that claim was
    never enforced and risked leaking a local file into the user's repo."""
    targets = [*_ALL_COMMANDS, "plugin/CLAUDE.md", "plugin/skills/session-summary/SKILL.md", "README.md"]
    for path in targets:
        text = read_file(path)
        assert ".context" not in text, f"{path} must not reference the removed docs/.context file"
        assert "gitignored, never committed" not in text.lower(), \
            f"{path} must not promise an untested 'gitignored, never committed' machine-local file"


def test_claude_md_documents_home_config_state_contract(read_file):
    """plugin/CLAUDE.md must document the machine-local state shape: a `projects` map keyed by name,
    each with a `directory` and a `repositories` map, living in hercules-config.json."""
    md = read_file("plugin/CLAUDE.md")
    assert "hercules-config.json" in md, "CLAUDE.md must name the home config file"
    assert "projects" in md, "CLAUDE.md must document the projects map"
    assert "directory" in md, "each project entry must carry a directory field"
    assert "repositories" in md, "CLAUDE.md must document the repositories (repo list) map"


def test_claude_md_defines_development_principles(read_file):
    """CLAUDE.md must contain a Development principles section with the fixed project rules."""
    md = read_file("plugin/CLAUDE.md")
    assert "Development principles" in md, \
        "CLAUDE.md must define a '## Development principles' section"
    assert "hercules" in md.lower(), \
        "Development principles must state the canonical app name 'hercules'"
    assert "business-requirements" in md, \
        "Development principles must reference permanent business-requirements files"
    assert "temporary" in md.lower() or "deleted" in md.lower(), \
        "Development principles must state that spec files are temporary"


def test_design_produces_sub_specs_with_delivery_order(read_file):
    """Design command must produce numbered sub-spec files and a delivery order section."""
    md = read_file(_DESIGN)
    lower = md.lower()
    assert "delivery order" in lower, \
        "design must include a ## Delivery order section"
    assert "spec-01" in lower or "spec-nn" in lower or "spec-0" in lower, \
        "design must show numbered sub-spec naming (e.g. spec-01-{slug}.md)"
    assert "satisfies" in lower, \
        "each sub-spec must carry a 'satisfies:' header linking to business-requirements.md"


def test_discover_step0_nudges_code_of_conduct(read_file):
    """discover Step 0 must surface code-of-conduct as a quality lever and offer to generate it."""
    md = read_file("plugin/commands/discover.md").lower()
    assert "code-of-conduct" in md
    assert "generate" in md
    assert "quality" in md
