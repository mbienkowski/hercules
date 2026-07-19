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


def test_shipped_skill_directories_match_the_documented_list(repo_root):
    """The skills listed as available to users must exactly match the skill folders actually
    shipped in the plugin. If they drift, users get pointed at a skill that doesn't exist, or a
    shipped skill goes undocumented and invisible."""
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
def test_every_skill_explains_when_to_use_it_and_active_ones_declare_a_stop_condition(path):
    """Each skill file must state, in its own description, when a user should reach for it, and
    skills that actively drive a workflow must also declare a hard-stop condition. Without this,
    a skill could fire at the wrong moment or run past a point where it should have halted for
    missing information."""
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


def test_skills_stay_usable_with_any_tech_stack(repo_root, skill_files):
    """None of the shipped skills may hard-code the name of a specific framework or library
    (for example React, Django, or Spring). Doing so would make the skill's advice wrong or
    irrelevant for a project built on a different stack."""
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
def test_documentation_always_shows_the_working_form_of_a_hercules_command(path):
    """Every command, skill, and agent doc must show hercules subcommands with the '--' prefix
    (e.g. 'hercules --origin-trace'), never the bare form. The bare form is silently forwarded to
    the underlying assistant as a plain prompt instead of running the command, so a doc using it
    would teach users a command that doesn't actually work."""
    hit = _BARE_SUBCOMMAND_RE.search(path.read_text())
    assert hit is None, \
        f"{path.name} uses the bare subcommand form {hit.group()!r} — write 'hercules --<name>'"





def test_the_advertised_skill_list_matches_the_installed_plugin_configuration(repo_root):
    """The skill names declared in the plugin's settings file must be exactly the same set as the
    canonical skill list maintained in code. If they fall out of sync, a skill could be installed
    but undocumented, or documented but never actually enabled for users."""
    settings = json.loads((repo_root / "dist" / "claude-code" / "settings.json").read_text())
    manifest = settings.get("skills", [])
    assert sorted(manifest) == sorted(_SKILL_LIST), (
        "dist/claude-code/settings.json skills[] and _SKILL_LIST are out of sync.\n"
        f"  In settings.json only: {sorted(set(manifest) - set(_SKILL_LIST))}\n"
        f"  In _SKILL_LIST only: {sorted(set(_SKILL_LIST) - set(manifest))}"
    )


_COC_GENERATOR = "dist/claude-code/skills/code-of-conduct-generator/SKILL.md"


def test_code_of_conduct_generator_lets_the_user_review_the_draft_before_writing_it(repo_root):
    """Generating a code of conduct must open plan mode first and only write the file after the
    user explicitly approves the plan, so the user always sees and can correct the full draft
    before it becomes a real file in their repo."""
    md = (repo_root / _COC_GENERATOR).read_text()
    assert "EnterPlanMode" in md, \
        "code-of-conduct-generator must call EnterPlanMode to present the CoC draft for review"
    assert "ExitPlanMode" in md, \
        "code-of-conduct-generator must call ExitPlanMode after the user approves"


def test_looking_up_the_project_code_of_conduct_works_regardless_of_filename_case(skill_files):
    """A skill that checks for an existing code-of-conduct file must recognize it whatever case
    the filename uses. An instruction pinned to the lowercase name alone would miss
    CODE_OF_CONDUCT.md, a common uppercase convention on the same filesystem, and wrongly
    conclude no code of conduct exists."""
    forbidden = ("`code-of-conduct.md` if present", "Read `code-of-conduct.md`", "read `code-of-conduct.md`")
    for path in skill_files:
        text = path.read_text()
        for pat in forbidden:
            assert pat not in text, \
                f"{path.parent.name}/SKILL.md: '{pat}' is a fixed-lowercase CoC read — use 'any capitalization'"


def test_a_new_code_of_conduct_is_created_with_a_lowercase_filename_unless_asked_otherwise(read_file):
    """When no code-of-conduct file exists yet, the generator must default to creating the
    lowercase `code-of-conduct.md` rather than proposing the uppercase `CODE_OF_CONDUCT.md`
    (GitHub's community-doc convention). Proposing uppercase unprompted risks ending up with two
    conflicting files if a lowercase one is added later."""
    skill = read_file("dist/claude-code/skills/code-of-conduct-generator/SKILL.md")
    assert "→ `CODE_OF_CONDUCT.md`" not in skill, \
        "generator must not PROPOSE an uppercase output filename by default"
    assert "`code-of-conduct.md`" in skill, \
        "the default create name must be the lowercase code-of-conduct.md"


def test_the_learnings_skill_only_promises_to_run_at_a_phase_that_actually_calls_it(read_file):
    """If the learnings skill tells the model it fires at 'ship time', the ship phase's own
    instructions must actually invoke it. Otherwise a user is told their learnings get captured
    at ship time, but the ship command runs without ever writing them."""
    skill = read_file("dist/claude-code/skills/learnings/SKILL.md")
    if "ship time" in skill.lower():
        assert "learnings" in read_file("dist/claude-code/commands/ship.md"), \
            "learnings anchors to 'ship time' but only Build invokes it — rephrase the trigger"


# ── code-of-conduct-generator: v4 lean spine + coverage-map companion ──────────
# The SKILL.md is a lean orchestration spine; detailed scan/output rules live in the
# coverage-map companion, read per-step. Tests read whichever file owns the behavior,
# whitespace-collapsed so a pinned phrase survives line-wrapping.

_COC_MAP = "dist/claude-code/skills/code-of-conduct-generator/coverage-map.md"


def _coc_flat(read_file):
    return " ".join(read_file(_COC_GENERATOR).split())


def _cmap_flat(read_file):
    return " ".join(read_file(_COC_MAP).split())


