---
description: Lightweight guided delivery — same 4 phases, faster, token-efficient
model: null
agent: hercules
---



Lightweight guided delivery: same 4 phases, trimmed debates, optional Ship. Keeps the full Hercules schema (`protocols/…`, `hercules-reference §…`) but runs faster and cheaper — ideal for trivial-to-medium tasks where token cost matters more than deep multi-round review.

**Plan mode — required.** Enter plan mode at start; leave at each approval gate. Regenerate full drafts, never patch.

Key differences from full workflow: debates capped at **1 round max** regardless of tier; independent reviewer **skipped for trivial/low** (optional for medium+); **Ship is optional** — say "skip ship" after Build to finish.

---

## Quick start

> Welcome — quick version. Discover → Design → Build → Ship (optional). Let's go. 🔍

---

## Phase 1 — Discover

*Purpose: pin the need quickly.*

Run `/hercules:discover` (Steps 0–7). For speed: cap advisor debate at **1 round** (low-complexity mode — see `protocols/debate-consensus-protocol.md`). Skip the full debate for `trivial` tasks; run 1 round for `low`/`medium`/`high`/`critical`.

When covered, approve and save. Then say **"move to Design"**.

---

## Phase 2 — Design

*Purpose: specs + delivery order — faster.*

Run `/hercules:design` (Steps 1–9). Read the requirements. Debate capped at **1 round max**. For `trivial`/`low` tiers, skip the independent reviewer spawn (coverage gate is self-checked); for `medium+`, make the reviewer optional — ask: "Run independent review? (yes/no)". On "no", proceed with a brief self-check note.

Approve specs, then **"move to Build"**.

---

## Phase 3 — Build

*Purpose: deliver specs with TDD — same rigor, shorter prompts.*

Run `/hercules:build`. Same delivery plan, same frozen-test rules (`protocols/workflow-protocol.md`), same quality gates. Per-spec spawn uses the delegation packet (`protocols/workflow-protocol.md#packet`) but with shorter prompts (no re-explaining full protocol each time — reference by section).

When complete:

> ✓ Build complete. Tests green, traced, delivered.
>
> **Ship is optional.** Say **"move to Ship"**, **"skip ship"**, or **"continue all"**.

---

## Phase 4 — Ship (optional)

*Purpose: commit and push — only if you say so.*

If you said "skip ship", announce: "✓ Workflow complete. Artifacts delivered; Ship skipped per request." Stop.

Otherwise run `/hercules:ship`. When done:

> ✓ Shipped. Commit: [one-liner]. Run `/hercules:workflow-lite` for the next feature.

---

## Model / cost note

This command uses the same model as your host selection (`opencode.json` `model`). Opencode descriptors set all tiers to `null` — no per-agent model switching. Subagents inherit the primary model; switching models mid-flow loses context and rarely saves tokens (reloading artifacts costs more than the coding phase). For simple tasks, set a cheaper global model; for complex tasks, keep the capable one. See `capabilities.md` § No per-agent model tier.
