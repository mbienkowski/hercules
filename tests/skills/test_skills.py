"""Tests that verify the skill list is complete and follows the plugin contract."""

import json
import re
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
# Module-level lists so tests can parametrize over each file (one cell per file).
_SKILL_PATHS = sorted(_PLUGIN.glob("skills/*/SKILL.md"))
_DOC_FILES = sorted(_PLUGIN.glob("commands/*.md")) + _SKILL_PATHS + sorted(_PLUGIN.glob("agents/*.md"))


_SKILL_LIST = [
    "solution-complexity-scoring", "code-of-conduct-generator",
    "learnings", "write-test-scenarios", "session-summary",
]

_ACTIVE_SKILLS = frozenset({
    "solution-complexity-scoring", "code-of-conduct-generator", "learnings",
    "write-test-scenarios", "session-summary",
})

_SKILL_NAME_RE = re.compile(r"(?m)^name:\s*(\S+)\s*$")

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

_BARE_SUBCOMMAND_RE = re.compile(r"hercules\s+(origin-trace|sessions)\b")


def test_all_five_skills_are_present(repo_root):
    """All 5 listed skills must have a corresponding SKILL.md in skills/."""
    # Given
    existing = {p.parent.name for p in (repo_root / "plugin" / "skills").glob("*/SKILL.md")}

    # When
    missing = [n for n in _SKILL_LIST if n not in existing]
    extra = [n for n in existing if n not in _SKILL_LIST]

    # Then
    assert not missing, f"Listed skills missing from skills/: {missing}"
    assert not extra, (
        f"skills/ contains directories not in the canonical list: {extra}"
    )


@pytest.mark.parametrize("path", _SKILL_PATHS, ids=lambda p: p.parent.name)
def test_each_skill_file_declares_its_purpose_and_preconditions(path):
    """Every skill declares its use-case; active skills also define a precondition hard-stop clause."""
    md = path.read_text()
    lower = md.lower()
    name = path.parent.name
    assert md.startswith("---"), f"{name}/SKILL.md must open with YAML frontmatter"
    m = _SKILL_NAME_RE.search(md)
    assert m is not None, f"{name}/SKILL.md frontmatter missing `name:`"
    assert m.group(1) == name, f"{name}/SKILL.md frontmatter name={m.group(1)!r} must match directory {name!r}"
    assert "description:" in md, f"{name}/SKILL.md frontmatter missing `description:`"
    desc_m = re.search(r"(?m)^description:\s*(.+)$", md)
    assert desc_m, f"{name}/SKILL.md frontmatter missing a description value"
    assert any(t in desc_m.group(1).lower() for t in ("use ", "use in", "use on", "use when", "use to")), \
        f"{name}/SKILL.md description must state WHEN to use the skill"
    assert "code-of-conduct" in lower, \
        f"{name}/SKILL.md must reference the project's code-of-conduct (any capitalization)"
    if name in _ACTIVE_SKILLS:
        assert "precondition" in lower, f"{name}/SKILL.md (active skill) must declare a Preconditions clause"
        assert re.search(r"\bstop\b", lower), f"{name}/SKILL.md (active skill) must hard-stop on precondition miss"


def test_skills_carry_no_framework_assumptions(repo_root, skill_files):
    """No shipped skill must name a concrete framework or stack — skills stay generic."""
    # Given
    violations = []

    # When
    for path in skill_files:
        md = path.read_text()
        for pattern in _STACK_LITERAL_PATTERNS:
            hit = pattern.search(md)
            if hit:
                violations.append(f"{path.parent.name}/SKILL.md: matched {hit.group()!r}")

    # Then
    assert not violations, (
        "Skills contain stack literals:\n" + "\n".join(f"  {v}" for v in violations)
    )


@pytest.mark.parametrize("path", _DOC_FILES, ids=lambda p: p.stem)
def test_plugin_doc_uses_double_dash_subcommand_prefix(path):
    """All plugin docs (commands/, skills/, agents/) must use 'hercules --<subcommand>', never the
    bare form — the bare form is forwarded to claude as a prompt instead of running natively."""
    hit = _BARE_SUBCOMMAND_RE.search(path.read_text())
    assert hit is None, \
        f"{path.name} uses the bare subcommand form {hit.group()!r} — write 'hercules --<name>'"



