"""Tests that verify the Hercules delivery command files follow the methodology contracts."""

import re

import pytest


_DISCOVER  = "plugin/commands/discover.md"
_DESIGN    = "plugin/commands/design.md"
_BUILD     = "plugin/commands/build.md"
_WORKFLOW  = "plugin/commands/workflow.md"
_SHIP      = "plugin/commands/ship.md"
_ALL_COMMANDS = [_DISCOVER, _DESIGN, _BUILD, _WORKFLOW, _SHIP]

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
        (_BUILD,    "/hercules:ship"),
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
    assert "tier" in lower and "state" in lower, \
        "design must read the tier from state (complexity is scored once in Discover)"
    assert "re-score" in lower or "re-scor" in lower, \
        "design must state it does not re-score complexity"
    assert "approved" in lower
    assert "do not" in lower, "design command must block writing until approval"
    assert ("quote" in lower or "cite" in lower), "design command must cite coverage evidence"
    assert "coverage" in lower, "design command must perform requirements coverage check"
    assert ("not covered" in lower or "uncovered" in lower), "design command must name uncovered items"
    assert "n-1" in lower, "design command must document the n-1 collapse"
    assert "-spec-" in md, "design command must emit numbered sub-spec files (no separate design.md)"
    assert "design.md" not in md, "design command must not produce a *-design.md artifact"
    assert ("mocking:" in lower or "what must be mocked" in lower), \
        "design Test-suite template must carry the mocking guidance the engineers follow (QA owns the WHAT)"
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
    assert "tier" in lower and "state" in lower, \
        "build must read the tier from state (complexity is scored once in Discover)"
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
        "build command must invoke learnings skill at every tier"
    assert "branch" in lower, \
        "build must reference branch coverage as a gate"
    assert "code-of-conduct" in lower, \
        "build must defer quality-gate thresholds to the project's code-of-conduct.md (no hardcoded numbers)"
    assert "90%" not in md, \
        "build must not hardcode a coverage/mutation number — thresholds come from code-of-conduct.md"
    assert "mutation" in lower, \
        "build must require mutation testing"
    assert "kill rate" in lower or "kill-rate" in lower, \
        "build must reference the mutation kill rate"
    assert ("frontend" in lower or "Gherkin" in md or "BDD" in md), \
        "build must suggest BDD/Gherkin e2e for frontend scope"
    assert "git rm" in md, \
        "build must delete each spec file after delivery via git rm"
    assert "traceab" in lower, \
        "build close-out must verify requirement→spec→code/test traceability"
    assert "drift" in lower, \
        "build close-out must check for reverse scope-drift"
    assert "-build.md" not in lower, \
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


def test_workflow_command_runs_all_phases_in_sequence(read_file):
    """The workflow command must orchestrate all phases with guided transitions."""
    # Given
    md = read_file(_WORKFLOW)
    lower = md.lower()

    # When / Then
    for phase in ["discover", "design", "build", "ship"]:
        assert phase in lower, f"workflow must reference the {phase} phase"
    assert "move to" in lower, "workflow must use 'move to [phase]' transition prompts"
    assert "plan mode" in lower, "workflow must enforce plan mode"
    assert "not yet" in lower, "workflow must offer 'not yet' to stay in the current phase"
    assert "move to ship" in lower, "workflow must gate the Build→Ship transition on the user"


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
    targets = [*_ALL_COMMANDS, "plugin/CLAUDE.md", "plugin/skills/session-summary/SKILL.md", "README.md"]
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


def test_debate_round_counts_consistent(read_file):
    """The debate-consensus protocol and the a2a Core must agree on rounds per tier, and `low`
    must run exactly Round 1 (never reach Round 2)."""
    debate = read_file("plugin/protocols/debate-consensus-protocol.md").lower()
    a2a = read_file("plugin/protocols/a2a-communication-protocol.md").lower()
    # a2a Core: trivial=skip; low=R1 only; medium=R1+R2; high=R1+R2+R3; critical=...fresh-eyes
    assert "low=r1 only" in a2a, "a2a Core must state low=R1 only"
    assert "medium=r1+r2" in a2a, "a2a Core must state medium=R1+R2"
    # debate table mirrors it
    assert "round 1 only" in debate, "debate protocol must state 'Round 1 only' for low"
    assert "round 1 + 2" in debate, "debate protocol must state 'Round 1 + 2' for medium"
    # the Round-3 skip line must not claim low reaches Round 2
    assert "round 1 is its only round" in debate, \
        "debate protocol must say low's only round is Round 1 (not that Round 2 is its final round)"


