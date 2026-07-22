# Hercules on Gemini CLI — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on Gemini CLI as an extension
(`gemini-extension.json` + `agents/`, `commands/`, `skills/`, `GEMINI.md`, `hooks/`), with the
capability gaps disclosed here (the "disclose gaps, never hide" principle).

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
    firing check. If Gemini adds another file-mutating tool name, add it to `_MUTATING` in the adapter.
  - **Fail-open.** The hook needs `python3` on PATH and fails **open** (prints nothing, exit 0) on any
    error, malformed input, or a missing `python3` — a gate bug never bricks an unrelated edit. Where the
    gate is inactive, the **acceptance backstop** (every frozen test re-hashed against a baseline before a
    spec retires, halting on un-overridden drift) remains the protection; Build announces this at start.
    The block is runtime-*mediated*, not tamper-proof against a model that rewrites its own state.

- **No per-agent model tier.** Every Hercules subagent **inherits the model you select in Gemini CLI** —
  the build omits a per-agent `model:` on purpose (`models.json[gemini-cli]` is all-`null`), as OpenCode
  and Cursor do. Claude Code assigns a heavier model to the orchestrator and lighter models to routine
  advisors; on Gemini that tiering is intentionally not applied — your one selected model drives everything.

- **Independent review relies on subagent delegation.** The Design coverage and Build traceability gates
  delegate to a fresh `cynical-reviewer` subagent (shipped under `agents/`). Gemini CLI supports subagents,
  but exposes no orchestrator-forced isolated spawn, so — as on OpenCode/Cursor — independence is enforced
  by prompt (the reviewer attests it read the requirements source and returns a coverage/traceability
  matrix); the release checklist re-verifies subagent isolation on a real install rather than trusting CI.
