"""Spec 01 — tier→model resolution with fallback and null=omit.

Frozen for spec-01-build-compiler-core.
"""
import pytest

from scripts.build.model_map import ModelMapError, resolve

MODELS = {
    "claude-code": {"high": "opus", "medium": "sonnet", "low": "haiku"},
    "opencode": {"high": None, "medium": None, "low": None},
    "partial": {"high": "big"},  # medium/low fall back to high
}


def test_direct_tier_lookup():
    assert resolve(MODELS, "claude-code", "high") == "opus"
    assert resolve(MODELS, "claude-code", "low") == "haiku"


def test_null_value_means_omit():
    assert resolve(MODELS, "opencode", "high") is None
    assert resolve(MODELS, "opencode", "low") is None


def test_fallback_high_medium_low():
    # 'partial' only defines high; medium and low fall back to it.
    assert resolve(MODELS, "partial", "medium") == "big"
    assert resolve(MODELS, "partial", "low") == "big"


def test_unknown_tier_raises():
    with pytest.raises(ModelMapError):
        resolve(MODELS, "claude-code", "extreme")


def test_unknown_target_raises():
    with pytest.raises(ModelMapError):
        resolve(MODELS, "no-such-target", "high")
