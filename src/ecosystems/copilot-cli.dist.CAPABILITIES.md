# Hercules on GitHub Copilot CLI — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on GitHub Copilot CLI as an
installable plugin (`plugin.json` manifest; agents, commands, skills, and a write-gate hook), with the
capability gaps disclosed here (the "disclose gaps, never hide" principle):

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
- **No per-agent model tier.** Every Hercules agent **inherits the model you select in Copilot** — the
  build omits a per-agent `model:` on purpose (the copilot-cli descriptor's `models` are all-`null`), matching
  OpenCode and Cursor. Claude Code assigns a heavier model to the orchestrator and lighter models to
  routine advisors; on Copilot that tiering is intentionally not applied — your one selected model drives
  everything.
- **Persona loads as `AGENTS.md`.** The always-on project instructions ship as the plugin's `AGENTS.md`
  (Copilot's custom-instructions convention), and the operational reference ships as an auto-loaded
  skill (`skills/hercules-reference/SKILL.md`) — so the workflow guidance reaches the agent through
  Copilot's own component loading, not a Claude-only `CLAUDE.md`.
- **Independent review is best-effort.** The Design coverage and Build traceability gates delegate to a
  fresh `cynical-reviewer` agent. Copilot exposes no orchestrator-forced isolated spawn, so — as on
  Cursor — Hercules requires an explicit reviewer **handshake** (the reviewer attests it read the
  requirements source and returns a coverage/traceability matrix) and **halts and asks you** if that
  handshake is missing, converting a silent self-review into a loud stop.
