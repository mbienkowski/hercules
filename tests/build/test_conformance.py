"""Ecosystem-conformance hardening — doc-grounded runtime fixes (post-audit).

Two ecosystem-specialist audits (vs current Claude Code + OpenCode docs / v1.18.1 loader source) found
runtime-misfiring content defects. These tests pin each fix so it can't regress.
"""
from pathlib import Path
import re

from scripts.build import targets as target_registry
from scripts.build.cli import build_target


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*") if p.is_file()}


# ── Fix 1: agent-spawn namespace (OpenCode registers under the bare key) ──────
def test_opencode_build_tells_agents_to_spawn_reviewer_by_its_plain_name(tmp_path):
    """When Hercules builds itself for OpenCode, the instructions for spawning the reviewer
    sub-agent must use its plain name rather than a namespaced id -- OpenCode does not recognize
    namespaced spawn ids, so leaving one in place would make spawning that agent silently fail."""
    out = tmp_path / "oc"
    build_target("opencode", out)
    build_md = (out / "commands" / "build.md").read_text(encoding="utf-8")
    assert "Spawn `cynical-reviewer`" in build_md
    assert "hercules:cynical-reviewer" not in build_md, "OpenCode agent id must be bare"


def test_claude_code_build_tells_agents_to_spawn_reviewer_by_its_scoped_name(tmp_path):
    """When Hercules builds itself for Claude Code, the instructions for spawning the reviewer
    sub-agent keep the fully plugin-scoped name, because Claude Code needs that scoping to find
    the right agent among possibly many with similar names."""
    out = tmp_path / "cc"
    build_target("claude-code", out)
    assert "hercules:cynical-reviewer" in (out / "commands" / "build.md").read_text(encoding="utf-8")


# ── Fix 2: operational sections live in an auto-loaded reference skill ─────────
_SECTIONS = ["Artifact root resolution", "Machine-local state", "Agent scaling",
             "Code-of-conduct resolution", "Sub-agent consent", "Debate protocol",
             "Independent review"]


def test_every_target_ships_all_operational_guidance_in_its_reference_skill(tmp_path):
    """For every shipped build (Claude Code, OpenCode, Cursor), every operational section --
    covering things like artifact root resolution, agent scaling, and the debate protocol -- must
    appear in the auto-loaded reference skill. A section left out of this file never reaches the
    running agent, since nothing else loads it automatically."""
    for tgt in ("claude-code", "opencode", "cursor", "grok-build", "gemini-cli", "copilot-cli"):
        out = tmp_path / tgt
        build_target(tgt, out)
        skill = out / "skills" / "hercules-reference" / "SKILL.md"
        assert skill.is_file(), f"{tgt}: hercules-reference skill missing"
        body = skill.read_text(encoding="utf-8")
        for sec in _SECTIONS:
            assert sec in body, f"{tgt}: '{sec}' missing from hercules-reference skill"


def test_operational_guidance_never_cites_a_file_the_agent_never_loads(tmp_path):
    """Built output for any target must never point the user to a section inside a file that is
    never actually loaded -- for example the OpenCode or Cursor build citing the user's own
    AGENTS.md, or the Claude Code build citing the plugin's unread top-level CLAUDE.md. Such a
    citation would send someone hunting for guidance in a place they are told to look but that is
    never read."""
    oc = tmp_path / "oc"; build_target("opencode", oc)
    cc = tmp_path / "cc"; build_target("claude-code", cc)
    cur = tmp_path / "cur"; build_target("cursor", cur)
    # OpenCode & Cursor: AGENTS.md is the *user's* rules file — never a section source we ship.
    for tree in (oc, cur):
        for rel, txt in _files(tree).items():
            assert "AGENTS.md §" not in txt, f"{tree.name} {rel} cites AGENTS.md §"
    # Claude: plugin-root CLAUDE.md is not loaded — sections must not be cited from it.
    for rel, txt in _files(cc).items():
        assert "CLAUDE.md §" not in txt, f"claude {rel} cites CLAUDE.md §"


# ── Fix 3: protocol references resolve / load ─────────────────────────────────
def test_claude_code_protocol_links_resolve_from_the_plugin_root(tmp_path):
    """In the Claude Code build, references to the agent-to-agent communication protocol
    document must be written as a path rooted at the plugin's install location, not as a bare
    filename. A bare reference would break as soon as Claude Code loads the file from a
    different working directory than the plugin's own."""
    out = tmp_path / "cc"
    build_target("claude-code", out)
    joined = "\n".join(_files(out).values())
    assert "${CLAUDE_PLUGIN_ROOT}/protocols/a2a-communication-protocol.md" in joined
    assert "`protocols/a2a-communication-protocol.md`" not in joined, "bare protocol code-span left on Claude"


