# Hercules on Gemini CLI — capabilities & disclosed gaps

> Verified against: Gemini CLI v0.67.0 (2026-11-04) — geminicli.com/docs/hooks + source @ 1fe22af. Re-check these notes when upgrading past it.

> Gemini CLI is replaced by Antigravity CLI for unpaid and Google One tiers since 2026-06-18; this edition's notes do not cover Antigravity.

- **Ordinary-chat project memory (needs `python3` and enabled hooks).** `SessionStart` and `BeforeAgent`
  invoke `hooks/memory_hook.py gemini`, returning `hookSpecificOutput.additionalContext`. The host model
  receives compact preferences and instructions to capture explicit durable user preferences through
  `tools/memory_core.py`; capture depends on its compliance and tool permissions. Context is capped at
  2,400 UTF-8 bytes. Delivery state is per session in `~/.hercules/memory/.deliveries.json`. `/clear` and
  `--resume` re-deliver on the next prompt. A manual `/compress` (`PreCompress`, matcher `manual`) resets
  delivery state. Auto-compression re-delivers roughly per 256 KB of transcript growth (a heuristic). With
  `contextManagement.enabled`, `PreCompress` never fires. The hook is not wired to automatic compression
  because it would fire every turn. The hook writes only `~/.hercules/memory/`: the `.deliveries.json` state
  file, and a per-project store only after a capture. Failures allow the chat to continue; no separate model
  service performs extraction.
  See the [official hook reference](https://geminicli.com/docs/hooks/reference/).

Hercules ships the full Discover → Design → Build → Ship methodology on Gemini CLI as an extension
(`gemini-extension.json` + `agents/`, `commands/`, `skills/`, `GEMINI.md`, `hooks/`), with the
capability gaps disclosed here (the "disclose gaps, never hide" principle):

- **Install.** `gemini extensions install <git-url-or-path>` pointing at the built `dist/gemini-cli/`
  directory (or a repo containing it) — the `gemini-extension.json` at that root **is** the install
  manifest; there is no separate repo-level marketplace descriptor. Installing an extension that ships
  hooks prompts an explicit security consent in Gemini CLI (the hook runs `python3` on your machine).

- **Frozen-test write-gate: a real pre-write block (needs `python3`).** Unlike Cursor's notification-only
  edit hook, Gemini's `BeforeTool` event fires **before** a tool touches disk and can veto it — the same
  shape as Claude Code's `PreToolUse`. `hooks/hooks.json` wires `BeforeTool` with the matcher
  `write_file|replace` to `hooks/hercules_gate.py`, which reuses the **canonical** frozen-guard state
  (`hercules_state.py`) **and** the canonical `frozen_override` policy (`frozen_tests.py`, both shipped
  byte-identically). On an edit to a frozen test during an active build it returns Gemini's block
  decision `{"decision": "deny", "reason": ...}` (`deny` is the documented decision; `block` is a
  documented alias), carrying the same canonical reason — including the `"change test X — <why>"` escape
  hatch — that Claude Code, OpenCode, and Cursor emit. A user-granted `frozen_override` lifts the gate
  for that file this round, identically to the other ecosystems.
  - **Host-verification point (release-checklist item).** The gate assumes `BeforeTool` actually fires
    for Gemini's `write_file` **and** `replace` tools with the target path in `tool_input.file_path`. The
    payload shape and the deny contract are confirmed against the Gemini CLI hooks docs, but that the
    event fires for *both* edit tools (and that a `deny` decision aborts the edit) is verified on a real
    `gemini` install before release, not by CI alone — the same posture as Cursor's `${CURSOR_PLUGIN_ROOT}`
    firing check. If Gemini adds another file-mutating tool name, add it to the gate's tool map in the
    ecosystem descriptor.
  - **Fail-open.** The hook needs `python3` on PATH and fails **open** (prints nothing, exit 0) on any
    error, malformed input, or a missing `python3` — a gate bug never bricks an unrelated edit. Where the
    gate is inactive, the **acceptance backstop** (every frozen test re-hashed against a baseline before a
    spec retires, halting on un-overridden drift) remains the protection; Build announces this at start.
    The block is runtime-*mediated*, not tamper-proof against a model that rewrites its own state.
  - **Shell/MCP writes are backstop-only.** The `BeforeTool` matcher gates Gemini's `write_file`/`replace`
    edit tools; a write to a frozen test via `run_shell_command` (`echo > …`, `sed -i`, `git checkout`) or
    an MCP filesystem server is **not** vetoed at write-time — only the edit-tool path is a hard block.
    That gap is caught after the fact by the acceptance backstop (re-hash at retire), matching Cursor's
    honestly-coarse guardrail scope. (The adapter accepts both snake_case and camelCase payloads and
    resolves the path across the common key spellings, so a wire-format difference cannot silently no-op
    the edit-tool veto.)

- **`project-reset` runs a program, and stops without one.** The maintenance command clears a
  project's record through a shipped program (`tools/project_reset.py`) rather than editing the
  record from prose, so its safety rules are code rather than instructions. It needs `python3` on
  PATH like the enforcement hooks do. Unlike them it does **not** fail open: with no interpreter the
  command stops with a message and changes nothing, because doing nothing is the safe default for a
  deletion. This is identical on every edition.

- **No per-agent model tier.** Every Hercules agent **inherits the model you select in Gemini CLI** —
  the build omits a per-agent `model:` on purpose (this ecosystem's descriptor `models` are
  all-`null`). Claude Code assigns a heavier model to the orchestrator and lighter models to routine
  advisors; on Gemini CLI that tiering is intentionally not applied — your one selected model drives
  everything.

- **Independent review relies on subagent delegation.** The Design coverage and Build traceability gates
  delegate to a fresh `cynical-reviewer` subagent (shipped under `agents/`). Gemini CLI supports subagents,
  but exposes no orchestrator-forced isolated spawn, so — as on OpenCode/Cursor — independence is enforced
  by prompt (the reviewer attests it read the requirements source and returns a coverage/traceability
  matrix); the release checklist re-verifies subagent isolation on a real install rather than trusting CI.
