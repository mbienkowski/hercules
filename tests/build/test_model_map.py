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


def test_a_defined_tier_resolves_to_its_configured_model():
    """When a target has an explicit model configured for a tier, resolving that tier
    returns exactly that model -- the basic case a user relies on when they've set
    up their tiers deliberately."""
    assert resolve(MODELS, "claude-code", "high") == "opus"
    assert resolve(MODELS, "claude-code", "low") == "haiku"


def test_a_tier_explicitly_set_to_none_resolves_to_no_model():
    """When a target's tier is explicitly configured as 'no model', resolving it
    returns nothing rather than some default -- so that tier is left out of the
    generated output instead of picking up an unintended model."""
    assert resolve(MODELS, "opencode", "high") is None
    assert resolve(MODELS, "opencode", "low") is None


def test_medium_and_low_tiers_fall_back_to_the_high_tier_model_when_undefined():
    """If a target only configures a model for its high tier, asking for its medium
    or low tier still works by falling back to that same high-tier model, so a
    partially configured target doesn't break -- it just uses its best available model."""
    # 'partial' only defines high; medium and low fall back to it.
    assert resolve(MODELS, "partial", "medium") == "big"
    assert resolve(MODELS, "partial", "low") == "big"


def test_requesting_an_undefined_tier_name_fails_with_a_clear_error():
    """Asking for a tier that isn't one of the recognized levels raises an error
    instead of silently returning nothing, so a typo or invalid tier in configuration
    is caught right away rather than producing a confusing missing model later."""
    with pytest.raises(ModelMapError):
        resolve(MODELS, "claude-code", "extreme")


def test_requesting_a_model_for_an_unconfigured_target_fails_with_a_clear_error():
    """Asking for a model on a target that isn't listed in the model map raises an
    error instead of returning a default, so a misspelled or unconfigured target name
    is caught immediately instead of silently producing no model."""
    with pytest.raises(ModelMapError):
        resolve(MODELS, "no-such-target", "high")
