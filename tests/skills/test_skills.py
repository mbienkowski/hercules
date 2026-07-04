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
        "never suggest a mutation gate for a repo with no mutation tooling"


def test_learnings_store_has_an_entry_budget_and_eviction_criterion(read_file):
    """Discover reads the whole store, so it is instruction load like the CoC: the cap
    must be the literal rule sentence and eviction criterion-driven."""
    skill = read_file("plugin/skills/learnings/SKILL.md")
    assert "keep **20–30** entries" in skill
    assert "**40 is the hard ceiling**" in skill
    low = skill.lower()
    assert "universal" in low and "importan" in low, \
        "eviction must be criterion-driven: keep by universality and importance"