# ── Fix 4: plan-mode prose is behavioral on OpenCode ──────────────────────────
def test_opencode_build_has_no_leftover_claude_only_wording(tmp_path):
    """The OpenCode build must not contain phrasing borrowed from Claude Code's plan-mode
    workflow, such as the "(auto)" marker, an instruction to "call `plan mode`", or a reference
    to an "approval" tool -- none of those concepts or tools exist in OpenCode, so telling the
    agent to use them would send it looking for something that isn't there."""
    out = tmp_path / "oc"
    build_target("opencode", out)
    joined = "\n".join(_files(out).values())
    assert "(`auto`)" not in joined, "Claude ExitPlanMode '(auto)' leaked into OpenCode"
    # Tighter anchor: the Claude idiom is "call `EnterPlanMode`" / "call `ExitPlanMode`" — a bare
    # "call `plan mode`" (case-insensitive) is a non-existent OpenCode tool call. Match the specific
    # "call" + backticked "plan mode" phrase rather than lowercasing the whole tree, which would
    # also flag innocent prose that happens to contain those two words apart.
    assert not re.search(r"call\s+`plan mode`", joined, re.IGNORECASE), \
        "non-existent OpenCode 'plan mode' tool call"
    assert "`approval`" not in joined, "non-existent OpenCode 'approval' tool"


def test_cursor_build_has_no_leftover_claude_only_wording(tmp_path):
    """The Cursor build, like OpenCode, must not carry Claude's plan-mode idioms — the ``(auto)``
    marker, a "call `plan mode`" tool call, or an "approval" tool — none of which exist in Cursor."""
    out = tmp_path / "cur"
    build_target("cursor", out)
    joined = "\n".join(_files(out).values())
    assert "(`auto`)" not in joined, "Claude ExitPlanMode '(auto)' leaked into Cursor"
    assert not re.search(r"call\s+`plan mode`", joined, re.IGNORECASE), \
        "non-existent Cursor 'plan mode' tool call"
    assert "`approval`" not in joined, "non-existent Cursor 'approval' tool"


def test_cursor_protocol_links_resolve_from_the_plugin_root(tmp_path):
    """The Cursor build must root protocol references at the plugin location (${CURSOR_PLUGIN_ROOT}/),
    mirroring the Claude guard, so the A2A Agent-Injected Core resolves when a subagent is spawned."""
    out = tmp_path / "cur"
    build_target("cursor", out)
    joined = "\n".join(_files(out).values())
    assert "${CURSOR_PLUGIN_ROOT}/protocols/a2a-communication-protocol.md" in joined


def test_claude_code_build_keeps_its_plan_mode_tool_names(tmp_path):
    """The Claude Code build must still reference the real EnterPlanMode and ExitPlanMode
    tools, confirming that cleaning OpenCode-only wording out of the OpenCode build did not
    also strip Claude Code's own working plan-mode instructions."""
    out = tmp_path / "cc"
    build_target("claude-code", out)
    joined = "\n".join(_files(out).values())
    assert "EnterPlanMode" in joined and "ExitPlanMode" in joined


# ── Fix 5: write-gate disclosure lands in a loaded surface ────────────────────
def test_opencode_users_are_warned_about_the_edit_approval_prompt_where_they_will_read_it(tmp_path):
    """The note warning that OpenCode's file-edit approval setting can interrupt Hercules mid-task
    must live in instructions.md, the file OpenCode actually loads on startup -- not tucked away
    somewhere the user would never see it before running into the prompt unprepared."""
    out = tmp_path / "oc"
    build_target("opencode", out)
    instr = (out / "instructions.md").read_text(encoding="utf-8")
    assert 'edit: "ask"' in instr, "write-gate mitigation must be in the loaded instructions.md"


# ── Fix 6: no target renders a plan-mode/CoC triad empty (the ${target:default} guard) ─────────
def test_no_registered_target_renders_a_plan_gate_empty(tmp_path):
    """Every registered target must render the plan-mode instruction in every command. ${target:…}
    switches resolve exact-name → short-alias → default → empty (render.py), so a command whose
    plan-mode switch lost its `default` branch would render to nothing -- shipping a phase with no
    plan-approval discipline. The assertion pins the *switched* sentence "Plan mode — required" (which
    lives ONLY inside the switch block, unlike the static "## Plan mode" heading a global search would
    mask), per command file, parametrized over the live registry so a new ecosystem is auto-covered."""
    for tgt in target_registry.registered_target_names():
        out = tmp_path / tgt
        build_target(tgt, out)
        cmd_files = list((out / "commands").glob("*"))
        assert cmd_files, f"{tgt}: no command files built"
        for cf in cmd_files:
            assert "Plan mode — required" in cf.read_text(encoding="utf-8"), \
                f"{tgt}: {cf.name} plan-mode switch rendered empty"
        assert "${target:" not in "\n".join(_files(out).values()), \
            f"{tgt}: unresolved target switch left in output"