def test_session_summary_skill_exists(repo_root):
    """session-summary must exist as a plugin skill for team handoff support."""
    skill_file = repo_root / "plugin" / "skills" / "session-summary" / "SKILL.md"
    assert skill_file.exists(), "plugin/skills/session-summary/SKILL.md must exist"


def test_session_summary_skill_covers_handoff_fields(repo_root):
    """session-summary SKILL.md must reference delivered_specs and handoff context."""
    md = (repo_root / "plugin" / "skills" / "session-summary" / "SKILL.md").read_text()
    assert "delivered_specs" in md, \
        "session-summary must read delivered_specs from the per-project state file"
    assert "~/.hercules/" in md and "state" in md, \
        "session-summary must read machine-local state from ~/.hercules/ (the per-project state file)"
    assert "docs/.context" not in md, \
        "session-summary must not reference the removed docs/.context file"
    assert "handoff" in md.lower(), \
        "session-summary must produce a handoff note"


def test_skill_list_matches_plugin_settings(repo_root):
    """_SKILL_LIST and plugin/settings.json skills[] must stay in sync."""
    settings = json.loads((repo_root / "plugin" / "settings.json").read_text())
    manifest = settings.get("skills", [])
    assert sorted(manifest) == sorted(_SKILL_LIST), (
        "plugin/settings.json skills[] and _SKILL_LIST are out of sync.\n"
        f"  In settings.json only: {sorted(set(manifest) - set(_SKILL_LIST))}\n"
        f"  In _SKILL_LIST only: {sorted(set(_SKILL_LIST) - set(manifest))}"
    )


_COC_GENERATOR = "plugin/skills/code-of-conduct-generator/SKILL.md"


def test_code_of_conduct_generator_uses_plan_mode(repo_root):
    """code-of-conduct-generator must use plan mode so the user reviews the full CoC before it is written."""
    md = (repo_root / _COC_GENERATOR).read_text()
    assert "EnterPlanMode" in md, \
        "code-of-conduct-generator must call EnterPlanMode to present the CoC draft for review"
    assert "ExitPlanMode" in md, \
        "code-of-conduct-generator must call ExitPlanMode after the user approves"


def test_code_of_conduct_generator_asks_minimum_questions(repo_root):
    """code-of-conduct-generator must ask at least 5 questions in a single batch — not a trickle."""
    md = (repo_root / _COC_GENERATOR).read_text()
    lower = md.lower()
    assert "5" in md or "five" in lower, \
        "code-of-conduct-generator must ask at least 5 questions"
    assert "batch" in lower or "single" in lower or "at once" in lower or "trickle" in lower, \
        "code-of-conduct-generator must send all questions in one message, not trickle them"


def test_code_of_conduct_generator_prohibits_attribution(repo_root):
    """The generated CoC must not contain Hercules/AI attribution — the skill must state this explicitly."""
    md = (repo_root / _COC_GENERATOR).read_text()
    lower = md.lower()
    has_prohibition = (
        "no hercules" in lower
        or "no ai" in lower
        or "no generator" in lower
        or "no credit" in lower
        or "no mention" in lower
        or "attribution" in lower
    )
    assert has_prohibition, \
        "code-of-conduct-generator must explicitly prohibit AI/Hercules attribution in the output file"


def test_code_of_conduct_generator_defines_required_sections(repo_root):
    """code-of-conduct-generator must define Architecture, Testing, Quality Gates, and Delivery as required
    sections, each with a 'why' explanation before the bullets."""
    md = (repo_root / _COC_GENERATOR).read_text()
    lower = md.lower()
    assert "architecture" in lower, \
        "code-of-conduct-generator must include an Architecture section in the output structure"
    assert "testing" in lower, \
        "code-of-conduct-generator must include a Testing section in the output structure"
    assert "quality" in lower or "gate" in lower, \
        "code-of-conduct-generator must include a Quality Gates section (name may vary)"
    assert "mutation" in lower, \
        "code-of-conduct-generator must mention mutation testing in the Quality Gates section"
    assert "delivery" in lower, \
        "code-of-conduct-generator must include a Delivery section in the output structure"
    assert "pattern" in lower, \
        "code-of-conduct-generator must scan for and document design patterns in Architecture"
    assert "why" in lower or "reason" in lower or "explain" in lower, \
        "code-of-conduct-generator must instruct sections to open with a 'why' explanation"


