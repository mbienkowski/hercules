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
# HAND-AUTHORED literal (never read from the descriptor being verified — the independent pin):
_READONLY_AGENTS = {
    "cynical-reviewer", "security-expert", "source-checker", "senior-qa-engineer", "maintainer",
}

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