def test_coc_generator_offers_a_quick_option_before_committing_to_a_full_scan(read_file):
    """The generator must enter plan mode before scanning anything, present the user a roadmap,
    and offer a Quick versus Thorough choice, so a small, low-stakes repo isn't forced through
    the full scan ceremony when a lighter pass would do."""
    flat = _coc_flat(read_file)
    assert "call `EnterPlanMode` first, before any scanning" in flat
    assert "chat summary of the" in flat
    assert "Quick" in flat and "Thorough" in flat and "low-stakes" in flat


def test_the_generators_main_instructions_defer_details_to_its_companion_reference_doc(read_file):
    """The generator's main instructions stay short by pointing readers to the detailed scan and
    output-format guidance in its companion reference file rather than repeating it inline,
    keeping the primary instructions easy to follow while the fine detail stays available on
    demand."""
    flat = _coc_flat(read_file)
    assert "§ Scan playbook" in flat and "§ Output format" in flat
    assert "coverage-map.md" in flat
    assert "this file is the spine" in flat


def test_coc_generator_confirms_which_repo_and_file_before_writing_anything(read_file):
    """Before generating anything, the skill must detect any existing code-of-conduct file
    regardless of capitalization, ask the user when more than one match is found, refuse to treat
    a generic template as an already-adequate standard, and confirm which repo the document is
    for when that's ambiguous, so it never ends up creating two conflicting code-of-conduct files
    in the same repo."""
    flat = _coc_flat(read_file)
    assert "any capitalization" in flat and "case-insensitiv" in flat.lower()
    assert "More than one" in flat and "never silently" in flat
    assert "Contributor Covenant is not an engineering standard" in flat
    assert "hercules-reference § Code-of-conduct resolution" in flat
    assert "which repo the CoC is for" in flat
    assert "one CoC per repo, never merged" in flat


def test_coc_generator_asks_a_substantial_batch_of_questions_and_holds_a_quality_bar(read_file):
    """The generator must ask its clarifying questions in one batch of at least five to eight,
    never trickling them in one at a time, let the user accept or decline each recommended rule,
    and recommend a real quality bar (branch coverage, mutation testing where available) rather
    than a token one."""
    flat = _coc_flat(read_file)
    assert "no trickle" in flat and "never asks fewer than 5–8 questions" in flat
    assert "minimum 5" in flat
    assert "accept/decline on each recommended gate" in flat
    assert "branch (not just line) coverage" in flat
    assert "mutation gate\n where a mutation tool exists".replace("\n ", " ") in flat \
        or "mutation gate where a mutation tool exists" in flat


def test_coc_generator_walks_through_its_nine_steps_in_the_documented_order(read_file):
    """The generator's nine numbered steps (plan mode, find existing, scan, questions, draft, gap
    pass, gate, approve, review) must appear in the file in that same order. A reshuffled step
    list would mislead anyone following the workflow, even though nothing enforces the order at
    runtime."""
    skill = read_file(_COC_GENERATOR)
    labels = ["1. **Plan mode", "2. **Find existing", "3. **Scan", "4. **Questions",
              "5. **Draft", "6. **Gap pass", "7. **Gate", "8. **Approve", "9. **Review"]
    positions = [skill.index(s) for s in labels]
    assert positions == sorted(positions), "the nine steps must appear in execution order"


# ── coverage-map companion: the relocated Scan-playbook and Output-format detail ──

def test_the_coverage_gate_requires_objective_checks_not_just_reviewer_opinion(read_file):
    """The quality gate documented in the coverage-map companion must require each rule to read
    one way, not conflict with any other rule, name a mechanical check that isn't just "it looks
    nice", and be dry-run against the real repo with results kept in an auditable record, so a
    rule can't pass the gate on a reviewer's say-so alone."""
    flat = _cmap_flat(read_file)
    assert "reads exactly one way" in flat and "conflicts with no other" in flat
    assert '"it looks nice"' in flat and "is not proof" in flat
    assert "names an **objective** mechanical check" in flat
    assert "reviewer-judgment-only is rejected" in flat
    assert "auditable\n appendix".replace("\n ", " ") in flat or "auditable appendix" in flat
    assert "dry-run each cited check" in flat

def test_the_coverage_map_warns_about_broad_wildcard_architecture_rule_patterns(read_file):
    """The coverage-map must warn that broad wildcard package patterns in architecture/dependency
    rules catch infrastructure packages (config, admin, frontend, commons) that legitimately depend
    on each other — a footgun that produces 100+ false cycles on a Spring Boot monorepo. The
    coverage-map's Testing section must name this and recommend narrow patterns or subpackage
    exclusions."""
    flat = _cmap_flat(read_file)
    assert "broad wildcard" in flat, \
        "coverage-map must warn about broad wildcard package patterns in architecture rules"
    assert "infrastructure" in flat, \
        "coverage-map must name infrastructure packages as the false-positive source"
    assert "narrow" in flat, \
        "coverage-map must recommend narrow patterns as the fix"


def test_write_test_scenarios_captures_actual_counts_before_freezing(read_file):
    """The write-test-scenarios skill must capture actual observable quantities (violation counts,
    error counts, list lengths, status codes) by running the relevant tool before freezing —
    never guess an expected count and iterate. Guessing leads to 3–4 full edit-test cycles just
    to converge on the right number; capturing it once eliminates that churn."""
    skill = read_file("dist/claude-code/skills/write-test-scenarios/SKILL.md")
    lower = skill.lower()
    assert "capture" in lower and "actual" in lower, \
        "write-test-scenarios must instruct capturing actual counts before freezing"
    assert "never guess" in lower, \
        "write-test-scenarios must explicitly forbid guessing expected counts"
