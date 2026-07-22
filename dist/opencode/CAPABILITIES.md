# Hercules on OpenCode — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on OpenCode, with the
capability gaps disclosed here (the "disclose gaps, never hide" principle):

- **Frozen-test write-gate: enforced (needs `python3`).** The plugin's `tool.execute.before` hook
  hard-denies an edit to a frozen test file during an active build — a real pre-write veto, matching
  Claude Code's PreToolUse gate — by invoking the same canonical guard (`hooks/frozen_tests.py`). It
  requires `python3` on PATH; if `python3` is absent the gate **fails open** (the edit is allowed) and
  the approval gate falls back to prompt/permission-mediated discipline. Enable
  `permission: {edit: "ask"}` in your `opencode.json` for an additional backstop. One host limitation to
  be aware of (the plugin cannot pin it for you): on OpenCode versions where `tool.execute.before` does
  **not** also fire for subagent (`task`-tool) edits, a delegated edit bypasses the gate — run a version
  that fires the hook for subagent edits.

- **No per-agent model tier.** Every Hercules agent **inherits the model you select in OpenCode** —
  the build omits a per-agent `model:` on purpose (this ecosystem's descriptor `models` are
  all-`null`). Claude Code assigns a heavier model to the orchestrator and lighter models to routine
  advisors; on OpenCode that tiering is intentionally not applied — your one selected model drives
  everything.

