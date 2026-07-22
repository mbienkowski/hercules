"""Gemini CLI target: the version-injected ``gemini-extension.json`` manifest, a ``GEMINI.md`` context
file (from the persona, via ``dest_fn``), TOML commands / subagents (via the serializer), and the
``BeforeTool`` write-gate adapter.

Capability prose lives in ``src/targets/gemini-cli/CAPABILITIES.md`` (copied verbatim by ``emit_shared``).
"""
from __future__ import annotations

from scripts.build import emit
from scripts.build.serialize import gemini_dest
from scripts.build.targets.base import ExtrasContext, Target, emit_shared, register


def _extras(ctx: ExtrasContext) -> list[str]:
    """Gemini's non-content artifacts: the version-injected extension manifest (its ``${version}`` token
    filled from pyproject, mirroring claude-code/cursor), the BeforeTool write-gate adapter (hooks.json +
    hercules_gate.py), and — via ``emit_shared`` — the byte-identical canonical guard (hercules_state.py
    reader + frozen_tests.py, whose ``decide`` the adapter delegates to) plus CAPABILITIES.md."""
    emit.copy_versioned(ctx.src_target_dir / "gemini-extension.json",
                        ctx.out_root / "gemini-extension.json", ctx.version)
    written = ["gemini-extension.json"]
    written += emit.copy_map(ctx.src_target_dir, ctx.out_root,
                             {f"hooks/{n}": f"hooks/{n}" for n in ("hooks.json", "hercules_gate.py")})
    written += emit_shared(ctx, "hercules_state.py", "frozen_tests.py")
    return written


register(Target(
    name="gemini-cli",
    dest_fn=gemini_dest,
    emit_extras_fn=_extras,
))
