"""Output planning + the filesystem boundary (thin; round-trip tested in Spec 02, not mutation-critical).

Maps parsed source artifacts to their per-target destination paths. Spec 01 lands the discovery +
1:1 planning skeleton (exercised on the empty ``src/content`` scaffold); per-category paths, the
``[filter]``, and ``overrides/`` land with Spec 02's dist generation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutputUnit:
    """One planned output file: its source path(s), destination, and the serializer target."""

    dest: str
    target: str
    sources: tuple[str, ...]


def discover_sources(content_root: Path) -> list[Path]:
    """Return every ``*.md`` source under ``src/content`` in a stable (sorted) order."""
    if not content_root.exists():
        return []
    return sorted(content_root.rglob("*.md"))


def plan_outputs(content_root: Path, target: str) -> list[OutputUnit]:
    """Plan the output units for *target* (1:1 mapping under ``dist/<target>/`` for Spec 01)."""
    units: list[OutputUnit] = []
    for src in discover_sources(content_root):
        rel = src.relative_to(content_root).as_posix()
        units.append(OutputUnit(dest=rel, target=target, sources=(str(src),)))
    return units
