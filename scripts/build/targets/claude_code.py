"""Claude Code target: the native plugin tree + byte-copied non-content files."""
from __future__ import annotations

from scripts.build import emit
from scripts.build.targets.base import ExtrasContext, Target, register

# Byte-copied Claude sources (non-markdown): host settings, hooks (incl. the canonical guard authored
# here), and the versioned plugin manifest into its .claude-plugin/ home.
_COPIES = {
    "settings.json": "settings.json",
    "hooks/hooks.json": "hooks/hooks.json",
    "hooks/frozen_tests.py": "hooks/frozen_tests.py",
    "hooks/hercules_state.py": "hooks/hercules_state.py",
    "plugin.json": ".claude-plugin/plugin.json",
}


def _extras(ctx: ExtrasContext) -> list[str]:
    return emit.copy_map(ctx.src_target_dir, ctx.out_root, _COPIES)


register(Target(
    name="claude-code",
    renames={"persona.md": "CLAUDE.md"},
    emit_extras_fn=_extras,
))