def test_code_of_conduct_generator_detects_file_naming_convention(repo_root):
    """The generator finds an existing code-of-conduct case-insensitively — a repo may carry
    `code-of-conduct.md` or `CODE_OF_CONDUCT.md` (on Linux, two distinct files) — so an
    uppercase-only repo is not mistaken for having no standards."""
    md = (repo_root / _COC_GENERATOR).read_text().lower()
    assert "case-insensitiv" in md, \
        "the generator must scan for the code-of-conduct file case-insensitively"
    assert "any capitalization" in md or "any casing" in md, \
        "the generator must state any capitalization of the filename counts as the same file"


def test_coc_filename_regex_matches_any_casing():
    """The detection regex is case-insensitive and separator-tolerant but ANCHORED — it matches
    the real file at any casing and rejects a draft/variant that is not the code-of-conduct."""
    coc_re = re.compile(r"(?i)^code[-_ ]of[-_ ]conduct\.md$")
    for name in ("code-of-conduct.md", "CODE_OF_CONDUCT.md", "Code-Of-Conduct.md", "code_of_conduct.md"):
        assert coc_re.match(name), f"{name} should be detected as a code-of-conduct file"
    for name in ("code-of-conduct-draft.md", "code-of-conduct-v2.md", "conduct.md", "codeofconduct.md"):
        assert not coc_re.match(name), f"{name} must NOT be treated as the code-of-conduct"


def test_skills_read_the_coc_case_insensitively(skill_files):
    """A skill that reads the project code-of-conduct must find it at any capitalization — a
    'Read `code-of-conduct.md`' / '`code-of-conduct.md` if present' instruction misses
    CODE_OF_CONDUCT.md on Linux (the same file). Naming references are not matched here."""
    forbidden = ("`code-of-conduct.md` if present", "Read `code-of-conduct.md`", "read `code-of-conduct.md`")
    for path in skill_files:
        text = path.read_text()
        for pat in forbidden:
            assert pat not in text, \
                f"{path.parent.name}/SKILL.md: '{pat}' is a fixed-lowercase CoC read — use 'any capitalization'"


def test_generator_documents_multi_match_precedence(read_file):
    """With >1 code-of-conduct match (e.g. a lowercase technical file AND a .github community
    doc), the generator must never silently pick one — it surfaces what it found and confirms."""
    skill = read_file(_COC_GENERATOR).lower()
    assert "more than one" in skill or "multiple" in skill, \
        "generator must address the multi-match case"
    assert "never silently" in skill or "confirm" in skill, \
        "on multiple matches the generator must confirm with the user, not silently pick"


def test_code_of_conduct_generator_handles_existing_coc_safely(repo_root):
    """When CoC exists, generator must update incrementally — never restructure or delete content."""
    md = (repo_root / _COC_GENERATOR).read_text()
    lower = md.lower()
    assert "existing" in lower or "re-run" in lower or "update mode" in lower, \
        "code-of-conduct-generator must describe behaviour when a CoC already exists"
    assert "never" in lower and any(w in lower for w in ("reorder", "restructure", "delete", "rename")), \
        "code-of-conduct-generator must explicitly prohibit restructuring an existing CoC"
    assert "gap" in lower or "missing" in lower or "conflict" in lower, \
        "code-of-conduct-generator must perform gap analysis when re-running against an existing CoC"
    assert "addition" in lower or "append" in lower or "insert" in lower, \
        "code-of-conduct-generator must describe the additions-only update strategy"


def test_coc_generator_creates_lowercase_by_default(read_file):
    """When NO code-of-conduct exists, the generator defaults the new file to the lowercase
    `code-of-conduct.md` (uppercase CODE_OF_CONDUCT.md is GitHub's community-doc convention,
    which would self-inflict the two-file collision). It never proposes uppercase unprompted."""
    skill = read_file("plugin/skills/code-of-conduct-generator/SKILL.md")
    assert "→ `CODE_OF_CONDUCT.md`" not in skill, \
        "generator must not PROPOSE an uppercase output filename by default"
    assert "`code-of-conduct.md`" in skill, \
        "the default create name must be the lowercase code-of-conduct.md"


