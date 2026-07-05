"""Delivery commands — Discover and Design phase contracts."""

from __future__ import annotations

import pytest
from tests.conftest import (
    BUILD as _BUILD,
    DESIGN as _DESIGN,
    DISCOVER as _DISCOVER,
    section as _section,
)


_DISCOVER_GUIDANCE = [
    ("waits_for_answers", lambda md, lo: "wait for" in lo,
     "discover command must instruct Claude to wait for user answers"),
    ("classifies_complexity", lambda md, lo: "classif" in lo, "discover command must classify complexity"),
    ("asks_to_confirm_classification", lambda md, lo: "confirm or override" in lo,
     "discover command must ask user to confirm the classification"),
    ("requires_approved", lambda md, lo: "approved" in lo,
     "discover command must require 'approved' before writing"),
    ("gates_file_on_approval", lambda md, lo: "do not create the file until" in lo,
     "discover command must gate file creation on approval"),
    ("uses_docs_root", lambda md, lo: "docs/" in md, "discover command must use docs/ as the default artifact root"),
    ("names_output_file", lambda md, lo: "business-requirements.md" in md,
     "discover command must name the output file with -business-requirements.md suffix"),
    ("template_has_goal", lambda md, lo: "## Goal" in md, "discover template must include ## Goal"),
    ("template_has_users", lambda md, lo: "## Users" in md, "discover template must include ## Users"),
    ("template_has_scope", lambda md, lo: "## Scope" in md, "discover template must include ## Scope"),
    ("template_has_constraints", lambda md, lo: "## Constraints" in md,
     "discover template must include ## Constraints"),
    ("template_has_success_criteria", lambda md, lo: "## Success criteria" in md,
     "discover template must include ## Success criteria"),
    ("has_stakeholders_approved_phrase", lambda md, lo: "stakeholders approved" in md,
     "discover must include the 'stakeholders approved' trigger phrase"),
    ("offers_skip_review_phrase", lambda md, lo: "skip stakeholder review" in lo,
     "discover must offer the 'skip stakeholder review' escape phrase"),
    ("asks_about_api_contracts", lambda md, lo: "API contracts" in md,
     "discover Group D must ask about existing API contracts and ADRs"),
    ("enforces_plan_mode", lambda md, lo: "plan mode" in lo, "discover must enforce plan mode at the top"),
    ("accepts_prd_adr_context", lambda md, lo: "PRD" in md or "ADR" in md,
     "discover must explicitly accept rich upfront context (PRDs, ADRs)"),
    ("constrains_to_business_language", lambda md, lo: "business language" in lo,
     "discover must constrain business-requirements to business language (no code/classes)"),
]


@pytest.mark.parametrize("predicate,reason", [(p, r) for _, p, r in _DISCOVER_GUIDANCE],
                         ids=[i for i, _, _ in _DISCOVER_GUIDANCE])
def test_discover_step_guides_the_user(read_file, predicate, reason):
    md = read_file(_DISCOVER)
    assert predicate(md, md.lower()), reason

_DESIGN_CONTRACT = [
    ("reads_business_requirements", lambda md, lo: "business-requirements.md" in md,
     "design command must read the *-business-requirements.md artifact"),
    ("uses_docs_root", lambda md, lo: "docs/" in md, "design command must use docs/ as the default session root"),
    ("reads_tier_from_state", lambda md, lo: "tier" in lo and "state" in lo,
     "design must read the tier from state (complexity is scored once in Discover)"),
    ("does_not_rescore", lambda md, lo: "re-score" in lo or "re-scor" in lo,
     "design must state it does not re-score complexity"),
    ("requires_approved", lambda md, lo: "approved" in lo, "design command must require approval"),
    ("blocks_write_until_approval", lambda md, lo: "do not" in lo,
     "design command must block writing until approval"),
    ("cites_coverage_evidence", lambda md, lo: "quote" in lo or "cite" in lo,
     "design command must cite coverage evidence"),
    ("performs_coverage_check", lambda md, lo: "coverage" in lo,
     "design command must perform requirements coverage check"),
    ("names_uncovered_items", lambda md, lo: "not covered" in lo or "uncovered" in lo,
     "design command must name uncovered items"),
    ("documents_n_minus_1_collapse", lambda md, lo: "n-1" in lo, "design command must document the n-1 collapse"),
    ("emits_numbered_sub_specs", lambda md, lo: "-spec-" in md,
     "design command must emit numbered sub-spec files (no separate design.md)"),
    ("no_design_md_artifact", lambda md, lo: "design.md" not in md,
     "design command must not produce a *-design.md artifact"),
    ("carries_mocking_guidance", lambda md, lo: "mocking:" in lo or "what must be mocked" in lo,
     "design Test-suite template must carry the mocking guidance the engineers follow (QA owns the WHAT)"),
    ("has_stakeholders_approved_phrase", lambda md, lo: "stakeholders approved" in md,
     "design must include the 'stakeholders approved' trigger phrase"),
    ("offers_skip_review_phrase", lambda md, lo: "skip stakeholder review" in lo,
     "design must offer the 'skip stakeholder review' escape phrase"),
    ("asks_about_api_contracts", lambda md, lo: "API contracts" in md,
     "design Group A must ask about existing API contracts before new architecture questions"),
    ("mentions_adrs", lambda md, lo: "ADR" in md, "design Group A must mention ADRs"),
    ("enforces_plan_mode", lambda md, lo: "plan mode" in lo, "design must enforce plan mode at the top"),
    ("produces_delivery_order", lambda md, lo: "spec-" in lo or "spec-01" in lo or "delivery order" in lo,
     "design must produce numbered sub-spec files with a delivery order section"),
    ("instructs_spec_deletion", lambda md, lo: "git rm" in md or "delete" in lo,
     "design must instruct that spec files are deleted after delivery"),
    ("gates_on_satisfies_header", lambda md, lo: "satisfies" in lo,
     "design gate must tie every requirement to a sub-spec via its satisfies header"),
]


