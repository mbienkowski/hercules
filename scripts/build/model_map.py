"""Tier → per-target model resolution (pure).

``models.json`` maps ``model_tier`` (``high|medium|low``) to a per-target value. A missing tier falls
back toward higher capability (``low`` → ``medium`` → ``high``). A ``null`` value is first-class and
means **omit the field**.
"""
from __future__ import annotations

TIER_FALLBACK = ("high", "medium", "low")


class ModelMapError(ValueError):
    """Raised on an unknown tier or an unconfigured target."""


def resolve(models: dict, target: str, tier: str) -> str | None:
    """Return the model id for *target*/*tier*, falling back toward higher tiers when unset.

    Returns ``None`` when the resolved value is ``null`` (field omitted) or no tier is configured.
    Raises :class:`ModelMapError` on an unknown *tier* or a *target* absent from *models*.
    """
    if tier not in TIER_FALLBACK:
        raise ModelMapError(f"unknown tier: {tier!r}")  # pragma: no mutate
    if target not in models:
        raise ModelMapError(f"target not configured in models.json: {target!r}")  # pragma: no mutate
    tmap = models[target]
    idx = TIER_FALLBACK.index(tier)
    order = [tier, *reversed(TIER_FALLBACK[:idx])]  # requested tier, then higher tiers
    for candidate in order:
        if candidate in tmap:
            return tmap[candidate]
    return None
