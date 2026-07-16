---
name: session-summary
description: Produce a structured handoff note for the next developer. Use at the end of a Build session before handing work to a teammate, or on demand at any phase. Reads session artifacts and the project's machine-local state in ~/.hercules/ (the per-project state file) to summarise progress, key decisions, and the next step.
---

# session-summary

**Precondition:** an active session directory must exist inside the artifact root (`docs/` by default) with at least one artifact. If no session directory is found, stop and report: "No active session found — run `/hercules:discover` first."

## What it does

Reads the active session and produces a handoff note.

**Reads:**
- The active session in the project's state file `~/.hercules/state/{slug}.json` (see `hercules-reference § Machine-local state`) — `current_spec`, `delivered_specs`, `pending_specs`, `handed_off_by`, `handoff_note`
- Session artifacts in `docs/{active_session}/` — `*-business-requirements.md`, `*-spec-NN-*.md` (present ones only)
- `docs/learnings.md` — entries matching the session tag
- the project's code-of-conduct (any capitalization) if present — for project conventions that inform the "next step" note

**Produces:**

```
## Session handoff: {active_session}
**Status:** {current_phase}, current spec: {current_spec}
**Delivered specs:** {delivered_specs list, or "none yet"}
**Handed off by:** {handed_off_by} — "{handoff_note}"
**Key decisions:** [3–5 bullets from design rationale and ADR sections]
**Open threads:** [pending specs or deferred items]
**Next step:** {first pending spec} — {one sentence on what to do first}
```

Omit `Handed off by` line if `handed_off_by` is absent from the active session.

## Output

Print to chat for copy/paste into `handoff_note`. If the user says "save it", write to `docs/tmp/session-summary.md` atomically (temp + rename).

## Constraints

- Idempotent: re-running produces the same output for the same context.
- Read-only: never modifies session artifacts or the project's machine-local state.