def test_learnings_skill_names_the_phase_that_invokes_it(read_file):
    """build.md invokes learnings at Build close-out (every tier); a 'ship time' trigger routes
    the model to Ship — which never invokes it and runs prompt-free — so nothing gets written."""
    skill = read_file("plugin/skills/learnings/SKILL.md")
    if "ship time" in skill.lower():
        assert "learnings" in read_file("plugin/commands/ship.md"), \
            "learnings anchors to 'ship time' but only Build invokes it — rephrase the trigger"


def test_generator_states_the_directive_budget(read_file):
    """The bands must be the literal rule sentences, the ceiling must reconcile with the
    ~150 adherence line (100 base + 70 = 170 — the trade must be admitted), and the
    cut/merge advice must not contradict update mode's additions-only law."""
    skill = read_file("plugin/skills/code-of-conduct-generator/SKILL.md")
    assert "aim for\n**30–40** directives" in skill or "aim for **30–40** directives" in skill
    assert "up to **50**" in skill
    assert "**70 is the hard ceiling**" in skill
    assert "one bullet = one directive" in skill, "the counting unit must be defined"
    assert "adherence" in skill, \
        "past-40 must admit the trade against the ~150 adherence line, not hide it"
    assert "update mode" in skill and "never cut or merged" in skill, \
        "the cut/merge advice must carve out update mode (additions only)"
    assert "mutation tool exists" in skill or "mutation tool is present" in skill, \
        "the enforced mutation gate must be conditioned on a mutation tool being present"


def test_learnings_store_has_an_entry_budget_and_eviction_criterion(read_file):
    """Discover reads the whole store, so it is instruction load like the CoC: the cap
    must be the literal rule sentence and eviction criterion-driven."""
    skill = read_file("plugin/skills/learnings/SKILL.md")
    assert "keep **20–30** entries" in skill
    assert "**40 is the hard ceiling**" in skill
    low = skill.lower()
    assert "universal" in low and "importan" in low, \
        "eviction must be criterion-driven: keep by universality and importance"


# ── code-of-conduct-generator: the v3 evidence-first, enforced-only flow ───────
# New tests match a whitespace-collapsed read so a pinned phrase survives line-wrapping.

def _coc_flat(read_file):
    return " ".join(read_file(_COC_GENERATOR).split())


def test_coc_generator_enters_plan_mode_and_offers_modes(read_file):
    """Plan mode opens the flow before any scan, with a roadmap, and offers Quick vs Thorough
    so a small repo is not dragged through the full ceremony."""
    flat = _coc_flat(read_file)
    assert "Call `EnterPlanMode` first, before any scanning" in flat
    assert "chat summary of the flow" in flat
    assert "Quick" in flat and "Thorough" in flat and "low-stakes" in flat


def test_coc_generator_drafts_evidence_first_enforced_only(read_file):
    """The draft is built only from scan observations + user answers, and the emitted file states
    only what is enforced today — no aspirational (target) markers live in the file."""
    flat = _coc_flat(read_file)
    assert "Draft rules only from scan observations and user answers" in flat
    assert "enforced today" in flat
    assert "`(target)`" not in flat, "v3 emits an enforced-only file — no (target) markers"


def test_coc_generator_recommends_unmet_standards_in_chat(read_file):
    """Recommended-but-unmet standards are offered in conversation, not written into the file;
    a mutation gate ships only when a mutation tool exists, else it is a chat recommendation."""
    flat = _coc_flat(read_file)
    assert "offered in\n chat".replace("\n ", " ") in flat or "offered in chat" in flat
    assert "mutation testing is a chat recommendation, never a file rule" in flat


def test_coc_generator_scan_is_bounded_and_size_adaptive(read_file):
    """The scan is hard-capped at 5 minutes, config-first, and size-adaptive — a large/monorepo
    proceeds sampled and invites the user rather than blocking."""
    flat = _coc_flat(read_file)
    assert "**5-minute cap**" in flat
    assert "sizing probe" in flat
    assert "read\n manifests and config first".replace("\n ", " ") in flat or "read manifests and config first" in flat
    assert "proceed sampled and invite the user to point at key modules" in flat


