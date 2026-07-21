# Hercules for Cursor

A spec-first delivery methodology as a native Cursor plugin: it turns a request into requirements, then
specs, then implemented-and-tested code — with specialist advisors and requirement→test traceability.

## What it gives you

- **An always-on persona** (`rules/hercules-persona.mdc`) — Hercules leads the four-phase workflow.
- **Commands** — `/discover`, `/design`, `/build`, `/ship`, `/workflow`.
- **Specialist subagents** — architect, QA, security, and more, isolated per review.
- **Frozen-test enforcement (best-effort on Cursor)** — during Build, Hercules resists silent weakening
  of acceptance tests: `beforeShellExecution`/`beforeMCPExecution` deny the common frozen-test
  write/commit forms (a coarse guardrail, not a sandbox — some forms such as `git add .` slip past), the
  IDE Composer edit path is **advisory** (a notice, your tree untouched; a real `git checkout` revert
  only in headless `cursor-agent -p`), and a re-hash check gates each spec before it retires. On hosts
  whose edit hooks can veto a write before it lands the same lock is a real **pre-write veto**; on
  Cursor it is materially weaker — see [`CAPABILITIES.md`](./CAPABILITIES.md).

## Install (local)

1. Copy this plugin directory into `~/.cursor/plugins/local/hercules/`.
2. Restart Cursor.
3. Confirm it under **Customize → Plugins**; the commands appear in Composer.

The hooks need `python3` on PATH; without it they fail open (advisory only) — see `CAPABILITIES.md`.

## Disclosed capability gaps

Cursor handles a few enforcement surfaces differently (no pre-edit veto, no per-agent model tier,
best-effort independent review). All of them are disclosed, with the workarounds, in
[`CAPABILITIES.md`](./CAPABILITIES.md).
