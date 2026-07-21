"""Cursor target: the ``.cursor-plugin`` manifest, ``.mdc`` persona rule, and write-gate hooks.

Capability prose lives in ``src/targets/cursor/CAPABILITIES.md`` (copied verbatim by ``emit_shared``).
"""
from __future__ import annotations

from scripts.build import emit
from scripts.build.serialize import cursor_dest
from scripts.build.targets.base import ExtrasContext, Target, emit_shared, register

def _extras(ctx: ExtrasContext) -> list[str]:
    """Cursor's non-content artifacts: the version-injected manifest (its ${version} token filled from
    pyproject, mirroring claude-code), the cursor write-gate adapter (hooks.json + hercules_gate.py),
    and — via emit_shared — the shared canonical guard files (from which the adapter reuses the SAME
    frozen_override policy Claude/OpenCode apply, not a re-port) plus CAPABILITIES.md."""
    emit.copy_versioned(ctx.src_target_dir / "plugin.json",
                        ctx.out_root / ".cursor-plugin" / "plugin.json", ctx.version)
    written = [".cursor-plugin/plugin.json"]
    written += emit.copy_map(ctx.src_target_dir, ctx.out_root,
                             {f"hooks/{n}": f"hooks/{n}" for n in ("hooks.json", "hercules_gate.py")})
    # Marketplace-facing assets referenced by the manifest (logo) or expected by submission (README).
    written += emit.copy_map(ctx.src_target_dir, ctx.out_root,
                             {"logo.svg": "logo.svg", "README.md": "README.md"})
    written += emit_shared(ctx, "hercules_state.py", "frozen_tests.py")
    return written


register(Target(
    name="cursor",
    dest_fn=cursor_dest,
    emit_extras_fn=_extras,
))
