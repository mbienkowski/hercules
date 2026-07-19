"""The Cursor target: an official Cursor plugin (``.cursor-plugin/plugin.json`` + native component
dirs). Structure, routing, extensions, YAML-semantic frontmatter, determinism, neutrality, and the
independent-review subagent shape.

Cursor's dominant failure mode is *silent*: a rule with the wrong extension (``.md`` not ``.mdc``),
a string where a bool is expected (``alwaysApply: "false"``), or missing per-type frontmatter loads
as if absent, with **no error**. These tests are the fork-safe structural guard against that — they
assert types (via ``yaml.safe_load``), not strings.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from scripts.build.cli import build_target
from scripts.build.serialize import CursorSerializer

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_CONTENT = REPO_ROOT / "src" / "content"
CLAUDE_ISM = re.compile(r"CLAUDE\.md|E(?:nter|xit)PlanMode|\bClaude\b")


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*") if p.is_file()}


def _frontmatter(text: str) -> dict:
    """Parse a document's YAML frontmatter with a real YAML loader (types preserved)."""
    assert text.startswith("---\n"), "component file must open with a YAML frontmatter fence"
    body = text[len("---\n"):]
    end = body.index("\n---")
    return yaml.safe_load(body[:end]) or {}


def _src_names(subdir: str) -> list[str]:
    return sorted(p.stem for p in (SRC_CONTENT / subdir).glob("*.md"))


def _build(tmp_path: Path) -> Path:
    out = tmp_path / "cursor"
    build_target("cursor", out)
    return out


# ── Determinism ──────────────────────────────────────────────────────────────
def test_building_cursor_twice_produces_identical_output(tmp_path):
    """Two builds from the same source must be byte-for-byte identical, or reproducible releases
    and dist-drift diffing break."""
    a, b = tmp_path / "a", tmp_path / "b"
    build_target("cursor", a)
    build_target("cursor", b)
    assert _files(a) == _files(b)


# ── Routing + exact extensions (the .mdc-vs-.md silent-fail guard) ───────────
def test_persona_ships_as_an_always_applied_rule(tmp_path):
    """The persona must land at rules/hercules-persona.mdc with ``alwaysApply: true`` as a real
    boolean. A .md extension or a string 'true' would make Cursor silently ignore the always-on
    persona."""
    out = _build(tmp_path)
    persona = out / "rules" / "hercules-persona.mdc"
    assert persona.is_file(), "persona must be an .mdc rule under rules/"
    fm = _frontmatter(persona.read_text(encoding="utf-8"))
    assert fm.get("alwaysApply") is True, "alwaysApply must be the boolean True, not a string"
    assert isinstance(fm.get("description"), str) and fm["description"], "rule needs a description"


def test_agents_ship_as_subagents_with_the_official_field_set(tmp_path):
    """Every specialist ships at agents/<name>.md with name+description and NO per-agent model or
    tools (subagents inherit the user's model). The review/audit roles are read-locked."""
    out = _build(tmp_path)
    for name in _src_names("agents"):
        f = out / "agents" / f"{name}.md"
        assert f.is_file(), f"agent {name} must ship at agents/{name}.md"
        fm = _frontmatter(f.read_text(encoding="utf-8"))
        assert fm.get("name") == name and fm.get("description")
        assert "model" not in fm and "model_tier" not in fm and "tools" not in fm, \
            f"{name}: Cursor subagents carry no model tier/tools"
        if name in CursorSerializer.readonly_agents:
            assert fm.get("readonly") is True, f"{name} is a review/audit role — must be readonly"


def test_commands_ship_with_name_and_description_frontmatter(tmp_path):
    """The official plugin validator requires name+description on commands; the raw-overlay
    'frontmatter-free' shape would be rejected. Name is the file stem."""
    out = _build(tmp_path)
    for name in _src_names("commands"):
        f = out / "commands" / f"{name}.md"
        assert f.is_file(), f"command {name} must ship at commands/{name}.md"
        fm = _frontmatter(f.read_text(encoding="utf-8"))
        assert fm.get("name") == name, f"command {name} must carry its stem as name"
        assert fm.get("description"), f"command {name} needs a description"
        assert "disable-model-invocation" not in fm, "Claude's slash marker must be dropped"