def test_coc_generator_reconciles_config_against_code(read_file):
    """A rule the config states but the sampled code violates becomes a question, never an
    enforced rule — the CoC never enforces aspirational config nobody follows."""
    flat = _coc_flat(read_file)
    assert "Reconcile config\n against code".replace("\n ", " ") in flat or "Reconcile config against code" in flat
    assert "becomes a Step-4 question, never\n an enforced rule".replace("\n ", " ") in flat \
        or "becomes a Step-4 question, never an enforced rule" in flat


def test_coc_generator_mines_git_history(read_file):
    """Rules come from what the repo's own history testifies to — commit convention, branch and
    merge shape, releases — under a bounded history read."""
    flat = _coc_flat(read_file)
    assert "`git log -n 200` for the commit convention" in flat
    assert "branch\n names and merge shape".replace("\n ", " ") in flat or "branch names and merge shape" in flat
    assert "`git tag` for releases" in flat


def test_coc_generator_is_deterministic_and_resumable(read_file):
    """A fixed question-priority order keeps runs deterministic, and scan+answers persist so a
    cancelled run resumes instead of restarting the scan."""
    flat = _coc_flat(read_file)
    assert "fixed\n question-priority order".replace("\n ", " ") in flat or "fixed question-priority order" in flat
    assert "stay deterministic" in flat
    assert "~/.hercules/state/{slug}-coc.json" in flat
    assert "re-invoke resumes" in flat
    assert "Plan mode blocks writes" in flat, "resumability must not rely on a plan-mode write"


def test_coc_generator_output_leads_with_must_block_and_inline_checks(read_file):
    """The emitted CoC leads with a flat Non-negotiables (MUST) block, and every rule names its
    mechanical check inline and is tagged MUST or SHOULD."""
    flat = _coc_flat(read_file)
    assert "`## Non-negotiables (MUST)` block" in flat
    assert "names its\n **mechanical check** inline".replace("\n ", " ") in flat \
        or "names its **mechanical check** inline" in flat
    assert "tagged **MUST** or\n **SHOULD**".replace("\n ", " ") in flat or "tagged **MUST** or **SHOULD**" in flat


def test_coc_generator_thresholds_are_grounded_not_padded(read_file):
    """A numeric threshold must quote a user answer or a computed repo statistic, never a padded
    default; the file scales to the evidence (a thin repo ships a small seed)."""
    flat = _coc_flat(read_file)
    assert "quote a user answer or a computed repo statistic, never a padded" in flat
    assert "small, clearly-labelled seed, never padded to fill a band" in flat


def test_coc_generator_runs_gap_pass_then_red_team(read_file):
    """The coverage-map runs once as a stack-gated gap detector after the evidence-first draft,
    then one challenger red-teams; the full trio is opt-in, not the default."""
    flat = _coc_flat(read_file)
    assert "Run the coverage-map once as a **gap detector**" in flat
    assert "stack-gated" in flat
    assert "**red-team** the draft: one challenger" in flat
    assert "full\n trio (lead-architect, senior-qa-engineer, challenger) is opt-in".replace("\n ", " ") in flat \
        or "full trio (lead-architect, senior-qa-engineer, challenger) is opt-in" in flat


def test_coc_generator_defers_debate_mechanics_and_advisors_are_read_only(read_file):
    """Consent + round mechanics live in CLAUDE.md (referenced, never restated); advisors carry
    the A2A Core and return findings only."""
    flat = _coc_flat(read_file)
    assert "§ Sub-agent consent" in flat and "CLAUDE.md § Debate protocol" in flat
    assert "A2A Core" in flat
    assert "return findings only, never\n write".replace("\n ", " ") in flat \
        or "return findings only, never write" in flat
    raw = read_file(_COC_GENERATOR).lower()
    assert "round 1" not in raw and "cross-examin" not in raw


def test_coc_generator_validation_gate_is_strict_and_auditable(read_file):
    """The gate holds the draft until every rule is unambiguous, conflict-free, evidence-backed,
    and mechanically checkable; citations are emitted for audit and a sample re-verified."""
    flat = _coc_flat(read_file)
    assert "reads exactly one way" in flat
    assert "conflicts with no other" in flat
    assert '"it looks nice" is not proof' in flat
    assert "restates the rule as a platitude is not proof either" in flat
    assert "names an objective mechanical check" in flat
    assert "unstructured reviewer judgment is rejected" in flat
    assert "auditable\n appendix".replace("\n ", " ") in flat or "auditable appendix" in flat