def test_spec_deletion_wording_consistent(repo_root, read_file):
    """Specs are deleted when delivered in code (during Build), not on merge to main. No shipped
    doc may describe spec deletion as happening on 'merge to main'."""
    targets = ["README.md", *(str(p.relative_to(repo_root)) for p in (repo_root / "plugin").rglob("*.md"))]
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
    assert "never re-scores" in read_file("plugin/CLAUDE.md").lower(), \
        "sanity: CLAUDE.md must still state the never-re-scores rule this test pins README against"


def test_readme_discover_no_false_resume_claim(read_file):
    """README must not claim Discover's in-progress draft is saved/resumable across sessions —
    discover.md has no state/file write before Step 7 (final output, after Plan approval); only
    tier/tier_rationale persist earlier (Step 3)."""
    readme = read_file("README.md").lower()
    assert "picked up where you left off" not in readme, \
        "README must not claim the in-progress Discover draft is saved/resumable"


def test_high_risk_floor_list_consistent(read_file):
    """The high-risk surfaces that floor a feature at `high` must be stated identically in the
    README and plugin/CLAUDE.md (token-based, so minor wording differences elsewhere are fine)."""
    readme = read_file("README.md").lower()
    claude = read_file("plugin/CLAUDE.md").lower()
    canonical = ["auth", "secrets", "money", "migration", "deletion", "production config", "concurrency"]
    for token in canonical:
        assert token in claude, f"plugin/CLAUDE.md floor list must name '{token}'"
        assert token in readme, f"README high-risk floor rule must name '{token}'"


def test_discover_writes_no_machine_local_file_into_repo(read_file):
    """discover must NOT write machine-local state into the user's repo — no docs/.gitignore
    and no docs/.context. State lives only under ~/.hercules/ (config.json + state/)."""
    md = read_file(_DISCOVER)
    assert ".gitignore" not in md, "discover must not create a docs/.gitignore for machine-local state"
    assert "docs/.context" not in md, "discover must not write docs/.context into the repo"
    assert "~/.hercules/" in md, \
        "discover must record session state under ~/.hercules/ (registry config.json + state file)"


def test_discover_disambiguates_approval_trigger(read_file):
    """discover Step 5's draft-loop "approved" must not read as the literal, immediate save
    trigger — design.md already disambiguates this at its equivalent step; discover must point
    "approved"/file-creation forward at the real gate (Step 6's Plan approval) instead."""
    md = read_file(_DISCOVER)
    lower = md.lower()
    assert "and i will save the file" not in lower, \
        "Step 5 must not claim saying 'approved' immediately saves the file"
    i_step5 = lower.index("## step 5")
    i_step6 = lower.index("## step 6")
    step5_text = lower[i_step5:i_step6]
    assert "plan approval" in step5_text, \
        "Step 5 must point file-creation at the Step 6 Plan-approval gate"


