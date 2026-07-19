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
    """Every /hercules: command mentioned in the docs must actually exist as a command file, and
    every real command must be mentioned in the docs -- so a user following the documentation
    never hits a command that isn't there, and a shipped command is never left undocumented."""
    # Given
    doc = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md"))
    command_re = re.compile(r"/hercules:([a-z-]+)")
    doc_commands = {m.group(1) for m in command_re.finditer(doc)}

    # When / Then
    for name in doc_commands:
        cmd_file = repo_root / "dist" / "claude-code" / "commands" / f"{name}.md"
        assert cmd_file.exists(), (
            f"CLAUDE.md names /hercules:{name} but dist/claude-code/commands/{name}.md does not exist"
        )

    for step_file in [_DISCOVER, _DESIGN, _BUILD]:
        name = step_file.split("/")[-1].replace(".md", "")
        assert name in doc_commands, (
            f"dist/claude-code/commands/{name}.md exists in the workflow chain but is not documented in CLAUDE.md"
        )

def test_step_numbers_in_commands_are_never_letter_suffixed(read_file):
    """Step numbers inside command instructions must be plain integers (1, 2, 3), never
    letter-suffixed like 4a or 1b -- so the numbered steps stay unambiguous for whoever is
    following them."""
    # Given / When / Then
    for rel in _ALL_COMMANDS:
        md = read_file(rel)
        hits = _LETTER_STEP_RE.findall(md)
        assert not hits, (
            f"{rel} uses letter-suffixed step numbering {hits} — use integers only (1, 2, 3, …)"
        )

def test_dates_in_commands_are_never_ambiguous(read_file):
    """Every date written into a command file must be in YYYY-MM-DD order. The day-before-month
    order (YYYY-DD-MM) is banned because it silently reads as a different, wrong date depending
    on the reader's locale."""
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
    """Every command file must literally contain the phrase a user types to invoke it (like
    /hercules:discover). If that phrase were accidentally deleted from the file body, this is
    the only check that would catch it."""
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

def test_every_phase_command_points_at_the_canonical_plan_approval_words(read_file):
    """Every phase command (Discover, Design, Build, Ship) must point at the canonical set of
    Plan-approval trigger words defined centrally in persona.md. Without a canonical set, a
    model has to interpret loose phrases like 'agree' or 'all' as approval — a missed variation
    loops the gate silently. persona.md owns the list; each phase gate references it so a future
    edit can't quietly drop a word from one phase without it showing up there."""
    # Given
    phase_commands = [_DISCOVER, _DESIGN, _BUILD, _SHIP]
    persona = read_file("dist/claude-code/CLAUDE.md")  # persona.md renders into CLAUDE.md
    canonical = ["approved", "approve", "yes", "continue", "proceed", "go", "Accept"]

    # When / Then — persona carries the full list, each phase command references it.
    for word in canonical:
        assert word in persona, (
            f"persona.md must list the Plan-approval trigger word {word!r} — "
            f"every phase gate accepts this canonical set"
        )
    for rel in phase_commands:
        md = read_file(rel)
        assert "canonical Plan-approval trigger words" in md, (
            f"{rel} must reference the canonical Plan-approval trigger words from persona.md"
        )
        assert "persona.md § Delivery workflow" in md, (
            f"{rel} must point at persona.md § Delivery workflow for the trigger-word list"
        )

def test_output_file_paths_are_dated_and_descriptively_named(read_file):
    """Files that Discover and Design write out must be named with today's date and a short
    description of their content, so a user browsing their project folder can tell at a glance
    when and why each file was produced."""
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

def test_main_commands_keep_the_session_index_up_to_date(read_file):
    """Discover, Design, and Build must each reference the project's running session index, so
    work done in one phase remains discoverable and traceable across the phases that follow."""
    # Given / When / Then
    for rel in [_DISCOVER, _DESIGN, _BUILD]:
        md = read_file(rel)
        assert "INDEX.md" in md, (
            f"{rel} must reference INDEX.md to maintain session continuity"
        )

