# Hercules on OpenCode — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on OpenCode, with two capability
gaps disclosed here (the "disclose gaps, never hide" principle):

- **No hard write-gate hook.** On Claude Code a PreToolUse hook can deny a premature artifact write;
  OpenCode has no equivalent, so the approval gate is prompt/permission-mediated — the agent presents
  the plan and waits, but it is not a runtime-enforced deny. Enable `permission: {edit: "ask"}` in your
  `opencode.json` for a stronger backstop.
- **No per-agent model tier.** Every Hercules agent runs on the model you select in OpenCode (the
  build omits per-agent `model:` on purpose). Claude Code assigns a heavier model to the orchestrator
  and lighter models to routine advisors; on OpenCode that tiering is intentionally not applied.
