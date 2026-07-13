"""Spec 03 — the OpenCode target: structure, determinism, neutrality, model contrast.

Frozen for spec-03-opencode-target.
"""
import re
from pathlib import Path

from scripts.build.cli import build_target

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_ISM = re.compile(r"CLAUDE\.md|E(?:nter|xit)PlanMode|/hercules:[a-z]|\bClaude\b")


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*") if p.is_file()}


def test_opencode_structure(tmp_path):
    out = tmp_path / "opencode"
    build_target("opencode", out)
    assert len(list((out / "agents").glob("*.md"))) == 16
    assert len(list((out / "commands").glob("*.md"))) == 5
    for f in ("plugin.js", "opencode.json", "instructions.md", "CAPABILITIES.md"):
        assert (out / f).is_file(), f"missing {f}"


def test_build_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    build_target("opencode", a)
    build_target("opencode", b)
    assert _files(a) == _files(b)


def test_no_claude_ism_leaks_into_opencode_content(tmp_path):
    out = tmp_path / "opencode"
    build_target("opencode", out)
    offenders = {}
    for rel, text in _files(out).items():
        # plugin.js inlines the (already-checked) content; CAPABILITIES.md legitimately *names*
        # Claude Code to disclose the cross-ecosystem capability difference.
        if rel in ("plugin.js", "CAPABILITIES.md"):
            continue
        hits = CLAUDE_ISM.findall(text)
        if hits:
            offenders[rel] = sorted(set(hits))
    assert offenders == {}, f"Claude-isms leaked into OpenCode: {offenders}"


def test_hercules_is_primary_advisors_are_subagents(tmp_path):
    out = tmp_path / "opencode"
    build_target("opencode", out)
    herc = (out / "agents" / "hercules.md").read_text(encoding="utf-8")
    assert herc.startswith("---\nname: hercules\ndescription: ")  # exact frontmatter keys/order
    mode = lambda p: re.search(r"^mode: (\S+)$", (out / "agents" / p).read_text(encoding="utf-8"), re.M).group(1)
    assert mode("hercules.md") == "primary"
    assert mode("challenger.md") == "subagent"


def test_opencode_agents_omit_model_while_claude_carry_it(tmp_path):
    oc, cc = tmp_path / "oc", tmp_path / "cc"
    build_target("opencode", oc)
    build_target("claude-code", cc)
    assert all("\nmodel:" not in p.read_text(encoding="utf-8") for p in (oc / "agents").glob("*.md"))
    assert all("\nmodel:" in p.read_text(encoding="utf-8") for p in (cc / "agents").glob("*.md"))


def test_capabilities_discloses_the_two_gaps(tmp_path):
    out = tmp_path / "opencode"
    build_target("opencode", out)
    caps = (out / "CAPABILITIES.md").read_text(encoding="utf-8").lower()
    assert "write-gate" in caps and "model" in caps