def test_no_shortcut_path_exists_for_trivial_or_low_tier_work(repo_root, read_file):
    """The workflow is a single flow with the same four phases for every tier of work -- there
    must be no separate abbreviated 'lightweight' or 'fast pass' route for small changes, and no
    leftover mention of a removed shortcut file. Regression guard: reintroducing such a shortcut
    would let low-effort work silently skip steps the process intends everyone to go through."""
    targets = [*_ALL_COMMANDS, "dist/claude-code/CLAUDE.md", "dist/claude-code/skills/write-test-scenarios/SKILL.md", "README.md"]
    for path in targets:
        text = read_file(path)
        lower = text.lower()
        assert "session.md" not in text, f"{path} must not reference the removed *-session.md artifact"
        assert "lightweight" not in lower, f"{path} must not describe a separate 'lightweight' path"
        assert "fast pass" not in lower, f"{path} must not describe a 'fast pass' shortcut"

def test_only_the_trivial_tier_skips_advisor_review(read_file):
    """Every tier of work gets some advisor input except 'trivial', which runs none; 'low' still
    gets a reduced (not empty) round. This guards against the advisor step silently being turned
    off for more than just the smallest, trivial changes."""
    md = read_file(_DISCOVER)
    lower = md.lower()
    assert "advisor recommendation (medium+)" not in lower, \
        "discover must not gate the advisor recommendation at medium+ (low gets a scaled round)"
    assert "trivial" in lower and "runs none" in lower, \
        "discover must say trivial runs no advisors"
    assert "reduced set" in lower, \
        "discover must give `low` a reduced advisor set (not zero, not the full set)"

def test_advisor_disagreements_are_resolved_through_a_real_debate(read_file):
    """Discover and Design must actually run the advisor debate procedure -- not just say
    advisors are 'recommended' -- so conflicting advisor opinions get resolved through the same
    protocol every time, rather than being silently accepted or ignored."""
    for rel in [_DISCOVER, _DESIGN]:
        md = read_file(rel)
        assert "Advisor debate" in md, f"{rel} must title the advisor step 'Advisor debate'"
        assert "debate-consensus-protocol.md" in md, \
            f"{rel} must invoke the debate per debate-consensus-protocol.md"

def test_docs_never_say_specs_are_deleted_on_merge_to_main(repo_root, read_file):
    """Spec files are actually deleted during Build, once the work is delivered in code -- not
    later when a branch merges to main. No shipped documentation may describe deletion as
    happening 'on merge to main', which would give a wrong mental model of when cleanup occurs."""
    targets = ["README.md", *(str(p.relative_to(repo_root)) for p in (repo_root / "dist" / "claude-code").rglob("*.md"))]
    for path in targets:
        lower = read_file(path).lower()
        assert "merge to main" not in lower, f"{path} must not say specs are deleted on 'merge to main'"
        assert "merged to main" not in lower, f"{path} must not say specs are deleted on 'merged to main'"

