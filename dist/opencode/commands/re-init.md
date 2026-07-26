---
description: Reset Hercules project configuration and registry/state
model: null
---



Reset the Hercules configuration for this project. Deletes or resets registry/state files and allows selecting new settings.

**Not a workflow phase** — standalone maintenance command, interactive.

---

## What this command does

- Removes/rebuilds `~/.hercules/config.json` registry entry for the current project
- Clears or resets `~/.hercules/state/{slug}.json` (delivery state)
- Allows selecting new settings: `docs_root`, `repositories`, `frozen_hook`, `keep_specs`, model preference
- Allows selecting new session-level settings: `tier` override, reviewer preference, model selection
- Optionally clears `docs/` artifacts (`INDEX.md`, learnings, session docs)

---

## Steps

1. Confirm current project directory matches registry (`directory`).
2. Show current registry entry (`docs_root`, `repositories`, `frozen_hook`, `keep_specs`).
3. Show current session state (`tier`, `current_phase`, `delivered_specs`, `pending_specs`).
4. Ask user: **delete registry/state files?** (yes / no / reset-only)
5. If yes: delete/rebuild registry entry; clear/reset state file; offer new settings selection.
6. Offer new settings selection: project-level and session-level adjustments (same options as init).
7. Optionally clear `docs/` artifacts (`docs/INDEX.md`, `docs/learnings.md`, session directories).
8. Confirm changes with user before applying.

---

## Warning

This deletes machine-local state (`~/.hercules/`). It does not delete code, specs in `docs/` (unless you choose to), or git commits. Always confirm before applying.
