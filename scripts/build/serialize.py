"""The serializer registry — populated from the ecosystem descriptors, zero per-ecosystem classes.

Every registered serializer is the ONE generic :class:`~scripts.build.genserialize.DescriptorSerializer`,
constructed from its ``src/ecosystems/<name>.json``. A bare import of this module yields the fully
populated registry, and a 7th descriptor file appears here automatically — adding an ecosystem is
one new JSON file, never a new serializer class (proven by ``tests/build/test_serialize.py``'s
extensibility contract, which still registers arbitrary third-party serializers by name).
"""
from __future__ import annotations

from typing import Protocol

from scripts.build.descriptor import discover
from scripts.build.genserialize import (  # noqa: F401  (canonical home; re-exported for callers)
    DescriptorSerializer,
    SerializeError,
    require_field,
)


class Serializer(Protocol):
    """Turns a source ``(frontmatter, body)`` into one target's output text."""

    target: str

    def serialize_agent(self, frontmatter: dict[str, str], body: str, tokens: dict[str, str], models: dict) -> str:
        ...

    def serialize_file(self, text: str, tokens: dict[str, str], models: dict, rel: str | None = None) -> str:
        ...


_REGISTRY: dict[str, "Serializer"] = {}


def register(serializer: "Serializer") -> "Serializer":
    """Register *serializer* under its ``.target`` key; return it (usable as a decorator)."""
    _REGISTRY[serializer.target] = serializer
    return serializer


def get(target: str) -> "Serializer":
    """Return the registered serializer for *target*; raise ``KeyError`` if absent."""
    return _REGISTRY[target]


def registered_targets() -> list[str]:
    """Return the sorted list of registered target keys."""
    return sorted(_REGISTRY)


def serialize_file(target: str, text: str, tokens: dict[str, str], models: dict, rel: str | None = None) -> str:
    """Serialize *text* for *target* using its registered serializer."""
    return get(target).serialize_file(text, tokens, models, rel)


# Bootstrap: every ecosystem descriptor registers one generic serializer.
for _descriptor in discover().values():
    register(DescriptorSerializer(_descriptor))
