"""Copilot CLI target: the ``plugin.json`` manifest, ``.github/plugin/marketplace.json`` registry
descriptor, the ``preToolUse`` write-gate (hooks.json + adapter), and the byte-copied canonical guard.

Capability prose lives in ``src/targets/copilot-cli/CAPABILITIES.md`` (copied verbatim by ``emit_shared``).
"""
from __future__ import annotations

from scripts.build import emit
from scripts.build.serialize import copilot_cli_dest
from scripts.build.targets.base import ExtrasContext, Target, emit_shared, register


def _extras(ctx: ExtrasContext) -> list[str]:
    """Copilot's non-content artifacts: the version-injected ``plugin.json`` manifest (its ${version}
    token filled from pyproject, mirroring claude-code/cursor), the marketplace registry descriptor at
    ``.github/plugin/marketplace.json``, the ``preToolUse`` write-gate (hooks.json + hercules_gate.py
    adapter, which reuses the SAME canonical frozen state + ``frozen_override`` policy as every other
    ecosystem), and — via emit_shared — the byte-identical canonical guard files plus CAPABILITIES.md."""
    emit.copy_versioned(ctx.src_target_dir / "plugin.json", ctx.out_root / "plugin.json", ctx.version)
    written = ["plugin.json"]
    written += emit.copy_map(ctx.src_target_dir, ctx.out_root, {
        "marketplace.json": ".github/plugin/marketplace.json",
        "hooks/hooks.json": "hooks/hooks.json",
        "hooks/hercules_gate.py": "hooks/hercules_gate.py",
    })
    written += emit_shared(ctx, "hercules_state.py", "frozen_tests.py")
    return written


register(Target(
    name="copilot-cli",
    dest_fn=copilot_cli_dest,
    emit_extras_fn=_extras,
))
