"""Spec 03 — the OpenCode target: structure, determinism, neutrality, model contrast.

Frozen for spec-03-opencode-target.
"""
import re
from pathlib import Path

from scripts.build.cli import build_target

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_ISM = re.compile(r"CLAUDE\.md|E(?:nter|xit)PlanMode|\bClaude\b")


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*") if p.is_file()}


def test_building_opencode_twice_produces_identical_output(tmp_path):
    """Building the OpenCode target from the same source twice in a row must produce
    byte-for-byte identical files. If the build were non-deterministic, two builds from the
    same commit could differ, breaking reproducible releases and confusing anyone diffing
    builds."""
    a, b = tmp_path / "a", tmp_path / "b"
    build_target("opencode", a)
    build_target("opencode", b)
    assert _files(a) == _files(b)


def test_opencode_output_contains_no_claude_specific_wording(tmp_path):
    """OpenCode is a separate ecosystem from Claude Code, so the files it ships to users must
    not mention Claude-specific names, files, or features (like CLAUDE.md or plan mode) except
    where a file is explicitly documenting the difference between the two products. Leaking
    such references would confuse OpenCode users with instructions that don't apply to them."""
    out = tmp_path / "opencode"
    build_target("opencode", out)
    offenders = {}
    for rel, text in _files(out).items():
        # plugin.js inlines the (already-checked) content; CAPABILITIES.md legitimately *names*
        # Claude Code to disclose the cross-ecosystem gap; hooks/ ships the CANONICAL shared guard
        # (byte-identical to Claude's), whose docstrings describe the cross-ecosystem write-gate.
        if rel in ("plugin.js", "CAPABILITIES.md") or rel.startswith("hooks/"):
            continue
        hits = CLAUDE_ISM.findall(text)
        if hits:
            offenders[rel] = sorted(set(hits))
    assert offenders == {}, f"Claude-isms leaked into OpenCode: {offenders}"


def test_hercules_is_the_main_agent_while_its_advisors_stay_subagents(tmp_path):
    """In the OpenCode build, the main Hercules agent must be registered as the primary agent
    a user talks to directly, while helper agents such as the challenger are registered as
    subagents. Getting this backwards would let an internal advisor agent surface as the main
    conversation partner, or hide Hercules itself behind a helper role."""
    out = tmp_path / "opencode"
    build_target("opencode", out)
    herc = (out / "agents" / "hercules.md").read_text(encoding="utf-8")
    assert herc.startswith("---\nname: hercules\ndescription: ")  # exact frontmatter keys/order
    mode = lambda p: re.search(r"^mode: (\S+)$", (out / "agents" / p).read_text(encoding="utf-8"), re.M).group(1)
    assert mode("hercules.md") == "primary"
    assert mode("challenger.md") == "subagent"


def test_opencode_agents_leave_model_choice_open_while_claude_code_pins_it(tmp_path):
    """OpenCode agent files must not hard-code which AI model to use, since OpenCode users
    pick their own model, whereas Claude Code agent files must specify a model, since that
    ecosystem expects it. Getting this swapped would either force an unwanted model on
    OpenCode users or leave Claude Code agents without one."""
    oc, cc = tmp_path / "oc", tmp_path / "cc"
    build_target("opencode", oc)
    build_target("claude-code", cc)
    assert all("\nmodel:" not in p.read_text(encoding="utf-8") for p in (oc / "agents").glob("*.md"))
    assert all("\nmodel:" in p.read_text(encoding="utf-8") for p in (cc / "agents").glob("*.md"))
