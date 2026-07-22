"""The universal conformance suite — every ecosystem, one test body per assertion shape.

Each test parametrizes over the registered targets and asserts against
``CONFORMANCE_EXPECTATIONS`` — a HAND-AUTHORED, fail-closed table of flat literals (the
``GATE_EXPECTATIONS`` house style). The table is never derived from the descriptors: it is the
independent second pin of the cross-file contract, so a wrong descriptor edit fails HERE instead of
updating the expectation in the same keystroke. A registered target with no entry FAILS; an entry
without a target FAILS — a 7th ecosystem cannot ship without declaring its conformance shape.

Tightness rule (CoC): cells are exact strings, full sets, and literal (path, must-contain) pins —
never "at least one of". Behavior that doesn't fit a flat cell is NOT conformance; it stays a named
test in the ecosystem's own file (e.g. Gemini's TOML parse, Cursor's alwaysApply YAML type).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.build.cli import TARGETS, build_target
from scripts.build.version_targets import read_canonical_version

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_CONTENT = REPO_ROOT / "src" / "content"

# Hercules ${...} tokens that must never survive rendering (a leak = a broken page for the user).
_HERCULES_TOKENS = ("${product}", "${host}", "${ns}", "${instructions_file}", "${agent_ns}",
                    "${plan_enter}", "${plan_exit}", "${version}")
# The Claude-only idiom scan for ecosystems that are NOT Claude-shaped.
_CLAUDE_ISM = r"CLAUDE\.md|E(?:nter|xit)PlanMode|\bClaude\b"
# Claude plan-mode idioms that exist on NO other host (Claude-shaped grok included).
_PLAN_IDIOMS = ("(`auto`)", "EnterPlanMode", "ExitPlanMode")

CONFORMANCE_EXPECTATIONS: dict = {
    "claude-code": {
        "command_marker_banned": False,
        "persona_dest": "CLAUDE.md",
        "agent_dest": "agents/{stem}.md",
        "command_dest": "commands/{stem}.md",
        "command_format": "frontmatter",
        "agent_keys_required": ("name", "description", "model"),
        "agent_keys_forbidden": ("model_tier",),
        "orchestrator_prefix": "---\nname: hercules\ndescription: ",
        "neutrality_pattern": None,          # the Claude-shaped reference — no idiom ban
        "neutrality_exempt": (),
        "plan_idioms_banned": False,         # EnterPlanMode/ExitPlanMode are REAL here
        "citation_root": "${CLAUDE_PLUGIN_ROOT}/",
        "top_level": {".claude-plugin", "CLAUDE.md", "agents", "commands", "hooks",
                      "protocols", "settings.json", "skills"},
        "pins": (("agents/hercules.md", "\nmodel: opus\n"),
                 ("hooks/hooks.json", "${CLAUDE_PLUGIN_ROOT}/hooks/frozen_tests.py")),
        "anti_pins": (("agents/hercules.md", "model_tier"),),
    },
    "opencode": {
        "command_marker_banned": True,
        "persona_dest": "instructions.md",
        "agent_dest": "agents/{stem}.md",
        "command_dest": "commands/{stem}.md",
        "command_format": "frontmatter",
        "agent_keys_required": ("name", "description", "mode"),
        "agent_keys_forbidden": ("model", "model_tier", "tools"),
        "orchestrator_prefix": "---\nname: hercules\ndescription: ",
        "neutrality_pattern": _CLAUDE_ISM,
        "neutrality_exempt": ("plugin.js", "CAPABILITIES.md", "hooks/"),
        "plan_idioms_banned": True,
        "citation_root": "",                 # plugin.js injects absolute paths at runtime
        "top_level": {"CAPABILITIES.md", "agents", "commands", "hooks", "instructions.md",
                      "opencode.json", "plugin.js", "protocols", "skills"},
        "pins": (("agents/hercules.md", "\nmode: primary\n"),
                 ("agents/challenger.md", "\nmode: subagent\n"),
                 ("commands/build.md", "\nagent: hercules\n")),
        "anti_pins": (("agents/hercules.md", "\nmodel:"),),
    },
    "cursor": {
        "command_marker_banned": True,
        "persona_dest": "rules/hercules-persona.mdc",
        "agent_dest": "agents/{stem}.md",
        "command_dest": "commands/{stem}.md",
        "command_format": "frontmatter",
        "agent_keys_required": ("name", "description"),
        "agent_keys_forbidden": ("model", "model_tier", "tools"),
        "orchestrator_prefix": "---\nname: hercules\ndescription: ",
        "neutrality_pattern": _CLAUDE_ISM,
        "neutrality_exempt": ("CAPABILITIES.md", "hooks/"),
        "plan_idioms_banned": True,
        "citation_root": "${CURSOR_PLUGIN_ROOT}/",
        "top_level": {".cursor-plugin", "CAPABILITIES.md", "README.md", "agents", "commands",
                      "hooks", "logo.svg", "protocols", "rules", "skills"},
        "pins": (("agents/cynical-reviewer.md", "\nreadonly: true\n"),
                 ("rules/hercules-persona.mdc", "alwaysApply: true"),
                 ("hooks/hooks.json", "${CURSOR_PLUGIN_ROOT}/hooks/hercules_gate.py shell")),
        "anti_pins": (("agents/backend-engineer.md", "readonly"),),
    },
    "grok-build": {
        "command_marker_banned": False,
        "persona_dest": "CLAUDE.md",
        "agent_dest": "agents/{stem}.md",
        "command_dest": "commands/{stem}.md",
        "command_format": "frontmatter",
        "agent_keys_required": ("name", "description"),
        "agent_keys_forbidden": ("model", "model_tier"),
        "orchestrator_prefix": "---\nname: hercules\ndescription: ",
        "neutrality_pattern": None,          # Grok reads the Claude-shaped format on purpose
        "neutrality_exempt": (),
        "plan_idioms_banned": True,
        "citation_root": "${GROK_PLUGIN_ROOT}/",
        "top_level": {".grok-plugin", "CAPABILITIES.md", "CLAUDE.md", "agents", "commands",
                      "hooks", "protocols", "settings.json", "skills"},
        "pins": (("hooks/hooks.json", "${GROK_PLUGIN_ROOT}/hooks/frozen_tests.py"),),
        "anti_pins": (("hooks/hooks.json", "CLAUDE_PLUGIN_ROOT"),
                      ("agents/hercules.md", "\nmodel:")),
    },
    "gemini-cli": {
        "command_marker_banned": True,
        "persona_dest": "GEMINI.md",
        "agent_dest": "agents/{stem}.md",
        "command_dest": "commands/{stem}.toml",
        "command_format": "toml",
        "agent_keys_required": ("name", "description"),
        "agent_keys_forbidden": ("model", "model_tier", "tools"),
        "orchestrator_prefix": "---\nname: hercules\ndescription: ",
        "neutrality_pattern": _CLAUDE_ISM,
        "neutrality_exempt": ("CAPABILITIES.md", "hooks/"),
        "plan_idioms_banned": True,
        "citation_root": "${extensionPath}/",
        "top_level": {"CAPABILITIES.md", "GEMINI.md", "agents", "commands",
                      "gemini-extension.json", "hooks", "protocols", "skills"},
        "pins": (("hooks/hooks.json", "${extensionPath}/hooks/hercules_gate.py"),
                 ("gemini-extension.json", '"contextFileName": "GEMINI.md"'),
                 ("commands/build.toml", "plan mode")),
        "anti_pins": (("agents/hercules.md", "\nmodel:"),),
    },
    "copilot-cli": {
        "command_marker_banned": True,
        "persona_dest": "AGENTS.md",
        "agent_dest": "agents/{stem}.agent.md",
        "command_dest": "commands/{stem}.prompt.md",
        "command_format": "frontmatter",
        "agent_keys_required": ("name", "description"),
        "agent_keys_forbidden": ("model", "model_tier", "tools"),
        "orchestrator_prefix": "---\nname: hercules\ndescription: ",
        "neutrality_pattern": _CLAUDE_ISM,
        "neutrality_exempt": ("CAPABILITIES.md", "hooks/"),
        "plan_idioms_banned": True,
        "citation_root": "${PLUGIN_ROOT}/",
        "top_level": {".github", "AGENTS.md", "CAPABILITIES.md", "agents", "commands",
                      "hooks", "plugin.json", "protocols", "skills"},
        "pins": (("hooks/hooks.json",
                  '"matcher": "create|edit|str_replace_editor|apply_patch|write|Write|Edit|MultiEdit|NotebookEdit"'),
                 ("hooks/hooks.json",
                  'python3 \\"$PLUGIN_ROOT/hooks/hercules_gate.py\\" preToolUse || exit 0'),
                 (".github/plugin/marketplace.json", '"name": "hercules"'),
                 ("commands/build.prompt.md", "plan mode")),
        "anti_pins": (("agents/hercules.agent.md", "\nmodel:"),),
    },
}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Build every registered target once for the whole module (mutation-runner wall-clock)."""
    roots = {}
    for target in TARGETS:
        out = tmp_path_factory.mktemp(target)
        build_target(target, out)
        roots[target] = out
    return roots


