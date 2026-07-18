"""Spec 02 — per-specialist model matching on Claude Code (data-driven, overridable).

Frozen for spec-02-claude-code-target.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.build.cli import build_target
from scripts.build.serialize import serialize_file

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS = json.loads((REPO_ROOT / "src" / "models.json").read_text(encoding="utf-8"))
AGENT = "---\nname: x\ndescription: d\nmodel_tier: {tier}\ntools: Read\n---\n\n# X\n"


def _model_of(text: str) -> str | None:
    m = re.search(r"^model: (.+)$", text, re.MULTILINE)
    return m.group(1) if m else None


def test_each_priority_tier_selects_its_configured_model():
    """An agent marked high, medium, or low priority is built to run on the exact model configured for
    that tier (opus, sonnet, or haiku respectively) -- so priority settings reliably control which model,
    and therefore what cost and capability, each agent gets."""
    assert _model_of(serialize_file("claude-code", AGENT.format(tier="high"), {}, MODELS)) == "opus"
    assert _model_of(serialize_file("claude-code", AGENT.format(tier="medium"), {}, MODELS)) == "sonnet"
    assert _model_of(serialize_file("claude-code", AGENT.format(tier="low"), {}, MODELS)) == "haiku"


def test_model_choice_per_tier_can_be_overridden_for_a_build():
    """A build can supply its own priority-to-model mapping, for example remapping "high priority" to sonnet
    instead of opus, and that override takes effect -- so teams can adjust cost and quality tradeoffs without
    editing every agent file by hand."""
    override = {"claude-code": {"high": "sonnet"}}  # a build could remap high→sonnet
    assert _model_of(serialize_file("claude-code", AGENT.format(tier="high"), {}, override)) == "sonnet"


def test_the_hercules_orchestrator_agent_is_built_on_the_top_tier_model(tmp_path):
    """When the full toolkit is built, the main Hercules orchestrator agent is generated to run on the most
    capable model (opus) -- ensuring the agent responsible for coordinating all the other agents has the
    strongest reasoning available to it."""
    out = tmp_path / "claude-code"
    build_target("claude-code", out)
    assert _model_of((out / "agents" / "hercules.md").read_text(encoding="utf-8")) == "opus"


def test_a_full_build_produces_agents_on_more_than_one_model_tier(tmp_path):
    """Building the complete toolkit produces a mix of agents: at least one running on the top-tier model
    and at least one other running on a cheaper tier -- confirming that low-priority agents don't get
    silently upgraded to (and billed at) the same expensive tier as the orchestrator."""
    out = tmp_path / "claude-code"
    build_target("claude-code", out)
    models = {_model_of((out / "agents" / p.name).read_text(encoding="utf-8"))
              for p in (out / "agents").glob("*.md")}
    assert "opus" in models and ("sonnet" in models or "haiku" in models)
