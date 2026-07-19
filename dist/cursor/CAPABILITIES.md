# Hercules on Cursor — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on Cursor as an official plugin
(`.cursor-plugin/plugin.json`), with three capability gaps disclosed here (the "disclose gaps, never
hide" principle):

- **Frozen-test write-gate: partially enforced (needs `python3`).** Cursor has no pre-file-edit veto
  (`afterFileEdit` is notification-only), so a Composer edit to a frozen test **cannot be prevented** —
  but the plugin's hooks (`hooks/hooks.json` → `hooks/hercules_gate.py`, reusing the same canonical
  guard state) add real teeth: `beforeShellExecution` **hard-denies** a shell command that writes to or
  commits a frozen test during a build, `beforeReadFile` denies reads of frozen tests, and
  `afterFileEdit` **reverts** a frozen edit after the fact (a backstop, since it cannot block). The
  hooks need `python3` on PATH and fail **open** if it is absent. Turn on Cursor's
  *ask-before-applying-edits* approval for an additional backstop. This is stronger than advisory but
  weaker than Claude Code's hard pre-write veto — the Composer-edit path is revert-only.
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
