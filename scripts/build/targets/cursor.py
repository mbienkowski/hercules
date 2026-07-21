"""Cursor target: the ``.cursor-plugin`` manifest, ``.mdc`` persona rule, and write-gate hooks.

Capability prose lives in ``src/targets/cursor/CAPABILITIES.md`` (copied verbatim by ``emit_shared``).
"""
from __future__ import annotations

from scripts.build import emit
from scripts.build.serialize import cursor_dest
from scripts.build.targets.base import ExtrasContext, Target, emit_shared, register

# Byte-copied Cursor sources (non-markdown). The manifest is versioned at its source
# (src/targets/cursor/plugin.json, in VERSION_TARGETS) and copied verbatim, mirroring claude-code.
_COPIES = {
    "plugin.json": ".cursor-plugin/plugin.json",
}


def _extras(ctx: ExtrasContext) -> list[str]:
    """Cursor's non-content artifacts: the versioned manifest copy, the cursor write-gate adapter
    (hooks.json + hercules_gate.py), and — via emit_shared — the shared canonical guard files
    (from which the adapter reuses the SAME frozen_override policy Claude/OpenCode apply, not a re-port)
    plus CAPABILITIES.md."""
    written = emit.copy_map(ctx.src_target_dir, ctx.out_root, _COPIES)
    written += emit.copy_map(ctx.src_target_dir, ctx.out_root,
                             {f"hooks/{n}": f"hooks/{n}" for n in ("hooks.json", "hercules_gate.py")})
    written += emit_shared(ctx, "hercules_state.py", "frozen_tests.py")
    return written


register(Target(
    name="cursor",
    dest_fn=cursor_dest,
    emit_extras_fn=_extras,
))