@pytest.mark.parametrize("predicate,reason", [(p, r) for _, p, r in _DESIGN_CONTRACT],
                         ids=[i for i, _, _ in _DESIGN_CONTRACT])
def test_design_step_declares_each_contract_clause(read_file, predicate, reason):
    md = read_file(_DESIGN)
    assert predicate(md, md.lower()), reason

def test_readme_discover_no_false_resume_claim(read_file):
    """README must not claim Discover's in-progress draft is saved/resumable across sessions —
    discover.md has no state/file write before Step 7 (final output, after Plan approval); only
    tier/tier_rationale persist earlier (Step 3)."""
    readme = read_file("README.md").lower()
    assert "picked up where you left off" not in readme, \
        "README must not claim the in-progress Discover draft is saved/resumable"

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

def test_discover_resolves_artifact_root(read_file):
    """discover Step 0 must resolve the artifact root from code-of-conduct.md, defaulting to docs/."""
    md = read_file(_DISCOVER)
    lower = md.lower()
    assert "artifact root" in lower, "discover must resolve the artifact root in Step 0"
    assert "code-of-conduct.md" in lower, "discover must let code-of-conduct.md override the docs location"
    assert "docs_root" in md, "discover must record the resolved path as docs_root in the home-config entry"

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
    """discover Step 0 must surface code-of-conduct as a quality lever AND offer to
    generate it — pinned to the generator skill name inside Step 0 ('generate' alone
    matched the plan-mode boilerplate's 'regenerate')."""
    md = read_file(_DISCOVER)
    step0 = md[md.index("## Step 0"):md.index("## Step 1")]
    assert "code-of-conduct-generator" in step0, \
        "Step 0 must offer the generator skill by name"
    assert "quality" in step0.lower(), "Step 0 must frame the CoC as a quality lever"

def test_session_discovery_is_state_driven_first(read_file):
    """Under keep_specs delivered spec files stay on disk forever — a pure filesystem
    scan would list finished sessions as deliverable. Pending must be defined by state
    (pending_specs / not in delivered_specs), with the disk scan as the no-state
    fallback."""
    build = read_file(_BUILD)
    step1 = build[build.index("### Step 1"):build.index("### Step 2")]
    assert "pending_specs" in step1 or "delivered_specs" in step1, \
        "Step 1's definition of pending must consult state, not file existence alone"

def test_discover_step0_defers_registry_write(read_file):
    """Step 0 runs inside plan mode (no writes) — recording docs_root there contradicts
    the same file's own Step 3 workaround. The write must be deferred to Step 7."""
    discover = read_file(_DISCOVER)
    step0 = discover[discover.index("## Step 0"):discover.index("## Step 1")]
    assert "Step 7" in step0, \
        "Step 0 must note docs_root now and let Step 7's session-init write persist it"

def test_discover_step7_preserves_existing_registry_keys(read_file):
    """Feature 2's Discover rewriting the registry entry with 'empty repositories' wipes
    repositories/frozen_hook/keep_specs — fields documented to persist across features.
    The write must create-or-update, preserving unknown keys."""
    discover = read_file(_DISCOVER)
    step7 = discover[discover.index("## Step 7"):]
    assert "empty\n`repositories`" not in step7 and "empty `repositories`" not in step7, \
        "Step 7 must not unconditionally blank the repositories map"
    assert "preserv" in step7, \
        "Step 7 must preserve existing registry keys (repositories, frozen_hook, keep_specs)"

def test_design_write_gate_sentence_is_pinned(read_file):
    """Design's actual write gate — deleting it left the suite green because 'approved'
    matched 'stakeholders approved' and 'do not' matched 'do not re-score'."""
    approval = _section(read_file(_DESIGN), "## Step 8 — Plan approval", "## Step 9",
                        label=_DESIGN)
    assert "**Do not write the specs until the user approves.**" in approval

def test_discover_batches_groups_for_plainly_small_ideas(read_file):
    """Five one-per-turn question groups for a small fix is the drop-out moment for solo
    devs — a plainly small idea gets all five groups in one message (depth scales, the
    groups stay; note: the tier isn't scored until Step 3, so this keys on the idea)."""
    discover = read_file(_DISCOVER)
    step2 = _section(discover, "## Step 2", "## Step 3", label=_DISCOVER)
    assert "one message" in step2, "small ideas must get the five groups batched"
