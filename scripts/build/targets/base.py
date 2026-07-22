"""The build's ``Target`` binding and its registry.

A ``Target`` binds an ecosystem's name to its source→dest mapping and its non-content "extras"
emitter. ``cli.build_target`` dispatches through these objects, so it holds **zero** per-ecosystem
branches. Both callables are wired from the ecosystem's descriptor (see ``targets/__init__``):
``dest_fn`` is the generic route interpreter and ``emit_extras_fn`` the generic extras emitter,
partially applied with the descriptor — onboarding an ecosystem is one new JSON file, never code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class ExtrasContext:
    """Everything a target's ``emit_extras`` needs, without importing the orchestrator."""

    out_root: Path
    src_target_dir: Path   # src/targets/<name> (legacy asset root, retired with the tree)
    shared_hooks_src: Path  # src/hooks — canonical guard + generic gate adapter, byte-copied everywhere
    src_content: Path      # src/content
    tokens: dict[str, str]
    version: str           # canonical build version (from pyproject) — injected into build-consumed manifests


def _no_extras(ctx: ExtrasContext) -> list[str]:
    return []


@dataclass(frozen=True)
class Target:
    """One ecosystem's build strategy: how source paths are relocated, and what extra files it emits."""

    name: str
    renames: dict[str, str] = field(default_factory=dict)
    dest_fn: Callable[[str], "str | None"] | None = None
    emit_extras_fn: Callable[[ExtrasContext], list[str]] = _no_extras

    def dest(self, rel: str) -> "str | None":
        """Map a ``src/content`` relative path to this target's destination path — ``None`` means
        the source ships nothing on this target (an ``omit`` route)."""
        if self.dest_fn is not None:
            return self.dest_fn(rel)
        return self.renames.get(rel, rel)

    def emit_extras(self, ctx: ExtrasContext) -> list[str]:
        """Emit the target's non-content artifacts (manifests, hooks, capability docs); return rels."""
        return self.emit_extras_fn(ctx)


_REGISTRY: dict[str, Target] = {}


def register(target: Target) -> Target:
    """Register *target* under its name (called at import by each ecosystem module)."""
    _REGISTRY[target.name] = target
    return target


def get(name: str) -> Target:
    """The build descriptor for *name*, or a default (identity dest, no extras) if unregistered.

    The default preserves the pre-registry contract exactly: a target with a serializer but no
    descriptor renders content only (the old ``if/elif`` extras tail simply didn't match it). Real
    ecosystems register an explicit ``Target``; ``test_enforcement_gates`` still fails any registered
    ecosystem that ships without a write-gate, so "content only" can't hide a missing safety gate.
    """
    return _REGISTRY.get(name) or Target(name=name)


def registered_target_names() -> list[str]:
    """The one authoritative ecosystem list — feeds the CLI target set and the CI smoke matrix."""
    return sorted(_REGISTRY)
