"""Tests that verify the skill list is complete and follows the plugin contract."""

import json
import re
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[2] / "dist" / "claude-code"
# Module-level lists so tests can parametrize over each file (one cell per file).
_SKILL_PATHS = sorted(_PLUGIN.glob("skills/*/SKILL.md"))
_DOC_FILES = sorted(_PLUGIN.glob("commands/*.md")) + _SKILL_PATHS + sorted(_PLUGIN.glob("agents/*.md"))


_SKILL_LIST = [
    "code-of-conduct-generator", "learnings", "write-test-scenarios",
    # Reference skill: carries the operational sections that plugin-root CLAUDE.md cannot load
    # (per Claude Code plugins-reference); auto-loads during any phase. Not an active procedure.
    "hercules-reference",
]

_ACTIVE_SKILLS = frozenset({
    "code-of-conduct-generator", "learnings", "write-test-scenarios",
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


def test_all_listed_skills_are_present(repo_root):
    """Every skill in the canonical list must have a corresponding SKILL.md in skills/."""
    # Given
    existing = {p.parent.name for p in (repo_root / "dist" / "claude-code" / "skills").glob("*/SKILL.md")}

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





def test_skill_list_matches_plugin_settings(repo_root):
    """_SKILL_LIST and plugin/settings.json skills[] must stay in sync."""
    settings = json.loads((repo_root / "dist" / "claude-code" / "settings.json").read_text())
    manifest = settings.get("skills", [])
    assert sorted(manifest) == sorted(_SKILL_LIST), (
        "dist/claude-code/settings.json skills[] and _SKILL_LIST are out of sync.\n"
        f"  In settings.json only: {sorted(set(manifest) - set(_SKILL_LIST))}\n"
        f"  In _SKILL_LIST only: {sorted(set(_SKILL_LIST) - set(manifest))}"
    )


_COC_GENERATOR = "dist/claude-code/skills/code-of-conduct-generator/SKILL.md"


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


def test_coc_matcher_resolves_this_repos_real_coc_file():
    """The matcher must fire on this repo's ACTUAL on-disk code-of-conduct file, not only synthetic
    names — the exact failure that started this feature (a real CoC silently missed). Rename-safe:
    it scans the repo root from disk, so renaming the file to a non-matching name is caught here."""
    repo_root = Path(__file__).resolve().parents[2]
    coc_re = re.compile(r"(?i)^code[-_ ]of[-_ ]conduct\.md$")
    matches = [p.name for p in repo_root.iterdir() if p.is_file() and coc_re.match(p.name)]
    assert matches, "repo root must hold a code-of-conduct file the matcher resolves (rename-safe guard)"


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
    skill = read_file("dist/claude-code/skills/code-of-conduct-generator/SKILL.md")
    assert "→ `CODE_OF_CONDUCT.md`" not in skill, \
        "generator must not PROPOSE an uppercase output filename by default"
    assert "`code-of-conduct.md`" in skill, \
        "the default create name must be the lowercase code-of-conduct.md"


def test_learnings_skill_names_the_phase_that_invokes_it(read_file):
    """build.md invokes learnings at Build close-out (every tier); a 'ship time' trigger routes
    the model to Ship — which never invokes it and runs prompt-free — so nothing gets written."""
    skill = read_file("dist/claude-code/skills/learnings/SKILL.md")
    if "ship time" in skill.lower():
        assert "learnings" in read_file("dist/claude-code/commands/ship.md"), \
            "learnings anchors to 'ship time' but only Build invokes it — rephrase the trigger"


def test_generator_states_the_directive_budget(read_file):
    """The bands must be the literal rule sentences, the ceiling must reconcile with the
    ~150 adherence line (100 base + 70 = 170 — the trade must be admitted), and the
    cut/merge advice must not contradict update mode's additions-only law."""
    skill = read_file("dist/claude-code/skills/code-of-conduct-generator/SKILL.md")
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
    skill = read_file("dist/claude-code/skills/learnings/SKILL.md")
    assert "keep **20–30** entries" in skill
    assert "**40 is the hard ceiling**" in skill
    low = skill.lower()
    assert "universal" in low and "importan" in low, \
        "eviction must be criterion-driven: keep by universality and importance"


# ── code-of-conduct-generator: v4 lean spine + coverage-map companion ──────────
# The SKILL.md is a lean orchestration spine; detailed scan/output rules live in the
# coverage-map companion, read per-step. Tests read whichever file owns the behavior,
# whitespace-collapsed so a pinned phrase survives line-wrapping.

_COC_MAP = "dist/claude-code/skills/code-of-conduct-generator/coverage-map.md"


def _coc_flat(read_file):
    return " ".join(read_file(_COC_GENERATOR).split())


def _cmap_flat(read_file):
    return " ".join(read_file(_COC_MAP).split())


def test_coc_generator_enters_plan_mode_and_offers_modes(read_file):
    """Plan mode opens before any scan, with a roadmap, and Quick vs Thorough keeps a small repo
    out of the full ceremony."""
    flat = _coc_flat(read_file)
    assert "call `EnterPlanMode` first, before any scanning" in flat
    assert "chat summary of the" in flat
    assert "Quick" in flat and "Thorough" in flat and "low-stakes" in flat


def test_coc_generator_drafts_evidence_first_enforced_only(read_file):
    """Rules come only from scan observations + user answers; the file is enforced-only with no
    aspirational (target) markers."""
    flat = _coc_flat(read_file)
    assert "draft rules only from scan observations and user answers" in flat
    assert "only what is enforced today" in flat
    assert "`(target)`" not in flat, "v4 emits an enforced-only file — no (target) markers"


def test_coc_generator_spine_points_to_companion_sections(read_file):
    """The lean spine delegates detail to the companion's Scan-playbook and Output-format
    sections — keeping SKILL.md's instruction load low."""
    flat = _coc_flat(read_file)
    assert "§ Scan playbook" in flat and "§ Output format" in flat
    assert "coverage-map.md" in flat
    assert "this file is the spine" in flat


def test_coc_generator_find_guard_and_target_resolution(read_file):
    """Case-insensitive detection, multi-match confirm, the behavioural-Covenant guard, and
    target-repo resolution (ask when ambiguous)."""
    flat = _coc_flat(read_file)
    assert "any capitalization" in flat and "case-insensitiv" in flat.lower()
    assert "More than one" in flat and "never silently" in flat
    assert "Contributor Covenant is not an engineering standard" in flat
    assert "hercules-reference § Code-of-conduct resolution" in flat
    assert "which repo the CoC is for" in flat
    assert "one CoC per repo, never merged" in flat


def test_coc_generator_questions_and_quality_bar(read_file):
    """A single batch with a raised floor — the main agent picks the count each run but never fewer
    than 5–8 questions (minimum 5), plus accept/decline per recommended gate and the AI-assisted
    quality bar recommended in chat."""
    flat = _coc_flat(read_file)
    assert "no trickle" in flat and "never asks fewer than 5–8 questions" in flat
    assert "minimum 5" in flat
    assert "accept/decline on each recommended gate" in flat
    assert "branch (not just line) coverage" in flat
    assert "mutation gate\n where a mutation tool exists".replace("\n ", " ") in flat \
        or "mutation gate where a mutation tool exists" in flat


def test_coc_generator_gap_pass_then_critical_review(read_file):
    """Stack-gated gap detector bounded by the directive budget, then a single-challenger critical
    review (full trio opt-in); debate mechanics are referenced, never restated."""
    flat = _coc_flat(read_file)
    assert "stack-gated gap detector" in flat
    assert "never past the directive budget" in flat
    assert "`challenger` critically reviews the draft" in flat
    assert "§ Sub-agent consent" in flat and "hercules-reference § Debate protocol" in flat
    assert "Agent-Injected Core" in flat
    assert "advisors return findings\n only, never write".replace("\n ", " ") in flat \
        or "advisors return findings only, never write" in flat
    raw = read_file(_COC_GENERATOR).lower()
    assert "round 1" not in raw and "cross-examin" not in raw


def test_coc_generator_quick_mode_still_self_scans(read_file):
    """Quick skips the full critical review but still runs a light platitude/no-evidence self-scan, so the
    quality floor is not Thorough-only."""
    flat = _coc_flat(read_file)
    assert "Quick runs a light platitude/no-evidence self-scan" in flat


def test_coc_generator_feedback_is_surgical(read_file):
    """Only genuine decisions surface (ranked by marginal information); feedback is surgical, not a
    silent full regenerate."""
    flat = _coc_flat(read_file)
    assert "genuine decisions" in flat and "marginal information" in flat
    assert "Feedback applies **surgically**" in flat
    assert "regenerate wholesale only when the user reopens the scope" in flat
    # The gate is too important to relocate — its criteria live inline in the spine, non-skippable.
    assert "reads exactly one way" in flat and '"it looks nice" is not proof' in flat
    assert "dry-run each cited check, dropping any that\n fails".replace("\n ", " ") in flat \
        or "dry-run each cited check, dropping any that fails" in flat


def test_coc_generator_commit_stages_before_committing(read_file):
    """The confirmed bug fix: stage then pathspec-commit so an untracked new file commits and the
    user's other staged work is untouched; attribution only in the message; push offer-only."""
    flat = _coc_flat(read_file)
    assert "stage then\n commit".replace("\n ", " ") in flat or "stage then commit" in flat
    assert "`git add -- <paths>` then" in flat
    assert "never reset or swept in" in flat
    assert "Attribution lives in the commit message, never in the file" in flat
    assert "never push automatically" in flat
    assert "/hercules:ship" not in flat


def test_coc_generator_forbids_hercules_internals_bleed(read_file):
    """The file states the target repo's standards only; Hercules process internals never leak."""
    flat = _coc_flat(read_file)
    assert "target repository's" in flat
    assert "Hercules's process internals" in flat and "spec-first flow" in flat


def test_coc_generator_steps_are_in_execution_order(read_file):
    """Structural: the nine numbered steps appear in order — a reshuffled spine fails."""
    skill = read_file(_COC_GENERATOR)
    labels = ["1. **Plan mode", "2. **Find existing", "3. **Scan", "4. **Questions",
              "5. **Draft", "6. **Gap pass", "7. **Gate", "8. **Approve", "9. **Review"]
    positions = [skill.index(s) for s in labels]
    assert positions == sorted(positions), "the nine steps must appear in execution order"


# ── coverage-map companion: the relocated Scan-playbook and Output-format detail ──

def test_coverage_map_scan_playbook_is_bounded_and_evidence_mining(read_file):
    """The relocated scan playbook is bounded (≤5 min), config-first, size-adaptive, mines git
    history, and reconciles config against code."""
    flat = _cmap_flat(read_file)
    assert "§ Scan playbook" in flat
    assert "**5-minute cap**" in flat and "Sizing probe" in flat and "Config first" in flat
    assert "`git log -n 200`" in flat and "branch names and merge shape" in flat and "`git tag`" in flat
    assert "Reconcile config against code" in flat
    assert "becomes a Step-4 question, never an enforced rule" in flat
    assert "proceed sampled and invite the user to point at key modules" in flat


def test_coverage_map_scan_playbook_is_deterministic_and_resumable(read_file):
    """Determinism (canonical sampling, fixed question order) and resumability that does not rely
    on a plan-mode write."""
    flat = _cmap_flat(read_file)
    assert "canonical sorted sampling" in flat
    assert "Plan mode blocks writes" in flat
    assert "~/.hercules/state/{slug}-coc.json" in flat


def test_coverage_map_output_format_leads_with_must_and_inline_checks(read_file):
    """The relocated output rules: lead with a MUST block, inline mechanical check, MUST/SHOULD
    tags, grounded thresholds, evidence-scaled size."""
    flat = _cmap_flat(read_file)
    assert "Lead with `## Non-negotiables (MUST)`" in flat
    assert "naming its **mechanical check** inline" in flat
    assert "tagged **MUST** or **SHOULD**" in flat
    assert "quotes a user answer or a computed repo statistic, never a padded default" in flat
    assert "small, clearly-labelled seed, never padded" in flat


def test_coverage_map_gate_is_strict_and_executed(read_file):
    """The relocated Step-6b gate: four criteria, an objective (not reviewer-judgment) check, an
    auditable citation appendix, and each cited check dry-run against the repo."""
    flat = _cmap_flat(read_file)
    assert "reads exactly one way" in flat and "conflicts with no other" in flat
    assert '"it looks nice"' in flat and "is not proof" in flat
    assert "names an **objective** mechanical check" in flat
    assert "reviewer-judgment-only is rejected" in flat
    assert "auditable\n appendix".replace("\n ", " ") in flat or "auditable appendix" in flat
    assert "dry-run each cited check" in flat


def test_coverage_map_exists_and_is_cited(read_file):
    """The coverage-map ships with the tier legend, stack flags, primary-source anchors, and is
    marked an internal scan aid, not CoC output."""
    cmap = read_file(_COC_MAP)
    assert "not CoC output" in cmap
    assert "P0" in cmap and "P1" in cmap and "[fe]" in cmap and "[be]" in cmap
    for anchor in ("OWASP ASVS", "SLSA", "SemVer", "SRE", "12-Factor", "RFC-2119"):
        assert anchor in cmap, f"coverage-map must cite {anchor}"
    assert "(conv)" in cmap
    for added in ("Coordinated disclosure", "Data classification scheme", "DCO/CLA", "License headers"):
        assert added in cmap, f"coverage-map must carry the {added} point"