def test_readme_never_claims_a_single_dissent_auto_escalates_the_tier(read_file):
    """A single advisor's disagreement must never be described as automatically raising the risk
    tier of the work -- Hercules surfaces dissent to the user but never re-scores on its own. The
    README's wording is pinned against contradicting that rule as stated in CLAUDE.md."""
    readme = read_file("README.md").lower()
    assert "escalates the tier" not in readme, \
        "README must not claim dissent auto-escalates the tier (contradicts CLAUDE.md's never-re-scores rule)"
    assert "never re-scores" in (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md")).lower(), \
        "sanity: CLAUDE.md must still state the never-re-scores rule this test pins README against"

def test_high_risk_categories_are_named_the_same_way_everywhere(read_file):
    """The set of sensitive areas (auth, secrets, money, migrations, deletion, production config,
    concurrency) that force a feature to at least the 'high' risk tier must be listed identically
    in the README and in CLAUDE.md, so a user reading either document sees the same rule."""
    readme = read_file("README.md").lower()
    claude = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md")).lower()
    canonical = ["auth", "secrets", "money", "migration", "deletion", "production config", "concurrency"]
    for token in canonical:
        assert token in claude, f"dist/claude-code/CLAUDE.md floor list must name '{token}'"
        assert token in readme, f"README high-risk floor rule must name '{token}'"

def test_the_session_index_columns_are_documented_and_stay_in_sync(read_file):
    """CLAUDE.md must spell out the columns (including Status and Tier) that every command writes
    into the project's session index, and the full set of allowed Status values, so no command
    can silently start writing a status value that isn't documented."""
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md"))
    assert "Status" in md and "Tier" in md, "CLAUDE.md must define Status and Tier columns"
    # Pin the declared Status set on its actual declaration line so a command can't write a
    # status (discover/design) that CLAUDE.md later drops without failing here.
    status_line = next((ln for ln in md.splitlines() if "Status values" in ln), "")
    assert status_line, "CLAUDE.md must declare the INDEX 'Status values' set"
    for status in ("discover", "design", "build", "delivered", "abandoned"):
        assert status in status_line, f"CLAUDE.md 'Status values' must include '{status}'"

def test_where_output_files_get_written_is_defined_once_and_reused(read_file):
    """CLAUDE.md must define a single rule for deciding where generated files are written
    (defaulting to the docs/ folder), so individual commands don't each invent their own answer
    to 'where does this file go'."""
    claude_md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md")).lower()
    assert "artifact root resolution" in claude_md, \
        "CLAUDE.md must define the Artifact root resolution rule"
    assert "default to" in claude_md and "docs/" in claude_md, \
        "CLAUDE.md must state docs/ as the default artifact root"

def test_no_doc_mentions_the_removed_local_context_file(read_file):
    """The docs/.context file was removed from the product. No command, README, or CLAUDE.md may
    still reference it or promise an untested 'gitignored, never committed' local file -- that
    promise was never actually enforced and risked leaking a local file into a user's repository."""
    targets = [*_ALL_COMMANDS, "dist/claude-code/CLAUDE.md", "dist/claude-code/skills/write-test-scenarios/SKILL.md", "README.md"]
    for path in targets:
        text = read_file(path)
        assert "docs/.context" not in text, f"{path} must not reference the removed docs/.context file"
        assert "gitignored, never committed" not in text.lower(), \
            f"{path} must not promise an untested 'gitignored, never committed' machine-local file"

def test_the_machine_local_settings_layout_is_fully_documented(read_file):
    """CLAUDE.md must describe exactly how Hercules stores its machine-local settings: one
    registry file listing each project's directory, state file, and repositories, plus one state
    file per project. Every sample shown must be labeled illustrative, since no real project ever
    has every field populated at once -- otherwise an agent could copy the sample as if it were a
    real template to reproduce."""
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md"))
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

def test_the_fixed_project_rules_are_written_down_in_one_place(read_file):
    """CLAUDE.md must contain a 'Development principles' section naming the app as 'hercules',
    referencing the permanent business-requirements files, and stating that spec files are
    temporary -- so these fixed rules live in one documented place rather than being assumed."""
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md"))
    assert "Development principles" in md, \
        "CLAUDE.md must define a '## Development principles' section"
    assert "hercules" in md.lower(), \
        "Development principles must state the canonical app name 'hercules'"
    assert "business-requirements" in md, \
        "Development principles must reference permanent business-requirements files"
    assert "temporary" in md.lower() or "deleted" in md.lower(), \
        "Development principles must state that spec files are temporary"

def test_every_phase_value_that_can_arm_or_disarm_a_safety_hook_is_documented(read_file):
    """Two safety hooks turn on and off based on which phase a session is currently in, so
    CLAUDE.md must document the current_phase field and enumerate every value it can take
    (discover, design, build, shipped) -- an undocumented value would leave a hook's behavior
    unexplained."""
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md"))
    prose = md[md.index("Session object (in the state file):"):]
    assert "`current_phase`" in prose, "session prose must document current_phase"
    for v in ('"discover"', '"design"', '"build"', '"shipped"'):
        assert v in prose, f"current_phase value set must enumerate {v}"

def test_the_option_to_keep_specs_instead_of_deleting_them_is_documented(read_file):
    """CLAUDE.md must document the keep_specs setting, and the development principle about
    deleting spec files must explicitly carry the exception that a code-of-conduct can choose to
    keep and refresh them instead."""
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md"))
    assert "keep_specs" in md, "CLAUDE.md must document the keep_specs registry field"
    principles = md[md.index("## Development principles"):md.index("## Persona")]
    assert "keep" in principles.lower() and "code-of-conduct" in principles.lower(), \
        "principle 3 must state the CoC can keep specs (refreshed at delivery)"

def test_a_kept_spec_does_not_carry_a_contradictory_delete_instruction(read_file):
    """Every generated spec includes a 'Deletion note' telling the reader to delete the file once
    the work is done. Because a spec created under keep_specs is meant to be kept and refreshed
    instead, that note must acknowledge the code-of-conduct override -- otherwise a kept spec
    would carry a delete instruction that contradicts its own lifecycle for as long as it exists."""
    md = read_file(_DESIGN)
    note = md[md.index("## Deletion note"):]
    note = note[:note.index("```")]
    assert "git rm" in note, "deletion must remain the template's stated default"
    assert "code-of-conduct" in note, \
        "the note must say a code-of-conduct keep directive overrides the delete"

def test_the_spec_template_has_a_known_violations_section(read_file):
    """The spec template must include a '## Known violations' section where architecture/dependency
    rules that are expected to fail at scaffold time are listed, along with which spec resolves them.
    This makes the 'known violation → fix → green' pattern visible to the traceability reviewer and
    the cross-check, instead of leaving it as an implicit understanding between specs."""
    md = read_file(_DESIGN)
    template_start = md.index("## Acceptance criteria")
    template_end = md.index("```", template_start + len("## Acceptance criteria"))
    template = md[template_start:template_end]
    assert "## Known violations" in template, \
        "the spec template must include a '## Known violations' section after Acceptance criteria"
    assert "architecture" in template.lower() or "dependency" in template.lower(), \
        "the Known violations section must name architecture/dependency rules as its subject"

def test_the_close_out_rule_accounts_for_specs_that_are_kept_not_deleted(read_file):
    """The development principle that gates closing out a feature on the spec being cleaned up
    must say 'retired' rather than 'deleted' -- under keep_specs a proven spec is refreshed and
    kept, not deleted, so wording that only mentions deletion would be false for that path."""
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md"))
    principles = md[md.index("## Development principles"):md.index("## Persona")]
    p8 = next(line for line in principles.splitlines() if line.startswith("8."))
    assert "retired" in p8, \
        "principle 8 must gate on retire (covers delete and keep-refresh), not delete alone"

def test_wizard_commands_can_only_be_started_by_explicit_invocation(read_file):
    """Discover, Design, Build, Ship, and Workflow must each declare a description and mark
    themselves as not auto-invocable. Without that, the model could start one of these
    multi-step wizards on its own in the middle of an unrelated task, instead of only when a
    user explicitly types the /hercules:* command."""
    for rel in (_DISCOVER, _DESIGN, _BUILD, _SHIP, _WORKFLOW):
        md = read_file(rel)
        assert md.startswith("---\n"), f"{rel} must open with YAML frontmatter"
        head = md[:md.index("\n---", 3)]
        assert "description:" in head, f"{rel} frontmatter must carry a description"
        assert "disable-model-invocation: true" in head, \
            f"{rel} must not be auto-invocable mid-task"

def test_commands_find_bundled_reference_files_without_a_fragile_path(read_file):
    """CLAUDE.md and the protocol files bundled with the plugin are not automatically loaded into
    a user's session, and any relative path would resolve against the user's own project instead.
    Every command must locate them by a generic rule -- this plugin's own directory -- rather than
    depending on a path placeholder that might not expand, so file lookup keeps working either
    way."""
    for rel in _ALL_COMMANDS:
        md = read_file(rel)
        assert "this plugin's directory" in md, \
            f"{rel} must locate plugin files in this plugin's directory (generic, no variable)"


def test_bundled_files_are_referenced_with_the_documented_path_placeholder(repo_root):
    """Instructions written for the agent must point to bundled plugin files using the officially
    supported ${CLAUDE_PLUGIN_ROOT} placeholder, which Claude Code's own documentation confirms
    does expand inside skill and agent content, and must never use the made-up
    ${CLAUDE_SKILL_DIR}, which never actually expands and would leave a broken, unresolved path."""
    md_files = [
        *(repo_root / "dist" / "claude-code" / "commands").glob("*.md"),
        *(repo_root / "dist" / "claude-code" / "agents").glob("*.md"),
        *(repo_root / "dist" / "claude-code" / "skills").glob("*/SKILL.md"),
    ]
    saw_plugin_root = False
    for path in md_files:
        text = path.read_text()
        assert "${CLAUDE_SKILL_DIR}" not in text, \
            f"{path.name} cites the fake ${{CLAUDE_SKILL_DIR}} — use ${{CLAUDE_PLUGIN_ROOT}}"
        if "${CLAUDE_PLUGIN_ROOT}" in text:
            saw_plugin_root = True
    assert saw_plugin_root, \
        "protocol references should resolve via ${CLAUDE_PLUGIN_ROOT} (the doc-sanctioned placeholder)"


def test_every_file_path_a_command_tells_the_agent_to_read_actually_exists(repo_root):
    """Every plugin file that a command or the persona instructs the agent to read must really
    exist at the expected path -- so a future rename or reorganization of the plugin's files is
    caught immediately instead of silently breaking the instructions that reference them."""
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
    md = (read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md"))
    prose = (_section(md, "Session object (in the state file):", "\n\n")
             + _section(md, "Registry entry:", "\n\n"))
    documented = set(re.findall(r"`([a-z]+(?:_[a-z]+)+)`", prose))
    documented |= {f for f in ("tier", "cadence") if f"`{f}`" in prose}
    commands = "".join(read_file(f) for f in _ALL_COMMANDS)
    referenced = set(re.findall(r"`([a-z]+(?:_[a-z]+)+)`", commands))
    return documented, referenced, commands


def test_a_documented_state_field_that_no_command_ever_uses_is_flagged(read_file):
    """Every machine-local state field that CLAUDE.md documents must actually be used by at least
    one command. A field that stays documented after every command has stopped using it is stale
    documentation that misleads whoever reads it about what the software actually does."""
    documented, _referenced, commands = _documented_and_referenced_state_fields(read_file)
    orphan_docs = {f for f in documented if f"`{f}`" not in commands}
    assert not orphan_docs, f"documented in CLAUDE.md but referenced by no command: {sorted(orphan_docs)}"


def test_a_state_field_a_command_invents_without_documenting_it_is_flagged(read_file):
    """Every machine-local state field a command reads or writes must be documented in CLAUDE.md
    (aside from a couple of known file-level keys). A command that starts using a new field
    without CLAUDE.md ever describing it is exactly how undocumented, drifting behavior creeps
    into the project."""
    documented, referenced, _commands = _documented_and_referenced_state_fields(read_file)
    allowed_file_level = {"active_session", "schema_version"}
    undocumented = referenced - documented - allowed_file_level
    assert not undocumented, f"state-shaped fields referenced by commands but undocumented: {sorted(undocumented)}"