def test_build_offers_resume_from_home_config(read_file):
    """Build (not all commands) must read the home-config project state and offer to resume by spec."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "resume" in lower, "build must offer resume from the home-config project state"
    assert "~/.hercules/" in lower and "state" in lower, \
        "build must reference ~/.hercules/ (config.json + per-project state file) for resume"
    assert "docs/.context" not in lower, "build must not reference the removed docs/.context file"


def test_build_writes_current_phase_on_plan_approval(read_file):
    """Build must write current_phase: "build" at its own Plan-approval gate, otherwise Step 0's
    resume offer (which checks current_phase == "build") can never fire for a session that crashes
    before any spec has ever been retired — including silently hiding a handoff_note left for that
    session, since Step 0 gates both on the identical condition."""
    md = read_file(_BUILD)
    assert 'current_phase: "build"' in md, \
        "build must write current_phase: \"build\" somewhere in its own flow"
    lower = md.lower()
    assert lower.index("### plan approval") < lower.index('current_phase: "build"'.lower()), \
        "current_phase: \"build\" must be written at the Plan-approval gate, not only at retire"


def test_build_retire_advances_current_spec_to_next_pending(read_file):
    """Step 10's retire-time write must give current_spec an explicit value (the next pending spec,
    or unset) — the original text said 'set current_spec,' with no value at all, which would leave
    current_spec stale on every spec after the first."""
    lower = read_file(_BUILD).lower()
    i_step10 = lower.index("10. **retire the spec.**")
    i_end = lower.index("for a spec scoped to a service")
    retire_text = lower[i_step10:i_end]
    assert "set `current_spec`," not in retire_text, \
        "retire must not leave current_spec's value unspecified"
    assert "set `current_spec` to" in retire_text, \
        "retire must set current_spec to an explicit value (next pending spec, or unset)"


def test_build_ship_now_routes_into_spec_scoped_ship(read_file):
    """"Ship now" in the per-spec cadence routes into Ship's plan flow (default plan presented,
    refined in rounds, executed on acceptance) as a spec-scoped invocation — never an ad-hoc
    inline commit, and never dependent on Ship's session-wide build_complete gate (set true only
    at Build's close-out, after ALL specs are retired)."""
    md = read_file(_BUILD)
    lower = md.lower()
    i_advance = lower.index("**advance.**")
    i_next = lower.index("**write the checkpoint.**")
    advance_step = lower[i_advance:i_next]
    assert "ship now" in advance_step, "build must define the 'ship now' option inside Advance"
    assert "spec-scoped" in advance_step and "/hercules:ship" in advance_step, \
        "'ship now' must route into /hercules:ship's spec-scoped plan flow"
    assert "git add" not in advance_step and "git commit" not in advance_step, \
        "'ship now' must not perform an inline commit — Ship's plan flow owns the commit"
    assert "not retired" in advance_step, \
        "Advance must state a failed spec-scoped ship returns control here, spec not retired"
    assert "build_complete" not in advance_step, \
        "'ship now' must not reference/depend on build_complete — that's Ship's session-wide gate"


def test_ship_spec_scoped_path_preserves_session_gate(read_file):
    """Ship's spec-scoped section scopes everything to the current spec while leaving the
    session-wide contract intact: build_complete stays the close-out gate, no session state is
    written mid-build, the PR belongs to the close-out ship, and failure routes back to Build."""
    md = read_file(_SHIP)
    assert "### Spec-scoped ship" in md, "ship must define the spec-scoped section as a heading"
    i = md.index("### Spec-scoped ship")
    section = md[i:md.index("---", i)]
    assert "Not included — stage if you want" in section, \
        "spec-scoped staging must surface non-spec changes, never sweep them in"
    assert "never writes" in section and 'current_phase: "shipped"' in section \
        and "build_complete" in section and "shipped_commit" in section, \
        "the section must name every session field a spec-scoped ship never writes"
    assert "PR step is omitted" in section and "shipped_pr" in section, \
        "a spec-scoped ship must omit the PR; shipped_pr belongs to the close-out ship"
    assert "Advance prompt" in section and "not retired" in section, \
        "a failed spec-scoped commit/push must return control to Build's Advance prompt"
    assert "residue" in section, \
        "the section must note the close-out ship commits the residue (retired specs, INDEX)"
    assert "Local build is not complete" in md, \
        "the session-wide build_complete refusal must remain for a plain /hercules:ship"
    assert "spec-scoped ship skips this step" in md, \
        "Execution's Record step must be marked session-wide-only (spec-scoped skips it)"


def test_ship_build_and_diagram_agree_on_spec_scoped(read_file):
    """The spec-scoped contract is one decision expressed in three places — build.md's Advance,
    ship.md's section, and the detailed workflow diagram. All three must carry it (lock-step)."""
    for path in (_BUILD, _SHIP, "docs/workflow/workflow-diagram-detailed.html"):
        assert "spec-scoped" in read_file(path).lower(), \
            f"{path} must carry the spec-scoped ship contract (lock-step rule)"


def test_build_bash_path_convention_is_single_and_consistent(read_file):
    """build.md must state exactly one convention for multi-service Bash invocations — not both
    'cd {service-path} && {command}' and 'never a bare relative path' for the same Bash calls."""
    md = read_file(_BUILD)
    assert "cd {service-path}" not in md, \
        "build must not describe a 'cd into the service' Bash convention — it contradicts the " \
        "absolute-path-for-every-Bash-run rule stated later in the same file"
    assert "never a bare relative path" in md, \
        "build must keep the single absolute-path convention for Read/Write/Edit/Bash"


