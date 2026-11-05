# Hercules on Grok Build — capabilities & disclosed gaps

> Verified against: Grok Build 1.0.45 @ xai-org/grok-build 2bdd1d6 (2026-09-29; repo has no tags/releases) — xai-grok-hooks source (config.rs, runner/command.rs). Re-check these notes when upgrading past it.

- **Project memory after the first tool call (needs `python3` and a trusted plugin).** `PostToolUse`
  runs `hooks/memory_hook.py`, and its `additionalContext` is the output Grok delivers to the model;
  session-start and prompt-submit output does not reach it. Delivery happens once per session, after the
  session's first tool call, so a chat that never calls a tool gets no memory. `PostCompact` resets
  delivery state, so the next tool call re-delivers. An MCP-instructions alternative was rejected: it is
  capped at 2,048 characters, needs a tool, and carries no workspace directory. The plugin must be trusted
  (`--trust` or `~/.grok/plugins`). Context is capped at 2,400 UTF-8 bytes. The hook writes only
  `~/.hercules/memory/`: the `.deliveries.json` state file, and a per-project store only after a
  capture. Capture depends on the host model's instructions and permissions; no separate model service runs.
  See the [official hooks guide](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/10-hooks.md).

Hercules ships the full Discover → Design → Build → Ship methodology on Grok Build as a native,
installable plugin (`.grok-plugin/marketplace.json` → `dist/grok-build`). Grok Build's plugin format
mirrors Claude Code's — the same `agents/`/`commands/`/`skills/`/`hooks/` layout, a `plugin.json`,
and a `CLAUDE.md` instruction file — so the components load as a native Grok plugin, rooted at
`${GROK_PLUGIN_ROOT}`. Gaps disclosed here (the "disclose gaps, never hide" principle):

- **Frozen-test write-gate: enforced (needs `python3`).** The plugin's `PreToolUse` hook
  (`hooks/hooks.json`, matcher `Edit|MultiEdit|Write|NotebookEdit`) invokes the same canonical guard
  (`hooks/frozen_tests.py`, shipped byte-identical to Claude Code's) to hard-deny (exit 2) an edit to a
  frozen test during an active build. Earlier builds of this hook passed the script in an `args` field,
  which Grok ignores; the command resolved to `<plugin>/hooks/python3`, failed open, and the gate was
  silently inactive. The command now names `python3` and the script directly. `apply_patch` edits are
  still not guarded on Grok. It requires `python3` on PATH; if `python3` is absent the gate
  **fails open** (the edit is allowed) and the frozen-test protection rests on the acceptance-gate
  re-hash (`frozen_baseline`) alone until `python3` returns — Build announces this at start. The hook
  reads the plugin's own files via `${GROK_PLUGIN_ROOT}`; on a Grok build that populates
  `${CLAUDE_PLUGIN_ROOT}` for compatibility instead, swap the token. **Verify on your Grok Build
  version that `PreToolUse` fires for the file-edit tool** (not only shell) — if it fires for shell
  only, the edit-path veto degrades to the best-effort shell/MCP-deny tier and the acceptance re-hash
  is the backstop.

- **`project-reset` runs a program, and stops without one.** The maintenance command clears a
  project's record through a shipped program (`tools/project_reset.py`) rather than editing the
  record from prose, so its safety rules are code rather than instructions. It needs `python3` on
  PATH like the enforcement hooks do. Unlike them it does **not** fail open: with no interpreter the
  command stops with a message and changes nothing, because doing nothing is the safe default for a
  deletion. This is identical on every edition.

- **No per-agent model tier.** Every Hercules agent **inherits the model you select in Grok Build** —
  the build omits a per-agent `model:` on purpose (this ecosystem's descriptor `models` are
  all-`null`). Claude Code assigns a heavier model to the orchestrator and lighter models to routine
  advisors; on Grok Build that tiering is intentionally not applied — your one selected model drives
  everything.

