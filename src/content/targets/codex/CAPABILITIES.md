# Hercules on Codex — capabilities & disclosed gaps

> Verified against: openai/codex main @ e7f32cf (2026-11-05) — https://learn.chatgpt.com/docs/hooks + codex-rs source. Re-check these notes when upgrading past it.

Hercules ships the full Discover → Design → Build → Ship methodology on Codex as a native plugin
(`.codex-plugin/plugin.json`) whose reusable phase and advisor components are Codex skills. The plugin
also ships a Codex `PreToolUse` hook; the host asks you to review/trust plugin hooks before they run.

- **Ordinary-chat project memory (needs `python3` and trusted hooks).** `SessionStart` (every source:
  startup, resume, clear, compact, fork) and `UserPromptSubmit` invoke `hooks/memory_hook.py`, delivering
  compact preferences and instructions to capture explicit durable user preferences through
  `tools/memory_core.py`. Delivery state is per session in `~/.hercules/memory/.deliveries.json`: session
  start always delivers, and compaction resets it. The existing host model performs extraction; capture
  depends on its permissions and compliance, with no separate model service. Context is capped at 2,400
  UTF-8 bytes. Memory failures allow the chat to continue. The event and context contract follows the
  [official hook reference](https://learn.chatgpt.com/docs/hooks). The hook writes only `~/.hercules/memory/`:
  the `.deliveries.json` state file, and a per-project store only after a capture.
  Codex hashes the whole plugin folder for hook trust, so every plugin update needs re-trust (startup
  "Trust all" or `/hooks`). There is no plugin-side pre-trust; administrators can use managed hooks.



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
