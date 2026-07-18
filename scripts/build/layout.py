"""Source discovery for the build (thin filesystem boundary).

Enumerates the ``*.md`` sources under ``src/content`` in a stable order for the serializers to
consume. ``cli.build_target`` maps each source to its per-target destination.
"""
from __future__ import annotations

from pathlib import Path


def discover_sources(content_root: Path) -> list[Path]:
    """Return every ``*.md`` source under ``src/content`` in a stable (sorted) order."""
    if not content_root.exists():
        return []
    return sorted(content_root.rglob("*.md"))
