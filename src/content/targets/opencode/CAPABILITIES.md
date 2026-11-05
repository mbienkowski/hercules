# Hercules on OpenCode — capabilities & disclosed gaps

> Verified against: OpenCode v1.19.5 (2026-10-28) — anomalyco/opencode plugin API ([index.ts](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/plugin/src/index.ts)). Re-check these notes when upgrading past it.

- **Gap: OpenCode v2 does not run this plugin.** OpenCode v2.x (v2.2.5, 2026-10-30) does not run v1
  plugins (see the migrate-v1 docs). On v2.x the whole Hercules plugin is inactive, memory included. This
  edition needs OpenCode v1.x.

- **Ordinary-chat project memory (needs `python3`).** The plugin's
  `experimental.chat.system.transform` runs `hooks/memory_hook.py text` asynchronously, with the project
  directory as both working directory and `cwd`, appending context to `output.system` and preserving its
  entries. Context is computed once per session (async, cached as a promise, so concurrent calls share one
  spawn) and re-attached on each model call. Compaction (`session.compacted`) drops the cache, so the next
  call recomputes it. Subagent (child) sessions are skipped. Calls with no session id (Agent.generate) get
  none. The hook writes only `~/.hercules/memory/`: the `.deliveries.json` state file, and a per-project
  store only after a capture.
  This hook has no prompt text, so it loads compact standing preferences and capture instructions,
  rather than prompt-specific search. Context is capped at 2,400 UTF-8 bytes.
  The host model captures explicit durable user preferences through `tools/memory_core.py` when
  its instructions and permissions allow; no separate model service runs and capture is not guaranteed.
  A missing interpreter, subprocess error or three-second timeout adds a memory-unavailable warning
  to system context and allows the model request to continue.
  This requires the experimental hook in the
  [official plugin interface](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/plugin/src/index.ts);
  compatibility with a different plugin API is not implied.

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

- **`project-reset` runs a program, and stops without one.** The maintenance command clears a
  project's record through a shipped program (`tools/project_reset.py`) rather than editing the
  record from prose, so its safety rules are code rather than instructions. It needs `python3` on
  PATH like the enforcement hooks do. Unlike them it does **not** fail open: with no interpreter the
  command stops with a message and changes nothing, because doing nothing is the safe default for a
  deletion. This is identical on every edition.

- **No per-agent model tier.** Every Hercules agent **inherits the model you select in OpenCode** —
  the build omits a per-agent `model:` on purpose (this ecosystem's descriptor `models` are
  all-`null`). Claude Code assigns a heavier model to the orchestrator and lighter models to routine
  advisors; on OpenCode that tiering is intentionally not applied — your one selected model drives
  everything.

