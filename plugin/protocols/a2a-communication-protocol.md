# A2A Communication Protocol

A tiny, terse format that the main orchestrator injects into every sub-agent so
agent-to-agent talk is direct and token-cheap. It applies to **every reply a sub-agent
sends back** in any multi-agent workflow — review, planning, research, brainstorming, data
extraction. Two cases are NOT wrapped in the line format: (a) a **named artifact you
author** (returned raw — MODE 0a); (b) **verbatim relay** of content you did not author
(an `[ATTACHMENT]` block — rule 5).

Validated to a unanimous 10/10 by an 8-lens adversarial debate (minimalism, instruction
adherence, usability, completeness, parseability, cold-start clarity, abuse-resistance,
generality). Keep it tiny — it must stay a small slice of the orchestrator's total
instruction budget. CI enforces this (see `internal/policy`).

## Agent-Injected Core

This is the **only** text injected into a sub-agent. Copy it verbatim into the delegation
prompt (and/or the agent's own `.md` body). Do not paraphrase.

```
A2A Communication Protocol  (every agent-to-agent reply; any multi-agent workflow)
0. MODE (first match wins):
   (a) Asked to PRODUCE a named artifact you author (spec/tasks/code/data/draft/file)?
       Return it raw, nothing else — no fence/prose unless the artifact's syntax needs it.
       Authorship gates this mode: if you did not author the content, (a) does not apply
       even when an artifact is requested — relay it via rule 5. The orchestrator signals
       this mode by its request and tracks it; you don't self-mark. If you have a
       Blocker/High about the artifact, emit that entry line first, then the raw artifact
       on the following lines.
   (b) Otherwise reply as entries (rules 1-5). To relay content you did NOT author, use rule 5.
1. One entry per line, exactly three ` | `-separated fields: [ROLE] STATUS | CONTENT | ACTION
   — always all three; never omit ACTION (use `none`). The orchestrator splits on the FIRST
   and LAST ` | `, so CONTENT (the middle) may contain a literal `|` (paths, shell, tables);
   keep ACTION pipe-free (reword or move detail into CONTENT). One per line, newline-separated;
   order evaluative entries Blocker>High>Medium>Nitpick>Pass, and Info entries by salience
   order. No other prose, fence, or blank line. One entry is fine; multiple are expected.
2. ROLE = the exact UPPERCASE tag the orchestrator assigned you (e.g. [QA]); never reuse
   a peer's tag or invent one.
3. STATUS: Blocker=gate fails, stop; High=fix or accept as documented risk; Medium=real
   but non-blocking; Nitpick=minor; Pass=reviewed, nothing to flag — name the scope AND
   what you checked (cases/risks considered), silence is never a pass; Info=purely
   descriptive payload (fact/option/data/answer), no judgement — if it implies any
   judgement/gate/decision, use an evaluative status instead.
4. CONTENT = the point in as few sentences as carry it (max 5); every sentence adds a
   distinct fact, no filler. When reviewing, state the consequence/failure mode (not just
   the defect) and cite section (planning) or file:line (code). ACTION = the fix or next
   step in 1-3 sentences, or `none` (Pass/Info default to none unless a decision is needed).
5. Verbatim relay: after the entries — one [ROLE] Pass | what + source + label | none line,
   then [ATTACHMENT: label] ...unchanged content... [/ATTACHMENT]. Relay external content
   (tool output/file/another agent), never your own prose; never summarise inside.
6. Debate: one line [ROLE] Agreement: N/5 | reasoning | none (N 0-5). Reasoning must cite
   the specific claim/section you agree or disagree with; a bare number, "+1", "I agree",
   or generic praise is invalid. An unresolved vote ends your role; orchestrator escalates.
7. Debate: classify complexity first — trivial=skip; low=R1 only; medium=R1+R2;
   high=R1+R2+R3; critical=R1+R2+R3+fresh-eyes(mandatory). R1 blind/parallel →
   R2 cross-examine (all see R1; Agreement: N/5) → R3 re-invoke ≤4/5 agents only.
   Max 3 rounds, then synthesise. Fresh-eyes: new agents, no R1/R2 history.
Example (review):   [QA] Blocker | auth_handler:42 lets an unauthenticated request reach the admin handler, exposing user data. | Gate the handler behind a session check.
Example (non-eval): [RESEARCH] Info | Postgres 16 ships logical-replication failover, relevant to the HA requirement. | none
```

## Orchestrator Section (NOT injected per-agent)

These rules govern the orchestrator's own behaviour. Do **not** paste them into each
sub-agent — keeping them out of the injected core is a per-spawn token saving.

- **ROLE assignment** — assign each sub-agent its `[ROLE]` tag at spawn to avoid collisions
  (cold-start agents can't self-coordinate tags). Track whether you requested an artifact
  (MODE 0a) vs entries, so you parse the reply in the mode you asked for.
- **Professional-critique mandate** — each critic does a real pass and surfaces its most
  important issue, or emits a scoped `Pass` stating what it checked. Never a rubber-stamp;
  empty praise / bare agreement is invalid (rules 3, 4, 6 enforce this in-band).
- **Debate mechanics** — Rule 7 in the Core carries the summary to all agents. Full
  orchestrator mechanics in [debate-consensus-protocol.md](debate-consensus-protocol.md).

## How to inject

A custom subagent receives its own `.md` body (system prompt), then the orchestrator's
delegation `prompt`, then project + user `CLAUDE.md`. Built-in **Explore** and **Plan**
agents skip `CLAUDE.md`. Use all three channels:

1. **Per-call `prompt` injection (mandatory)** — prepend the Agent-Injected Core to the
   delegation message of every sub-agent. This is the **only** channel that reaches built-in
   Explore/Plan agents, and it lands closest to the task. Always do this. For workflow spawns,
   the orchestrator prepends the delegation packet (`workflow-protocol.md#packet`) above the Core.
2. **`CLAUDE.md` pointer (one line)** — reinforces custom/ad-hoc agents that do read it:
   `Agent-to-agent output follows a2a-communication-protocol.md § Agent-Injected Core.`
   A pointer, not a paste — `CLAUDE.md` text carries less weight and duplication wastes budget.
3. **Owned agent `.md` body (highest adherence)** — for long-lived sub-agents you maintain,
   paste the full Core into the `.md` body (the system prompt).

## Reference (not injected)

**STATUS values** — first five are evaluative (severity-ordered); `Info` is non-evaluative.

| STATUS | Meaning | ACTION |
|--------|---------|--------|
| `Blocker` | Gate fails — work stops until resolved | the required fix |
| `High` | Serious — fix, or accept as a documented risk | the fix or the risk acceptance |
| `Medium` | Real issue, does not block on its own | the fix, or `none` |
| `Nitpick` | Minor clarity/style/consistency | usually `none` |
| `Pass` | Reviewed, nothing to flag — name scope + what was checked | `none` |
| `Info` | Purely descriptive payload (fact/option/data/answer) | `none` unless a decision is needed |

**Debate agreement** — `[ROLE] Agreement: N/5 | reasoning | none`:

| N | Meaning | Effect |
|---|---------|--------|
| 5 | Full agreement | resolved |
| 4 | Agree, minor reservation | resolved (reservation carried to synthesis) |
| 3 | Neutral | another round |
| 0–2 | Disagree → strong conflict | another round; if it persists past the cap → open question for the user |

**Provenance.** An original re-expression distilling the concepts from two prior internal
protocol documents — not a copy of their text. The `Info` status extends the source 5-status
set to 6 by design.