def test_no_stray_dot_md_rules_and_no_flat_top_level_dirs(tmp_path):
    """rules/ holds only .mdc (a .md rule is silently ignored by Cursor); there is no top-level
    flat mirror of the components outside the plugin's own component dirs."""
    out = _build(tmp_path)
    for p in (out / "rules").rglob("*"):
        if p.is_file():
            assert p.suffix == ".mdc", f"rules/ must be .mdc only, found {p.name}"
    # The plugin's component dirs are exactly these; nothing leaks elsewhere.
    top = {p.name for p in out.iterdir()}
    assert top <= {".cursor-plugin", "agents", "commands", "rules", "skills", "protocols",
                   "CAPABILITIES.md"}, f"unexpected top-level entries: {top}"


def test_cursor_never_ships_an_agents_md(tmp_path):
    """Cursor natively reads the user's AGENTS.md; shipping our own would clobber it."""
    out = _build(tmp_path)
    assert not (out / "AGENTS.md").exists()


# ── The manifest (single-sourced version) ────────────────────────────────────
def test_plugin_manifest_is_valid_and_version_matches_source(tmp_path):
    """.cursor-plugin/plugin.json must be a byte-copy of the versioned source: kebab name and a
    version identical to the source manifest (single-source-of-truth), so the version can't drift."""
    out = _build(tmp_path)
    manifest = json.loads((out / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?", manifest["name"]), "name must be kebab-case"
    source = json.loads((REPO_ROOT / "src" / "targets" / "cursor" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest == source, "dist manifest must byte-match its versioned source"
    for field in ("rules", "agents", "commands", "skills"):
        assert field in manifest, f"manifest should declare the {field} component path"


# ── Neutrality ───────────────────────────────────────────────────────────────
def test_cursor_output_contains_no_claude_specific_wording(tmp_path):
    """Files shipped to Cursor users must not carry Claude-only names/features, except
    CAPABILITIES.md which legitimately names Claude Code to disclose the cross-ecosystem gaps."""
    out = _build(tmp_path)
    offenders = {}
    for rel, text in _files(out).items():
        if rel == "CAPABILITIES.md":
            continue
        hits = CLAUDE_ISM.findall(text)
        if hits:
            offenders[rel] = sorted(set(hits))
    assert offenders == {}, f"Claude-isms leaked into Cursor: {offenders}"


# ── Positive switch-render: a forgotten ${target:cursor} branch renders empty ─
def test_cursor_switch_branches_render_non_empty(tmp_path):
    """test_target_switches only checks that switch names are spelled right; it cannot catch a
    forgotten cursor branch, which renders empty silently. These assert the load-bearing cursor
    content actually made it into the build."""
    out = _build(tmp_path)
    # Every command's plan-mode instruction is present.
    for name in _src_names("commands"):
        text = (out / "commands" / f"{name}.md").read_text(encoding="utf-8")
        assert "plan mode" in text.lower(), f"{name}: plan-mode branch missing (empty cursor switch?)"
    # The persona's Cursor write-gate note rendered.
    persona = (out / "rules" / "hercules-persona.mdc").read_text(encoding="utf-8")
    assert "ask-before-applying-edits" in persona, "persona cursor write-gate branch missing"
    # The independent-review handshake-or-HALT rendered in both gates.
    for cmd in ("design", "build"):
        text = (out / "commands" / f"{cmd}.md").read_text(encoding="utf-8")
        assert "HALT and tell the user" in text, f"{cmd}: cursor handshake-or-HALT branch missing"


# ── Protocol links resolve to shipped files ──────────────────────────────────
def test_cursor_protocol_citations_resolve_to_shipped_files(tmp_path):
    """Content cites protocol docs via ${plugin_root}protocols/<file>. On Cursor plugin_root is
    ${CURSOR_PLUGIN_ROOT}/, so each citation must point at a protocol file the plugin actually
    ships — otherwise the A2A Agent-Injected Core never reaches a spawned subagent."""
    out = _build(tmp_path)
    cited = set()
    for text in _files(out).values():
        for m in re.finditer(r"protocols/([A-Za-z0-9-]+\.md)", text):
            cited.add(m.group(1))
    assert cited, "expected at least one protocol citation"
    for fname in sorted(cited):
        assert (out / "protocols" / fname).is_file(), \
            f"cited protocols/{fname} is not shipped in the Cursor plugin"
