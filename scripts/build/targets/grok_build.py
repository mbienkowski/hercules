"""Grok Build target: a native Grok plugin whose format mirrors Claude Code's.

Grok Build's plugin layout is the same shape as Claude Code's (``agents/``/``commands/``/``skills/``/
``hooks/`` + a ``plugin.json``), so the target reuses the Claude-Code serialization (``GrokBuildSerializer``,
minus per-agent ``model:``). What is *native to Grok* is the distribution: the plugin ships under
``.grok-plugin/`` (its marketplace descriptor) and its ``PreToolUse`` hook is rooted at
``${GROK_PLUGIN_ROOT}`` (the env var Grok exports to plugin hooks), not Claude's ``.claude-plugin/`` /
``${CLAUDE_PLUGIN_ROOT}``. The canonical frozen-test guard is byte-copied from the shared source;
capability prose lives in ``src/targets/grok-build/CAPABILITIES.md`` (copied verbatim by ``emit_shared``).
"""
from __future__ import annotations

from scripts.build import emit
from scripts.build.targets.base import ExtrasContext, Target, emit_shared, register

# Grok-authored non-content files (its own hook wiring + the agent/skill/command roster).
_COPIES = {
    "settings.json": "settings.json",
    "hooks/hooks.json": "hooks/hooks.json",
}


def _extras(ctx: ExtrasContext) -> list[str]:
    emit.copy_versioned(ctx.src_target_dir / "plugin.json",
                        ctx.out_root / ".grok-plugin" / "plugin.json", ctx.version)
    written = [".grok-plugin/plugin.json"]
    written += emit.copy_map(ctx.src_target_dir, ctx.out_root, _COPIES)
    # Canonical guard (byte-identical to Claude Code's frozen_tests.py + hercules_state.py) + CAPABILITIES.md.
    written += emit_shared(ctx, "hercules_state.py", "frozen_tests.py")
    return written


register(Target(
    name="grok-build",
    renames={"persona.md": "CLAUDE.md"},
    emit_extras_fn=_extras,
))
