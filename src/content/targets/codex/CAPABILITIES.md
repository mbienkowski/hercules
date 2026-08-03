# Hercules on Codex — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on Codex as a native plugin
(`.codex-plugin/plugin.json`) whose reusable phase and advisor components are Codex skills. The plugin
also ships a Codex `PreToolUse` hook; the host asks you to review/trust plugin hooks before they run.



- **`project-reset` runs a program, and stops without one.** The maintenance command clears a
  project's record through a shipped program (`tools/project_reset.py`) rather than editing the
  record from prose, so its safety rules are code rather than instructions. It needs `python3` on
  PATH like the enforcement hooks do. Unlike them it does **not** fail open: with no interpreter the
  command stops with a message and changes nothing, because doing nothing is the safe default for a
  deletion. This is identical on every edition.

- **No per-agent model tier.** Every Hercules agent **inherits the model you select in Codex** —
  the build omits a per-agent `model:` on purpose (this ecosystem's descriptor `models` are
  all-`null`). Claude Code assigns a heavier model to the orchestrator and lighter models to routine
  advisors; on Codex that tiering is intentionally not applied — your one selected model drives
  everything.
- **Skills-first integration.** Codex loads Hercules' phase and advisor material as reusable skills;
  the generated `AGENTS.md` is a companion project-instructions file and must be copied into a project
  when always-on persona guidance is wanted. Codex's plugin surface does not automatically register
  Hercules' original host-specific agent Markdown as named subagents, so delegation is skill-mediated
  unless a project separately provisions Codex custom-agent TOML files.