def _files(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*") if p.is_file()}


def _frontmatter_keys(text: str) -> list:
    assert text.startswith("---\n"), "expected a frontmatter fence"
    block = text[4:text.index("\n---")]
    return [line.split(":", 1)[0].strip() for line in block.splitlines() if ":" in line]


def _src_stems(subdir: str) -> list:
    return sorted(p.stem for p in (SRC_CONTENT / subdir).glob("*.md"))


def test_every_registered_target_declares_its_conformance_shape():
    """The fail-closed completeness pin: a registered ecosystem with no expectations entry FAILS
    (you cannot ship a target without declaring what conforming output looks like), and a stale
    entry for an unregistered ecosystem FAILS too."""
    assert set(TARGETS) == set(CONFORMANCE_EXPECTATIONS), (
        "CONFORMANCE_EXPECTATIONS must cover exactly the registered targets — add a hand-authored "
        "entry for a new ecosystem (never derive it from the descriptor)")


@pytest.mark.parametrize("target", sorted(CONFORMANCE_EXPECTATIONS))
def test_build_is_deterministic(target, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    build_target(target, a)
    build_target(target, b)
    assert _files(a) == _files(b), f"{target}: two builds from one source must be byte-identical"


@pytest.mark.parametrize("target", sorted(CONFORMANCE_EXPECTATIONS))
def test_every_source_component_lands_at_its_declared_dest(target, built):
    """Inventory: every src/content agent/command lands exactly where the TABLE says (dest format
    strings are independent literals, not descriptor routes), the persona lands at its declared
    dest, and the component dirs carry NOTHING but the declared shape."""
    exp = CONFORMANCE_EXPECTATIONS[target]
    out = built[target]
    assert (out / exp["persona_dest"]).is_file(), f"{target}: persona must ship at {exp['persona_dest']}"
    assert not (out / "persona.md").exists(), f"{target}: raw persona.md must never ship"
    for stem in _src_stems("agents"):
        assert (out / exp["agent_dest"].format(stem=stem)).is_file(), f"{target}: agent {stem} missing"
    for stem in _src_stems("commands"):
        assert (out / exp["command_dest"].format(stem=stem)).is_file(), f"{target}: command {stem} missing"
    for skill in sorted(p.name for p in (SRC_CONTENT / "skills").iterdir() if p.is_dir()):
        assert (out / "skills" / skill / "SKILL.md").is_file(), f"{target}: skill {skill} missing"
    agent_names = {exp["agent_dest"].format(stem=s).rsplit("/", 1)[-1] for s in _src_stems("agents")}
    assert {p.name for p in (out / "agents").iterdir()} == agent_names, \
        f"{target}: agents/ must hold exactly the declared files"
    command_names = {exp["command_dest"].format(stem=s).rsplit("/", 1)[-1] for s in _src_stems("commands")}
    assert {p.name for p in (out / "commands").iterdir()} == command_names, \
        f"{target}: commands/ must hold exactly the declared files"


@pytest.mark.parametrize("target", sorted(CONFORMANCE_EXPECTATIONS))
def test_top_level_tree_is_exactly_the_declared_set(target, built):
    exp = CONFORMANCE_EXPECTATIONS[target]
    got = {p.name for p in built[target].iterdir()}
    assert got == exp["top_level"], f"{target}: unexpected top-level entries {sorted(got ^ exp['top_level'])}"


@pytest.mark.parametrize("target", sorted(CONFORMANCE_EXPECTATIONS))
def test_agents_carry_exactly_the_declared_frontmatter_shape(target, built):
    """Every agent's frontmatter carries the required keys and none of the forbidden ones; the
    orchestrator's exact frontmatter PREFIX is pinned (kills key-order and key-drop mutants)."""
    exp = CONFORMANCE_EXPECTATIONS[target]
    out = built[target]
    for stem in _src_stems("agents"):
        text = (out / exp["agent_dest"].format(stem=stem)).read_text(encoding="utf-8")
        keys = _frontmatter_keys(text)
        for key in exp["agent_keys_required"]:
            assert key in keys, f"{target}: agent {stem} missing required key {key!r}"
        for key in exp["agent_keys_forbidden"]:
            assert key not in keys, f"{target}: agent {stem} carries forbidden key {key!r}"
    herc = (out / exp["agent_dest"].format(stem="hercules")).read_text(encoding="utf-8")
    assert herc.startswith(exp["orchestrator_prefix"]), \
        f"{target}: orchestrator frontmatter must start exactly with {exp['orchestrator_prefix']!r}"


@pytest.mark.parametrize("target", sorted(CONFORMANCE_EXPECTATIONS))
def test_commands_drop_the_claude_marker_and_keep_a_description(target, built):
    """Every shipped command carries a description and — where the table bans it — never
    Claude's ``disable-model-invocation`` marker (Claude-SHAPED ecosystems keep it by design)."""
    exp = CONFORMANCE_EXPECTATIONS[target]
    out = built[target]
    for stem in _src_stems("commands"):
        text = (out / exp["command_dest"].format(stem=stem)).read_text(encoding="utf-8")
        if exp["command_format"] == "frontmatter":
            assert "description" in _frontmatter_keys(text), f"{target}: command {stem} needs a description"
        else:  # toml — the parse itself stays a named test in the ecosystem's own file
            assert re.search(r'^description = ".+"$', text, re.M), f"{target}: {stem} needs a TOML description"
        if exp["command_marker_banned"]:
            assert "disable-model-invocation" not in text, f"{target}: Claude marker leaked into {stem}"


@pytest.mark.parametrize("target", sorted(CONFORMANCE_EXPECTATIONS))
def test_no_hercules_token_or_switch_survives_rendering(target, built):
    for rel, text in _files(built[target]).items():
        assert "${target:" not in text, f"{target}:{rel}: unrendered target switch"
        if rel.startswith("hooks/"):
            continue  # shipped guard code legitimately documents host tokens in comments
        for token in _HERCULES_TOKENS:
            assert token not in text, f"{target}:{rel}: unrendered token {token}"


@pytest.mark.parametrize("target", sorted(CONFORMANCE_EXPECTATIONS))
def test_no_foreign_host_idiom_leaks(target, built):
    """Neutrality: a non-Claude-shaped ecosystem ships no Claude-only wording outside its named
    exemptions, and every non-Claude host bans Claude's plan-mode tool idioms."""
    exp = CONFORMANCE_EXPECTATIONS[target]
    pattern = re.compile(exp["neutrality_pattern"]) if exp["neutrality_pattern"] else None
    for rel, text in _files(built[target]).items():
        exempt = rel in exp["neutrality_exempt"] or any(
            rel.startswith(e) for e in exp["neutrality_exempt"] if e.endswith("/"))
        if pattern and not exempt:
            assert not pattern.search(text), f"{target}:{rel}: foreign host idiom leaked"
        if exp["plan_idioms_banned"] and rel.endswith(".md") and not exempt:
            for idiom in _PLAN_IDIOMS:
                assert idiom not in text, f"{target}:{rel}: Claude plan-mode idiom {idiom!r} leaked"


@pytest.mark.parametrize("target", sorted(CONFORMANCE_EXPECTATIONS))
def test_protocol_citations_resolve_to_shipped_files(target, built):
    """Every ``protocols/<file>`` a shipped page cites must actually ship — a dangling citation is
    a broken instruction at runtime."""
    files = _files(built[target])
    cited = set()
    for text in files.values():
        cited.update(re.findall(r"protocols/([A-Za-z0-9-]+\.md)", text))
    assert cited, f"{target}: expected at least one protocol citation"
    for fname in sorted(cited):
        assert f"protocols/{fname}" in files, f"{target}: cited protocols/{fname} not shipped"


@pytest.mark.parametrize("target", sorted(CONFORMANCE_EXPECTATIONS))
def test_versioned_manifests_carry_the_canonical_version(target, built):
    """Every versioned manifest artifact ships with the canonical (pyproject) version injected and
    no ``${version}`` token anywhere in the tree."""
    from scripts.build.descriptor import discover
    canonical = read_canonical_version(REPO_ROOT)
    out = built[target]
    for artifact in discover()[target].artifacts:
        if artifact.versioned:
            shipped = json.loads((out / artifact.dest).read_text(encoding="utf-8"))
            assert shipped["version"] == canonical, f"{target}: {artifact.dest} version drifted"
    for rel, text in _files(out).items():
        assert "${version}" not in text, f"{target}:{rel}: unresolved version token"


@pytest.mark.parametrize("target", sorted(CONFORMANCE_EXPECTATIONS))
def test_declared_pins_hold_and_anti_pins_stay_absent(target, built):
    """The per-ecosystem literal pins: exact must-contain strings (mode: primary, readonly locks,
    plugin-root-token wiring) and must-NOT-contain strings — the flat-cell home for every
    one-liner the collapsed per-ecosystem files used to assert."""
    exp = CONFORMANCE_EXPECTATIONS[target]
    out = built[target]
    for rel, needle in exp["pins"]:
        text = (out / rel).read_text(encoding="utf-8")
        assert needle in text, f"{target}:{rel}: expected pin {needle!r}"
    for rel, needle in exp["anti_pins"]:
        text = (out / rel).read_text(encoding="utf-8")
        assert needle not in text, f"{target}:{rel}: forbidden content {needle!r} present"


@pytest.mark.parametrize("target", sorted(CONFORMANCE_EXPECTATIONS))
def test_shipped_guard_modules_are_byte_identical_to_the_shared_source(target, built):
    """Every guard module an ecosystem ships must be the EXACT bytes of the one shared source in
    src/hooks/ — the write-gate logic can never diverge across ecosystems."""
    from scripts.build.descriptor import discover
    shared = REPO_ROOT / "src" / "hooks"
    guard = discover()[target].guard
    assert guard, f"{target}: every ecosystem ships the canonical guard"
    for name in guard:
        assert (built[target] / "hooks" / name).read_bytes() == (shared / name).read_bytes(), \
            f"{target}: hooks/{name} diverged from the shared source"


@pytest.mark.parametrize("target", sorted(CONFORMANCE_EXPECTATIONS))
def test_shipped_gate_config_is_the_descriptor_gate_verbatim(target, built):
    """Where a descriptor wires the generic adapter, the shipped hooks/gate.json must be exactly
    the descriptor's gate object — that data IS the enforcement wiring; drift is a broken gate."""
    from scripts.build.descriptor import discover
    gate = discover()[target].gate
    shipped_path = built[target] / "hooks" / "gate.json"
    if gate is None:
        assert not shipped_path.exists(), f"{target}: gate.json shipped without a descriptor gate"
        return
    assert json.loads(shipped_path.read_text(encoding="utf-8")) == gate
