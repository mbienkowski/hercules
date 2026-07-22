# Hercules on Grok Build — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on Grok Build as a native,
installable plugin (`.grok-plugin/marketplace.json` → `dist/grok-build`), reusing Grok's documented
Claude-Code compatibility (it reads Claude-format plugins, agents, commands, skills, hooks, and a
`CLAUDE.md` instruction file). Gaps disclosed here (the "disclose gaps, never hide" principle):

- **Frozen-test write-gate: enforced (needs `python3`).** The plugin's `PreToolUse` hook
  (`hooks/hooks.json`, matcher `Edit|MultiEdit|Write|NotebookEdit`) invokes the same canonical guard
  (`hooks/frozen_tests.py`, shipped byte-identical to Claude Code's) to hard-deny (exit 2) an edit to a
  frozen test during an active build. It requires `python3` on PATH; if `python3` is absent the gate
  **fails open** (the edit is allowed) and the frozen-test protection rests on the acceptance-gate
  re-hash (`frozen_baseline`) alone until `python3` returns — Build announces this at start. The hook
  reads the plugin's own files via `${GROK_PLUGIN_ROOT}`; on a Grok build that populates
  `${CLAUDE_PLUGIN_ROOT}` for compatibility instead, swap the token. **Verify on your Grok Build
  version that `PreToolUse` fires for the file-edit tool** (not only shell) — if it fires for shell
  only, the edit-path veto degrades to the best-effort shell/MCP-deny tier and the acceptance re-hash
  is the backstop.
- **No per-agent model tier.** Every Hercules agent runs on the model you select in Grok Build (the
  build omits per-agent `model:` on purpose). Claude Code assigns a heavier model to the orchestrator
  and lighter models to routine advisors; on Grok Build that tiering is intentionally not applied.
