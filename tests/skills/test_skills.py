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


def test_coc_generator_steps_are_in_execution_order(read_file):
    """Structural: the nine numbered steps appear in order — a reshuffled spine fails."""
    skill = read_file(_COC_GENERATOR)
    labels = ["1. **Plan mode", "2. **Find existing", "3. **Scan", "4. **Questions",
              "5. **Draft", "6. **Gap pass", "7. **Gate", "8. **Approve", "9. **Review"]
    positions = [skill.index(s) for s in labels]
    assert positions == sorted(positions), "the nine steps must appear in execution order"


# ── coverage-map companion: the relocated Scan-playbook and Output-format detail ──

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
