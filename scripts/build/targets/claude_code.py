"""Claude Code target: the native plugin tree + byte-copied non-content files."""
from __future__ import annotations

from scripts.build import emit
from scripts.build.targets.base import ExtrasContext, Target, register

# Byte-copied Claude sources (non-markdown): host settings and hooks (incl. the canonical guard
# authored here). The plugin manifest is NOT here — its ${version} token is injected from pyproject
# via copy_versioned (see _extras), so the source carries a token, not a literal to hand-bump.
_COPIES = {
    "settings.json": "settings.json",
    "hooks/hooks.json": "hooks/hooks.json",
    "hooks/frozen_tests.py": "hooks/frozen_tests.py",
    "hooks/hercules_state.py": "hooks/hercules_state.py",
}


def _extras(ctx: ExtrasContext) -> list[str]:
    written = emit.copy_map(ctx.src_target_dir, ctx.out_root, _COPIES)
    emit.copy_versioned(ctx.src_target_dir / "plugin.json",
                        ctx.out_root / ".claude-plugin" / "plugin.json", ctx.version)
    written.append(".claude-plugin/plugin.json")
    return written


register(Target(
    name="claude-code",
    renames={"persona.md": "CLAUDE.md"},
    emit_extras_fn=_extras,
))