def test_build_session_discovery_filter_not_zero_delivered(read_file):
    """Build Step 1's session filter must not require zero specs delivered — Step 0's resume path
    expects to find a session with some specs already in delivered_specs, so Step 1 must still
    surface a session that has delivered some (but not all) of its specs."""
    md = read_file(_BUILD)
    assert "none delivered yet" not in md, \
        "build Step 1 must not phrase its filter as 'none delivered yet' — read literally that " \
        "excludes any session with partial delivery progress, contradicting Step 0's resume path"
    lower = md.lower()
    i_step1 = lower.index("### step 1")
    i_step2 = lower.index("### step 2")
    assert "still pending" in lower[i_step1:i_step2] or "not yet delivered" in lower[i_step1:i_step2], \
        "build Step 1 must phrase the filter as per-spec pending status, not session-wide zero-delivered"


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
    # Pin the declared Status set on its actual declaration line so a command can't write a
    # status (discover/design) that CLAUDE.md later drops without failing here.
    status_line = next((ln for ln in md.splitlines() if "Status values" in ln), "")
    assert status_line, "CLAUDE.md must declare the INDEX 'Status values' set"
    for status in ("discover", "design", "build", "delivered", "abandoned"):
        assert status in status_line, f"CLAUDE.md 'Status values' must include '{status}'"


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
        assert "docs/.context" not in text, f"{path} must not reference the removed docs/.context file"
        assert "gitignored, never committed" not in text.lower(), \
            f"{path} must not promise an untested 'gitignored, never committed' machine-local file"


def test_claude_md_documents_home_config_state_contract(read_file):
    """plugin/CLAUDE.md must document the split machine-local state: a registry config.json with a
    `projects` map (directory, state_file, repositories) plus per-project state/{slug}.json files."""
    md = read_file("plugin/CLAUDE.md")
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


def test_ship_step_defines_its_execution_contract(read_file):
    """Ship must draft a complete plan in plan mode, wait for approval, then execute automatically."""
    md = read_file(_SHIP)
    lower = md.lower()
    assert "/hercules:ship" in md, "ship must contain its own trigger phrase"
    assert "plan mode" in lower, "ship must enter plan mode to draft the commit plan"
    assert "build_complete" in md, "ship must gate on build_complete from hercules-config"
    assert "index.md" in lower, "ship must include INDEX.md in the default staged set"
    assert "commit message" in lower, "ship must propose a commit message"
    assert "approved" in lower, "ship must wait for approval before executing"
    assert ("conventional" in lower or "feat(" in md or "fix(" in md), \
        "ship must format the suggested message in Conventional Commits format"
    assert "push" in lower, "ship must include a push step in the plan"
    assert "--no-verify" not in md, "ship must never suggest --no-verify"
    assert "--force" not in md, "ship must never suggest --force"
    assert "--force-with-lease" not in md, "ship must never suggest --force-with-lease"
    assert "co-authored" not in lower and "generated with" not in lower, \
        "ship must not add AI attribution to commit messages"
    assert "shipped_commit" in md, "ship must record the commit SHA in hercules-config"


def test_ship_does_not_write_docs_artifacts(read_file):
    """Ship produces git history — it must not write any new docs/ artifact."""
    md = read_file(_SHIP)
    assert "-ship.md" not in md.lower(), "ship must not produce a *-ship.md artifact"
    writing_to_docs = any(
        "docs/" in line and ("write" in line.lower() or "create" in line.lower())
        for line in md.splitlines()
        if "index.md" not in line.lower()
    )
    assert not writing_to_docs, "ship must not create new docs/ artifacts (Build owns those)"


def test_ship_pr_creation_is_conditional_on_gh(read_file):
    """Ship must make PR creation conditional on gh detection — never unconditional."""
    md = read_file(_SHIP)
    lower = md.lower()
    assert "gh pr" in lower, \
        "ship must reference gh pr create for optional PR creation"
    assert "auth" in lower, \
        "ship must check gh auth status before proposing PR creation"
    assert "shipped_pr" in md, \
        "ship must record the PR URL in hercules-config"
    assert "co-authored" not in lower, \
        "ship must not add AI attribution to PR bodies"
    assert "generated with" not in lower, \
        "ship must not add AI attribution to PR bodies"
    assert "existing" in lower or "already" in lower, \
        "ship must detect and handle an existing open PR to avoid duplicates"


def test_build_opens_with_delivery_plan(read_file):
    """Build opens in plan mode and presents a delivery plan (specs, their requirements, order,
    grouping) gated on Plan approval before any code is written."""
    lower = read_file(_BUILD).lower()
    assert "delivery plan" in lower, "build must present a delivery plan in plan mode"
    assert "satisfies" in lower, "the delivery plan must show which requirement each spec satisfies"
    assert lower.index("delivery plan") < lower.index("plan approval"), \
        "the delivery plan is presented before Plan approval"
    assert lower.index("plan approval") < lower.index("auto-execute") if "auto-execute" in lower else True


