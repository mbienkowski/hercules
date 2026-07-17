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


def test_each_tier_maps_to_its_configured_alias():
    assert _model_of(serialize_file("claude-code", AGENT.format(tier="high"), {}, MODELS)) == "opus"
    assert _model_of(serialize_file("claude-code", AGENT.format(tier="medium"), {}, MODELS)) == "sonnet"
    assert _model_of(serialize_file("claude-code", AGENT.format(tier="low"), {}, MODELS)) == "haiku"


def test_mapping_is_data_driven_overridable():
    override = {"claude-code": {"high": "sonnet"}}  # a build could remap high→sonnet
    assert _model_of(serialize_file("claude-code", AGENT.format(tier="high"), {}, override)) == "sonnet"


def test_generated_hercules_agent_uses_opus(tmp_path):
    out = tmp_path / "claude-code"
    build_target("claude-code", out)
    assert _model_of((out / "agents" / "hercules.md").read_text(encoding="utf-8")) == "opus"


def test_generated_orchestrator_is_high_tier_advisors_lower(tmp_path):
    out = tmp_path / "claude-code"
    build_target("claude-code", out)
    models = {_model_of((out / "agents" / p.name).read_text(encoding="utf-8"))
              for p in (out / "agents").glob("*.md")}
    assert "opus" in models and ("sonnet" in models or "haiku" in models)
