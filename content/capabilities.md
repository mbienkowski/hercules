# Hercules on ${product} — capabilities & disclosed gaps

${target:opencode}
Hercules ships the full Discover → Design → Build → Ship methodology on OpenCode, with the
capability gaps disclosed here (the "disclose gaps, never hide" principle):
${target:cursor}
Hercules ships the full Discover → Design → Build → Ship methodology on Cursor as an official plugin
(`.cursor-plugin/plugin.json`), with the capability gaps disclosed here (the "disclose gaps, never
hide" principle):
${target:grok}
Hercules ships the full Discover → Design → Build → Ship methodology on Grok Build as a native,
installable plugin (`.grok-plugin/marketplace.json` → `dist/grok-build`). Grok Build's plugin format
mirrors Claude Code's — the same `agents/`/`commands/`/`skills/`/`hooks/` layout, a `plugin.json`,
and a `CLAUDE.md` instruction file — so the components load as a native Grok plugin, rooted at
`${GROK_PLUGIN_ROOT}`. Gaps disclosed here (the "disclose gaps, never hide" principle):
${target:gemini}
Hercules ships the full Discover → Design → Build → Ship methodology on Gemini CLI as an extension
(`gemini-extension.json` + `agents/`, `commands/`, `skills/`, `GEMINI.md`, `hooks/`), with the
capability gaps disclosed here (the "disclose gaps, never hide" principle):

- **Install.** `gemini extensions install <git-url-or-path>` pointing at the built `dist/gemini-cli/`
  directory (or a repo containing it) — the `gemini-extension.json` at that root **is** the install
  manifest; there is no separate repo-level marketplace descriptor. Installing an extension that ships
  hooks prompts an explicit security consent in Gemini CLI (the hook runs `python3` on your machine).
${target:copilot}
Hercules ships the full Discover → Design → Build → Ship methodology on GitHub Copilot CLI as an
installable plugin (`plugin.json` manifest; agents, commands, skills, and a write-gate hook), with the
capability gaps disclosed here (the "disclose gaps, never hide" principle):
${target:end}

${target:opencode}
- **Frozen-test write-gate: enforced (needs `python3`).** The plugin's `tool.execute.before` hook
  hard-denies an edit to a frozen test file during an active build — a real pre-write veto, matching
  Claude Code's PreToolUse gate — by invoking the same canonical guard (`hooks/frozen_tests.py`). It
  requires `python3` on PATH; if `python3` is absent the gate **fails open** (the edit is allowed) and
  the approval gate falls back to prompt/permission-mediated discipline. Enable
  `permission: {edit: "ask"}` in your `opencode.json` for an additional backstop. One host limitation to
  be aware of (the plugin cannot pin it for you): on OpenCode versions where `tool.execute.before` does
  **not** also fire for subagent (`task`-tool) edits, a delegated edit bypasses the gate — run a version
  that fires the hook for subagent edits.
${target:cursor}
- **Frozen-test write-gate: works *with* Cursor's capabilities (needs `python3`).** Cursor's
  `afterFileEdit` is notification-only, so a Composer edit to a frozen test **cannot be blocked after it
  lands**. (Cursor also has a generic `preToolUse` deny hook with a `Write` matcher; whether it vetoes the
  Composer edit path *before* it lands is unverified, so Hercules does not rely on it and does not pretend
  the edit is blocked.) The hooks (`hooks/hooks.json` →
  `hooks/hercules_gate.py`, reusing the same canonical guard state AND the same `frozen_override` policy)
  put the hard teeth where Cursor *can* block: `beforeShellExecution` **and** `beforeMCPExecution`
  **deny** a shell command or MCP tool call that writes to or commits a frozen test during a build. On
  the edit path the behaviour is **runtime-aware**:
    - **Interactive IDE (default): advisory, no working-tree mutation.** A frozen edit raises a loud,
      plain-language notice (`userMessage`) and Hercules leaves your file exactly as you left it — you
      undo it (Ctrl+Z) or grant an override. A silent revert would fight Cursor's model (the human owns
      their working tree), so Hercules doesn't do it.
    - **Headless (`HERCULES_RUNTIME_MODE=headless`, set by Hercules when it drives `cursor-agent -p` — no
      human present): automatic `git checkout` restore**, and it says so **only when git actually
      restored it** (never a false "reverted" claim on an untracked test or a non-git tree).
  The backstop behind the advisory path is the **acceptance gate**: before a spec retires, every frozen
  test is re-hashed against a baseline and any drift not covered by an override **HALTs the retire**,
  catching a tamper however it was made (`python -c`, an MCP write, the advisory IDE path). The hash
  *check* is deterministic, but — like Hercules' other Build gates — its *invocation* is prompt-enforced
  by the orchestrator, not hard-wired into a hook: it is a strong catch-at-acceptance, **not** an
  unbypassable lock (the honest scope; runtime-mediated, not tamper-proof). A user-granted
  `frozen_override` ("change test X") lifts the gate for that file this round, exactly as on Claude Code
  and OpenCode. The hooks need `python3` on PATH and fail **open** (allow / no-op) if it is absent — for
  the shell/MCP deny **and** the after-edit path — leaving the acceptance gate as the protection until
  `python3` is available; Build announces this at start. The shell/MCP checks are coarse **guardrails**,
  not a sound sandbox — and coarse in both directions: they can **under-block** (`python -c`, heredocs,
  cross-pipe data flow; a `git add .` / `git add -A` / `git commit -am` that stages a frozen test **by
  pathspec without naming it** — a string matcher cannot resolve a pathspec against the index; or an MCP
  server that hides the target path from its arguments, or whose event uses payload keys the adapter
  doesn't recognise — then the MCP call fails open), and they can
  **over-block** (matching is basename-level, so a write to an *unrelated* file that happens to share a
  frozen test's basename can be denied during a build). Turn on Cursor's *ask-before-applying-edits*
  approval for an additional in-IDE backstop.
${target:grok}
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
${target:gemini}
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
${target:copilot}
- **Frozen-test write-gate: a real `preToolUse` veto (needs `python3`).** Unlike Cursor's
  notification-only `afterFileEdit`, Copilot CLI's `preToolUse` hook runs *before* a tool executes and
  can return `permissionDecision: "deny"` to block it. Hercules wires this
  (`hooks/hooks.json` → `hooks/hercules_gate.py`) so an edit to a frozen acceptance test during an
  active Build is **denied before it lands** — a true pre-write block, keyed off the SAME canonical
  frozen state AND the SAME `frozen_override` policy Claude Code, OpenCode, and Cursor read (the adapter
  reuses `frozen_tests.decide`, not a re-port), so the block message and the "change this test — <why>"
  escape hatch are identical across ecosystems.
    - **The matcher covers Copilot's real edit tools.** The hook fires for Copilot's file-mutating
      tools — `create`, `edit`, `str_replace_editor`, and `apply_patch` (native regex matcher
      `create|edit|str_replace_editor|apply_patch`, compiled `^(?:PATTERN)$` against the runtime tool
      name). A read tool (`view`) is intentionally NOT matched: the doctrine locks frozen tests against
      *edits*, not reads (the implementing agent must read the very test it makes pass). The adapter also
      accepts the VS Code-compatible `PreToolUse` payload (`tool_name`/`tool_input`), so it works under
      either event-name casing.
    - **`python3` fail-open.** The hook is invoked as `python3 .../hercules_gate.py preToolUse` and the
      adapter fails **open** (allow) on any error, missing state, or unresolvable build — so a gate bug
      never bricks an unrelated edit. Copilot's own rule is the opposite for `preToolUse` command hooks
      (a crash or non-zero exit **fails CLOSED** — denies), which would turn a *missing* `python3` into a
      surprise denial. Hercules avoids that: the shipped `hooks.json` guards the invocation
      (`... || exit 0` on bash, `...; exit 0` on PowerShell) so an absent interpreter yields an empty
      decision — the fail-**open** direction — while a genuine deny still rides on the adapter's stdout
      JSON at exit 0. Build announces the `python3` dependency at start.
    - **Coarse, and honest about it.** Path extraction is basename/argument-level: the adapter reads the
      target path from the tool arguments by trying several plausible keys, so a tool that hides the path
      under an unrecognised key fails **open** (allow), and matching is basename-level like the other
      ecosystems (a write to an unrelated file sharing a frozen test's basename could be denied during a
      Build — over-block). The gate is a runtime-mediated **guardrail**, not a tamper-proof lock; it
      reads model-authored state, so it is not unbypassable. The backstop behind it is the **acceptance
      gate** (frozen tests re-hashed against a baseline before a spec retires), whose *check* is
      deterministic but whose *invocation* is prompt-enforced by the Build phase — a strong
      catch-at-acceptance, not a hard lock.
    - **`preToolUse` from a plugin is a young surface (external risk Hercules cannot pin).** Copilot has
      had reports that a *plugin-declared* `preToolUse` hook does not always fire (github/copilot-cli
      issue 2540). Hercules wires the hook the documented way and the acceptance gate covers the case
      where it does not fire; the release checklist re-verifies the live veto on a real `copilot`
      install rather than trusting CI alone. `preToolUse` command-hook **timeouts** are always fail-open
      by Copilot's design, so a slow guard never blocks work.
${target:end}

- **No per-agent model tier.** Every Hercules agent **inherits the model you select in ${product}** —
  the build omits a per-agent `model:` on purpose (this ecosystem's descriptor `models` are
  all-`null`). Claude Code assigns a heavier model to the orchestrator and lighter models to routine
  advisors; on ${product} that tiering is intentionally not applied — your one selected model drives
  everything.
${target:copilot}

- **Persona loads as `AGENTS.md`.** The always-on project instructions ship as the plugin's `AGENTS.md`
  (Copilot's custom-instructions convention), and the operational reference ships as an auto-loaded
  skill (`skills/hercules-reference/SKILL.md`) — so the workflow guidance reaches the agent through
  Copilot's own component loading, not a Claude-only `CLAUDE.md`.

- **Independent review is best-effort.** The Design coverage and Build traceability gates delegate to a
  fresh `cynical-reviewer` agent. Copilot exposes no orchestrator-forced isolated spawn, so — as on
  Cursor — Hercules requires an explicit reviewer **handshake** (the reviewer attests it read the
  requirements source and returns a coverage/traceability matrix) and **halts and asks you** if that
  handshake is missing, converting a silent self-review into a loud stop.
${target:gemini}

- **Independent review relies on subagent delegation.** The Design coverage and Build traceability gates
  delegate to a fresh `cynical-reviewer` subagent (shipped under `agents/`). Gemini CLI supports subagents,
  but exposes no orchestrator-forced isolated spawn, so — as on OpenCode/Cursor — independence is enforced
  by prompt (the reviewer attests it read the requirements source and returns a coverage/traceability
  matrix); the release checklist re-verifies subagent isolation on a real install rather than trusting CI.
${target:cursor}
  (On Cursor specifically, forcing advisors onto a cheap `fast` tier would also degrade the
  reasoning-heavy reviewers, and Cursor's `model: inherit` is itself unreliable in nested cases.)

- **Independent review is best-effort in the IDE.** The Design coverage and Build traceability gates
  delegate to a fresh, isolated `cynical-reviewer` subagent (**Cursor >= 2.5**, which added plugin
  packaging; isolated subagents landed in 2.4). Cursor exposes **no** orchestrator-forced spawn —
  in-IDE delegation is heuristic or `@`-mention-driven — so Hercules requires an explicit reviewer
  **handshake** (the reviewer attests it read the requirements source and returns a
  coverage/traceability matrix) and **halts and asks you** if that handshake is missing, converting a
  silent self-review into a loud stop. The closest to a forced, isolated reviewer is to run the review
  packet through the headless `cursor-agent -p` CLI — a fresh agent process with its own context;
  Cursor's CLI has no flag to select a named subagent, so the packet carries the reviewer mandate.

- **Plugin loading in the headless CLI is a young feature (external risk Hercules cannot pin).** Cursor
  loads plugin agents/commands/rules/hooks reliably in the IDE, but its `cursor-agent` CLI gained plugin
  support only recently and has toggled it via a feature flag; if a Cursor update disables or regresses
  it, the CLI-only paths (the forced-reviewer fallback above, and CI's live smoke) may not load the
  plugin — the IDE is unaffected. Likewise the read-only reviewer lock depends on Cursor honouring
  `readonly` subagents server-side, which has regressed before. These are disclosed as accepted external
  risks; the release checklist re-verifies them on a real install rather than trusting CI alone.
${target:end}