def test_build_delivery_plan_allows_batching(read_file):
    """The delivery plan lets the user re-batch and set the cadence before approval."""
    lower = read_file(_BUILD).lower()
    assert "re-batch" in lower or "batch" in lower, "delivery plan must allow re-batching specs"
    assert "cadence" in lower, "delivery plan must let the user set the cadence"
    assert "deliver all" in lower and "ship each" in lower, \
        "cadence must offer deliver-all vs ship-each"


def test_build_freezes_and_diff_guards_tests(read_file):
    """Tests are frozen after they're written and machine-enforced with a git diff guard —
    and the freeze is announced with its exits, so the user is never surprised or stuck."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "frozen_test_files" in md, "build must record the frozen test files to state"
    assert "git diff" in lower, "build must git-diff-guard the frozen tests (machine-enforced)"
    assert "frozen" in lower, "build must state the tests are frozen"
    assert "announce the freeze" in lower and "bullets" in lower, \
        "build must announce the freeze verbosely, with the unblock options as bullets"
    assert "frozen_override" in md, \
        "build must offer the same-turn, user-granted frozen_override exit"
    assert "the same turn" in lower or "this turn" in lower, \
        "the freeze announcement must state the unblock happens in the same conversation turn"
    assert 'frozen_hook: "off"' in md, \
        "build must name the per-project opt-out (prompt-only discipline)"


def test_build_round_limit_persisted_with_user_decision(read_file):
    """The 3-round implementation limit is persisted in state and hands the user the decision."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "current_spec_round" in md, "build must persist the round counter in current_spec_round"
    assert "3 rounds" in lower or "round 3" in lower or "three rounds" in lower, \
        "build must cap implementation at 3 rounds"
    assert "user" in lower and ("decide" in lower or "decision" in lower), \
        "after the round limit, the user decides (no silent auto-advance)"


def test_build_writes_checkpoint_after_each_spec(read_file):
    """Build appends a build_progress checkpoint at spec retire (the durable cross-spec record)."""
    md = read_file(_BUILD)
    assert "build_progress" in md, "build must append a build_progress checkpoint entry"


def test_build_quality_gates_are_coc_driven(read_file):
    """Quality-gate thresholds come from the project's code-of-conduct.md — build carries no numbers,
    and the inverted per-tier mutation table is gone."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "code-of-conduct" in lower, "build must defer quality gates to code-of-conduct.md"
    assert "90%" not in md and "88%" not in md and "85%" not in md, \
        "build must not hardcode coverage/mutation thresholds (they live in the CoC)"


def test_build_mutation_gate_runs_in_loop_before_retire(read_file):
    """The mutation gate runs inside the per-spec loop, before the spec is retired — not post-loop —
    so a weak test is fixed while the spec is still live."""
    lower = read_file(_BUILD).lower()
    assert "mutation gate" in lower, "build must have a mutation gate"
    assert lower.index("mutation gate") < lower.index("retire the spec"), \
        "the mutation gate must run before the spec is retired"
    assert lower.index("retire the spec") < lower.index("## cross-check validation"), \
        "the cross-check validation is post-loop, after specs are retired"


def test_build_cross_check_validation_is_post_loop(read_file):
    """Cross-check validation runs after the per-spec loop and before close-out."""
    lower = read_file(_BUILD).lower()
    assert "cross-check" in lower, "build must run a cross-check validation"
    assert lower.index("cross-check") < lower.index("## close-out"), \
        "cross-check must come before close-out"
    assert "match what we set out to build" in lower, \
        "cross-check must verify the delivery matches the original intent"
    assert "build_progress" in lower, \
        "build's cross-check must read from build_progress, matching cynical-reviewer's fallback " \
        "spec-sync write target for when no live spec file exists"


def test_config_registry_is_rebuildable_from_state(read_file):
    """CLAUDE.md must document the registry as a regenerable index rebuilt from the state files."""
    md = read_file("plugin/CLAUDE.md").lower()
    assert "regenerable index" in md, "CLAUDE.md must describe the registry as a regenerable index"
    assert "rebuilt from" in md or "source of truth" in md, \
        "CLAUDE.md must state the state files are the source of truth (registry rebuildable)"
