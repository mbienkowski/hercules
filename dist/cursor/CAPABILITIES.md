# Hercules on Cursor — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on Cursor as an official plugin
(`.cursor-plugin/plugin.json`), with three capability gaps disclosed here (the "disclose gaps, never
hide" principle):

- **No hard write-gate hook.** On Claude Code a PreToolUse hook can deny a premature artifact write;
  Cursor's `afterFileEdit` hook is notification-only and cannot veto an edit, so the approval gate is
  honored by the assistant, not blocked by the tool. Turn on Cursor's *ask-before-applying-edits*
  approval for a stronger backstop.
- **No per-agent model tier.** Every Hercules subagent runs on the model you select in Cursor (the
  build omits per-agent model on purpose). Claude Code assigns a heavier model to the orchestrator and
  lighter models to routine advisors; on Cursor that tiering is intentionally not applied.
- **Independent review is best-effort in the IDE.** The Design coverage and Build traceability gates
  delegate to a fresh, isolated `cynical-reviewer` subagent (Cursor >= 2.4). Cursor exposes **no**
  orchestrator-forced spawn — in-IDE delegation is heuristic or `@`-mention-driven — so Hercules
  requires an explicit reviewer **handshake** (the reviewer attests it read the requirements source and
  returns a coverage/traceability matrix) and **halts and asks you** if that handshake is missing,
  converting a silent self-review into a loud stop. A genuinely forced, isolated reviewer is available
  only when Hercules runs via the headless `cursor-agent --agent cynical-reviewer` CLI.
