# Business Requirements: universal-plugin-distribution

> Hercules today exists only as a Claude Code plugin. Users of other AI coding tools cannot install
> it, and every new ecosystem would mean hand-maintaining another copy of all its content. This
> initiative makes Hercules **authored once and installable natively in each major AI coding
> ecosystem**, starting with two and growing one ecosystem at a time.

## Goal

Author the Hercules methodology once, in a single tool-neutral source, and deliver it as a native,
installable plugin per ecosystem. A user on any supported tool gets the identical methodology; the
maintainer edits one place and every ecosystem's plugin updates from that single edit. Each Hercules
specialist keeps a model matched to the difficulty of its job — a powerful model for complex
reasoning, an economical one for routine work — on every ecosystem that supports it.

## Users

- **Maintainers** — author and release once; the build produces every ecosystem's plugin. The
  constraint that shapes everything: solo/small-team maintenance cost.
- **End users** on each supported tool — install through their tool's own mechanism and get the same
  agents, commands, skills, persona, debate, and approval gates.
- **Contributors** — can improve content or add an ecosystem without forking the methodology (as the
  OpenCode contribution demonstrated).

## Scope

### In scope — v1 (ships together)

- One neutral source of truth for all Hercules content (persona, agents, commands, skills, protocols).
- A build that produces installable plugins, delivered for **Claude Code** and **OpenCode**.
- Per-specialist model matching (high / medium / low reasoning effort) preserved on both, with a
  sensible fallback when a preferred model is unavailable.
- One build command usable locally and in automation; outputs kept verifiably in sync with the source;
  a single version number across ecosystems.
- The existing OpenCode contribution (PR #11) is merged and credited; the universal build must
  reproduce its output with no unintended regression before replacing it.

### TBD (to be delivered) — after v1, one at a time, each proven before the next

**Codex — TBD.** Not part of any current delivery; listed so the architecture stays built to
accommodate it (adding one later is an increment, not a rework).

**Cursor — promoted into scope as v1.1** (2026-07-20). Originally queued as TBD; brought forward
because a Cursor distribution was contributed via PR #21. Its acceptance requirements are recorded
under `## v1.1 — Cursor ecosystem + delivery hardening` below, including the non-negotiable caveat
that Cursor's runtime behaviour must be **proven on a real Cursor install before release** (its
plugin-in-CLI surface cannot be fully verified in automation).

### Out of scope

- Any change to the Hercules methodology itself (phases, gates, debate) — this is distribution only.
- Ecosystems beyond the four named (revisit on demand).
- Publishing beyond what each ecosystem needs for a normal install.

## Constraints

- Solo/small-team maintenance: per-change effort must not multiply with each ecosystem; divergence
  between source and shipped output is caught automatically, never by hand.
- Each ecosystem installs from the project's public repository and has its own discovery rules; the
  repository layout must satisfy every tool's real installation path, verified against a live install
  before it is frozen.
- Ecosystem formats and model catalogs change frequently; the build must fail safely — never silently
  ship corrupted or stale output — and stale model mappings must be flagged automatically.
- Where an ecosystem cannot support a capability (a per-specialist model, an enforced approval gate),
  the gap is disclosed to the user in that ecosystem's plugin, never hidden.
- Licensing stays AGPL; external contributions are credited.

## Success criteria

- **v1:** one command builds both plugins from the single source; each installs through its
  ecosystem's normal mechanism and runs the full methodology; a green build means valid, in-sync,
  regression-checked output; the OpenCode plugin reproduces the contributed one (plus the deliberate
  model-matching restoration); one version number identifies the release everywhere.
- **Ongoing:** changing one agent/command/skill updates every shipped ecosystem from that single
  edit; adding the next ecosystem (Codex) requires no rework of the source or the build's
  architecture; per-specialist model matching visibly works wherever the ecosystem allows it.

## v1.1 — Cursor ecosystem + delivery hardening (added 2026-07-20)

This increment brings Cursor into scope and hardens the shared delivery machinery so that "one
source, many ecosystems" stays cheap to maintain as the ecosystem count grows. Each requirement is
plain-business intent; the technical specs trace to these.

### R1 — Cursor is a native, trustworthy ecosystem
A user on Cursor installs Hercules through Cursor's own plugin mechanism and gets the same
methodology. Hercules's safety guarantees (review-only specialists cannot write; protected tests
cannot be silently edited) must **actually take effect inside Cursor**, not merely be present in the
shipped files. Any capability Cursor cannot support is disclosed to the user, never hidden. Because
Cursor is a full IDE (not a CLI) and its plugin-in-automation surface is immature, Cursor's runtime
behaviour is **proven on a real Cursor install before release**, with at least a minimal automated
signal in CI and a documented manual verification for what automation cannot yet prove.

### R2 — Adding an ecosystem is additive, never a rewrite
Onboarding a new ecosystem must be additive configuration plus one self-contained strategy — it must
not require editing shared build logic with per-ecosystem special cases. The maintenance cost of the
build must not grow with each ecosystem added. There is one authoritative list of ecosystems; every
part of the system that needs to know "which ecosystems exist" derives from that single list.

### R3 — The quality pipeline is honest and correctly gated
The automated pipeline gates expensive checks behind cheap ones and must **never report success when
a required check did not truly pass**. The set of ecosystems the pipeline exercises derives from the
single ecosystem list (not a separate, drift-prone source), and the pipeline fails safe if that list
is ever empty rather than silently passing.

### R4 — Routine feedback stays fast
The pipeline's feedback loop must stay fast enough for everyday commits: the mutation-quality gate
completes in well under ten minutes without weakening the protection it provides (the same defects it
catches today are still caught).

### R5 — End-user and contributor instructions are separated
Instructions for people **using** Hercules and instructions for people **extending** Hercules live in
separate, non-duplicated documents, so neither audience wades through the other's material.