def test_coc_generator_feedback_is_surgical(read_file):
    """Feedback applies surgically with a diff; the whole draft regenerates only when the user
    reopens the scope — an approved rule is never silently mutated."""
    flat = _coc_flat(read_file)
    assert "Feedback applies **surgically**" in flat
    assert "diff of exactly what changed" in flat
    assert "regenerate the whole draft only when the user reopens the scope" in flat


def test_coc_generator_surfaces_only_genuine_decisions(read_file):
    """The user is shown only the genuine decisions, ranked by marginal information so obvious
    hygiene never outranks a repo-specific invariant — not a long list to curate."""
    flat = _coc_flat(read_file)
    assert "genuine decisions" in flat
    assert "marginal information" in flat
    assert "do not hand the user a long list to curate" in flat


def test_coc_generator_commit_stages_before_committing(read_file):
    """The confirmed bug fix: stage then commit via pathspec so a brand-new untracked file
    commits, and the user's other staged work is never reset or swept in."""
    flat = _coc_flat(read_file)
    assert "**stage then commit**" in flat
    assert "`git add -- <paths>` then" in flat
    assert "never reset or unstage the user's other work" in flat


def test_coc_generator_ship_is_self_contained_and_offer_only(read_file):
    """Attribution goes only to the commit message, push is offer-only, no /hercules:ship dep."""
    flat = _coc_flat(read_file)
    assert "Attribution lives in the commit message, never in the file" in flat
    assert "never push automatically" in flat
    assert "/hercules:ship" not in flat


def test_coc_generator_forbids_hercules_internals_bleed(read_file):
    """The emitted file states the target repo's standards only; Hercules process internals never
    leak into a user's file."""
    flat = _coc_flat(read_file)
    assert "target repository's" in flat
    assert "Hercules's own process internals" in flat and "spec-first flow" in flat


def test_coc_generator_guards_behavioral_doc_and_resolves_target(read_file):
    """A lone behavioural Contributor Covenant is not treated as an engineering standard; the
    target repo is resolved (asking when ambiguous) and one CoC is generated per repo."""
    flat = _coc_flat(read_file)
    assert "Contributor Covenant is not an engineering standard" in flat
    assert "CLAUDE.md § Code-of-conduct resolution" in flat
    assert "ask the user\n which repo the CoC is for".replace("\n ", " ") in flat \
        or "ask the user which repo the CoC is for" in flat
    assert "one CoC per repo, never merged" in flat


def test_coc_generator_points_to_the_coverage_map(read_file):
    """The exhaustive checklist lives in the companion coverage-map.md, which the skill reads
    during the scan — keeping SKILL.md lean."""
    flat = _coc_flat(read_file)
    assert "coverage-map.md" in flat


def test_coverage_map_exists_and_is_cited(read_file):
    """The coverage-map ships with the tier legend, stack flags, and its primary-source anchors,
    and is marked an internal scan aid, not CoC output."""
    cmap = read_file("plugin/skills/code-of-conduct-generator/coverage-map.md")
    assert "not CoC output" in cmap
    assert "P0" in cmap and "P1" in cmap and "[fe]" in cmap and "[be]" in cmap
    for anchor in ("OWASP ASVS", "SLSA", "SemVer", "SRE", "12-Factor", "RFC-2119"):
        assert anchor in cmap, f"coverage-map must cite {anchor}"
    assert "(conv)" in cmap, "convention gaps must be marked (conv)"


def test_coc_generator_steps_are_in_execution_order(read_file):
    """Structural: the numbered steps appear in order — a reshuffled skill fails."""
    skill = read_file(_COC_GENERATOR)
    order = ["### Step 1", "### Step 2", "### Step 3", "### Step 4",
             "### Step 5", "### Step 6", "### Step 7", "### Step 8", "### Step 9"]
    positions = [skill.index(s) for s in order]
    assert positions == sorted(positions), "the steps must appear in execution order"
