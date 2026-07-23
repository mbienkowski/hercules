# Hercules on Cursor — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on Cursor as an official plugin
(`.cursor-plugin/plugin.json`), with the capability gaps disclosed here (the "disclose gaps, never
hide" principle):

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

- **No per-agent model tier.** Every Hercules agent **inherits the model you select in Cursor** —
  the build omits a per-agent `model:` on purpose (this ecosystem's descriptor `models` are
  all-`null`). Claude Code assigns a heavier model to the orchestrator and lighter models to routine
  advisors; on Cursor that tiering is intentionally not applied — your one selected model drives
  everything.
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
