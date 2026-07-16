"""Ecosystem-conformance hardening — doc-grounded runtime fixes (post-audit).

Two ecosystem-specialist audits (vs current Claude Code + OpenCode docs / v1.18.1 loader source) found
runtime-misfiring content defects. These tests pin each fix so it can't regress.
"""
from pathlib import Path

from scripts.build.cli import build_target


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*") if p.is_file()}


# ── Fix 1: agent-spawn namespace (OpenCode registers under the bare key) ──────
def test_opencode_agent_spawns_use_bare_ids(tmp_path):
    out = tmp_path / "oc"
    build_target("opencode", out)
    build_md = (out / "commands" / "build.md").read_text(encoding="utf-8")
    assert "Spawn `cynical-reviewer`" in build_md
    assert "hercules:cynical-reviewer" not in build_md, "OpenCode agent id must be bare"


def test_claude_agent_spawns_stay_scoped(tmp_path):
    out = tmp_path / "cc"
    build_target("claude-code", out)
    assert "hercules:cynical-reviewer" in (out / "commands" / "build.md").read_text(encoding="utf-8")


# ── Fix 2: operational sections live in an auto-loaded reference skill ─────────
_SECTIONS = ["Artifact root resolution", "Machine-local state", "Agent scaling",
             "Code-of-conduct resolution", "Sub-agent consent", "Debate protocol"]


def test_reference_skill_carries_the_operational_sections(tmp_path):
    for tgt in ("claude-code", "opencode"):
        out = tmp_path / tgt
        build_target(tgt, out)
        skill = out / "skills" / "hercules-reference" / "SKILL.md"
        assert skill.is_file(), f"{tgt}: hercules-reference skill missing"
        body = skill.read_text(encoding="utf-8")
        for sec in _SECTIONS:
            assert sec in body, f"{tgt}: '{sec}' missing from hercules-reference skill"


def test_no_section_citations_point_at_unloaded_files(tmp_path):
    oc = tmp_path / "oc"; build_target("opencode", oc)
    cc = tmp_path / "cc"; build_target("claude-code", cc)
    # OpenCode: AGENTS.md is the *user's* rules file — never a section source we ship.
    for rel, txt in _files(oc).items():
        assert "AGENTS.md §" not in txt, f"opencode {rel} cites AGENTS.md §"
    # Claude: plugin-root CLAUDE.md is not loaded — sections must not be cited from it.
    for rel, txt in _files(cc).items():
        assert "CLAUDE.md §" not in txt, f"claude {rel} cites CLAUDE.md §"


# ── Fix 3: protocol references resolve / load ─────────────────────────────────
def test_claude_protocol_refs_use_plugin_root(tmp_path):
    out = tmp_path / "cc"
    build_target("claude-code", out)
    joined = "\n".join(_files(out).values())
    assert "${CLAUDE_PLUGIN_ROOT}/protocols/a2a-communication-protocol.md" in joined
    assert "`protocols/a2a-communication-protocol.md`" not in joined, "bare protocol code-span left on Claude"


def test_opencode_injects_protocols_into_context(tmp_path):
    out = tmp_path / "oc"
    build_target("opencode", out)
    js = (out / "plugin.js").read_text(encoding="utf-8")
    # The protocols must be added to cfg.instructions (always-loaded), not merely mentioned in a prompt.
    assert 'path.join(PLUGIN_ROOT, "protocols/a2a-communication-protocol.md")' in js
    assert 'path.join(PLUGIN_ROOT, "protocols/debate-consensus-protocol.md")' in js


# ── Fix 4: plan-mode prose is behavioral on OpenCode ──────────────────────────
def test_opencode_has_no_claude_plan_idioms(tmp_path):
    out = tmp_path / "oc"
    build_target("opencode", out)
    joined = "\n".join(_files(out).values())
    assert "(`auto`)" not in joined, "Claude ExitPlanMode '(auto)' leaked into OpenCode"
    assert "call `plan mode`" not in joined.lower(), "non-existent OpenCode 'plan mode' call"
    assert "`approval`" not in joined, "non-existent OpenCode 'approval' tool"


def test_claude_keeps_plan_mode_tools(tmp_path):
    out = tmp_path / "cc"
    build_target("claude-code", out)
    joined = "\n".join(_files(out).values())
    assert "EnterPlanMode" in joined and "ExitPlanMode" in joined


# ── Fix 5: write-gate disclosure lands in a loaded surface ────────────────────
def test_opencode_writegate_note_is_loaded(tmp_path):
    out = tmp_path / "oc"
    build_target("opencode", out)
    instr = (out / "instructions.md").read_text(encoding="utf-8")
    assert 'edit: "ask"' in instr, "write-gate mitigation must be in the loaded instructions.md"
