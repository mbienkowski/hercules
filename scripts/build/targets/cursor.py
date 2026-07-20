"""Cursor target: the ``.cursor-plugin`` manifest, ``.mdc`` persona rule, and write-gate hooks."""
from __future__ import annotations

from scripts.build import emit
from scripts.build.serialize import cursor_dest
from scripts.build.targets.base import ExtrasContext, Target, register

# Byte-copied Cursor sources (non-markdown). The manifest is versioned at its source
# (src/targets/cursor/plugin.json, in VERSION_TARGETS) and copied verbatim, mirroring claude-code.
_COPIES = {
    "plugin.json": ".cursor-plugin/plugin.json",
}

_CAPABILITIES = """# Hercules on Cursor — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on Cursor as an official plugin
(`.cursor-plugin/plugin.json`), with three capability gaps disclosed here (the "disclose gaps, never
hide" principle):

- **Frozen-test write-gate: partially enforced (needs `python3`).** Cursor has no pre-file-edit veto
  (`afterFileEdit` is notification-only), so a Composer edit to a frozen test **cannot be prevented** —
  but the plugin's hooks (`hooks/hooks.json` → `hooks/hercules_gate.py`, reusing the same canonical
  guard state AND the same `frozen_override` policy) add real teeth: `beforeShellExecution`
  **hard-denies** a shell command that writes to or commits a frozen test during a build, and
  `afterFileEdit` **reverts** a frozen edit after the fact (a backstop, since it cannot block). A
  user-granted `frozen_override` ("change test X") lifts the gate for that file this round, exactly as
  on Claude Code and OpenCode. The hooks need `python3` on PATH and fail **open** if it is absent. Turn
  on Cursor's *ask-before-applying-edits* approval for an additional backstop. This is stronger than
  advisory but weaker than Claude Code's hard pre-write veto — the Composer-edit path is revert-only, and
  the shell check is a coarse guardrail against honest/accidental writes (it catches the common
  write/delete/redirect forms, but not `python -c`, heredocs, or cross-pipe data flow).
- **No per-agent model tier.** Every Hercules subagent **inherits the model you select in Cursor** — the
  build omits a per-agent `model:` on purpose (Cursor's `inherit` default), because forcing advisors onto
  a cheap `fast` tier would degrade the reasoning-heavy reviewers, and Cursor's `model: inherit` is itself
  unreliable in nested cases. Claude Code assigns a heavier model to the orchestrator and lighter models
  to routine advisors; on Cursor that tiering is intentionally not applied — your one selected model
  drives everything.
- **Independent review is best-effort in the IDE.** The Design coverage and Build traceability gates
  delegate to a fresh, isolated `cynical-reviewer` subagent (**Cursor >= 2.5**, which added plugin
  packaging; isolated subagents landed in 2.4). Cursor exposes **no** orchestrator-forced spawn —
  in-IDE delegation is heuristic or `@`-mention-driven — so Hercules requires an explicit reviewer
  **handshake** (the reviewer attests it read the requirements source and returns a
  coverage/traceability matrix) and **halts and asks you** if that handshake is missing, converting a
  silent self-review into a loud stop. The closest to a forced, isolated reviewer is to run the review
  packet through the headless `cursor-agent -p` CLI — a fresh agent process with its own context;
  Cursor's CLI has no flag to select a named subagent, so the packet carries the reviewer mandate.
- **Plugin loading in the headless CLI is a young feature (external risk Hercules cannot pin).** Cursor
  loads plugin agents/commands/rules/hooks reliably in the IDE, but its `cursor-agent` CLI gained plugin
  support only recently and has toggled it via a feature flag; if a Cursor update disables or regresses
  it, the CLI-only paths (the forced-reviewer fallback above, and CI's live smoke) may not load the
  plugin — the IDE is unaffected. Likewise the read-only reviewer lock depends on Cursor honouring
  `readonly` subagents server-side, which has regressed before. These are disclosed as accepted external
  risks; the release checklist re-verifies them on a real install rather than trusting CI alone.
"""


def _extras(ctx: ExtrasContext) -> list[str]:
    """Cursor's non-content artifacts: the versioned manifest copy, the write-gate hooks (cursor adapter
    + the shared canonical guard files, from which the adapter reuses the SAME frozen_override policy
    Claude/OpenCode apply — not a re-port), and CAPABILITIES.md."""
    written = emit.copy_map(ctx.src_target_dir, ctx.out_root, _COPIES)
    written += emit.copy_map(ctx.src_target_dir, ctx.out_root,
                             {f"hooks/{n}": f"hooks/{n}" for n in ("hooks.json", "hercules_gate.py")})
    written += emit.copy_map(ctx.shared_hooks_src, ctx.out_root,
                             {n: f"hooks/{n}" for n in ("hercules_state.py", "frozen_tests.py")})
    emit.write(ctx.out_root / "CAPABILITIES.md", _CAPABILITIES)
    written.append("CAPABILITIES.md")
    return written


register(Target(
    name="cursor",
    dest_fn=cursor_dest,
    emit_extras_fn=_extras,
))
