"""The per-ecosystem build descriptor and its registry.

A ``Target`` binds an ecosystem's name to its source→dest mapping and its non-content "extras"
emitter. ``cli.build_target`` dispatches through these objects, so it holds **zero** per-ecosystem
branches — onboarding an ecosystem is registering one ``Target`` (plus its serializer in
``serialize.py``), never editing the orchestrator.

Destination rules stay data (a ``renames`` dict) unless an ecosystem needs load-bearing logic — Cursor
passes ``dest_fn=serialize.cursor_dest`` so the ``.mdc`` rule extension stays inside the
mutation-covered ``serialize`` module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from scripts.build import emit


@dataclass(frozen=True)
class ExtrasContext:
    """Everything a target's ``emit_extras`` needs, without importing the orchestrator."""

    out_root: Path
    src_target_dir: Path   # src/targets/<name>
    shared_hooks_src: Path  # src/targets/claude-code/hooks — canonical guard, byte-copied everywhere
    src_content: Path      # src/content
    tokens: dict[str, str]
    version: str           # canonical build version (from pyproject) — injected into build-consumed manifests


def _no_extras(ctx: ExtrasContext) -> list[str]:
    return []


def emit_shared(ctx: ExtrasContext, *hook_names: str) -> list[str]:
    """The one shared-extras helper for non-reference ecosystems: byte-copy the named canonical guard
    files (from the shared hooks source) into ``hooks/``, and — if the target ships a
    ``CAPABILITIES.md`` — copy that verbatim too. Both are identical in shape across cursor/opencode, so
    this replaces the copy-map + capabilities boilerplate each used to hand-roll. Returns written rels."""
    written = emit.copy_map(ctx.shared_hooks_src, ctx.out_root, {n: f"hooks/{n}" for n in hook_names})
    cap = ctx.src_target_dir / "CAPABILITIES.md"
    if cap.exists():
        emit.write(ctx.out_root / "CAPABILITIES.md", cap.read_text(encoding="utf-8"))
        written.append("CAPABILITIES.md")
    return written


@dataclass(frozen=True)
class Target:
    """One ecosystem's build strategy: how source paths are relocated, and what extra files it emits."""

    name: str
    renames: dict[str, str] = field(default_factory=dict)
    dest_fn: Callable[[str], str] | None = None
    emit_extras_fn: Callable[[ExtrasContext], list[str]] = _no_extras

    def dest(self, rel: str) -> str:
        """Map a ``src/content`` relative path to this target's destination path."""
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
