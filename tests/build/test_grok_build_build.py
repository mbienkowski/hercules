"""Grok Build target build: Claude-shaped tree, Grok-rooted hooks, model-choice-open, deterministic."""
from __future__ import annotations

import json

from scripts.build.cli import build_target


def _build(tmp_path):
    out = tmp_path / "grok"
    build_target("grok-build", out)
    return out


def _tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_build_is_deterministic(tmp_path):
    a = tmp_path / "a"; build_target("grok-build", a)
    b = tmp_path / "b"; build_target("grok-build", b)
    assert _tree(a) == _tree(b)


def test_persona_ships_as_claude_md_not_persona(tmp_path):
    out = _build(tmp_path)
    assert (out / "CLAUDE.md").is_file()
    assert not (out / "persona.md").exists()


def test_agents_pin_no_model_so_the_user_model_drives_every_agent(tmp_path):
    out = _build(tmp_path)
    for p in (out / "agents").glob("*.md"):
        assert "\nmodel:" not in p.read_text(encoding="utf-8"), f"{p.name} must not pin a model"


def test_hooks_are_rooted_at_grok_plugin_root_not_claude(tmp_path):
    out = _build(tmp_path)
    hj = (out / "hooks" / "hooks.json").read_text(encoding="utf-8")
    assert "${GROK_PLUGIN_ROOT}/hooks/frozen_tests.py" in hj
    assert "CLAUDE_PLUGIN_ROOT" not in hj


def test_marketplace_manifest_is_version_injected(tmp_path):
    out = _build(tmp_path)
    pj = json.loads((out / ".grok-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert pj["version"] and "${version}" not in pj["version"]


def test_no_leftover_claude_only_plan_mode_idioms(tmp_path):
    """Grok takes the generic ${target:default} plan-mode wording — never Claude's EnterPlanMode /
    ExitPlanMode / (auto) idioms, which name tools that do not exist on Grok Build."""
    out = _build(tmp_path)
    joined = "\n".join(p.read_text(encoding="utf-8") for p in out.rglob("*.md") if p.is_file())
    assert "(`auto`)" not in joined
    assert "EnterPlanMode" not in joined and "ExitPlanMode" not in joined
