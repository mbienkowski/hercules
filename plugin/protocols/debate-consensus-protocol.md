# Debate Consensus Protocol

When two or more agents evaluate the same topic, they debate and converge before their
findings are synthesised. Single-agent gates skip this protocol entirely.

All agent output in every round follows the
[A2A Communication Protocol § Agent-Injected Core](a2a-communication-protocol.md) —
format, STATUS values, and Agreement rules are defined there. Built-in Explore/Plan/Workflow
agents receive debate mechanics via Rule 7 in the Core; this file is the full reference for
human and custom-agent orchestrators who read files.

## complexity

Every debate is classified before Round 1. Classification is the orchestrator's responsibility, performed before dispatching Round 1 agents.

| complexity | Definition | Rounds |
|------------|-----------|--------|
| `complexity:trivial` | Typo, config value, single-line fix | none — skip debate |
| `complexity:low` | Simple change, single scope, easily reversible | Round 1 only |
| `complexity:medium` | Feature, multiple files, requires tests | Round 1 + 2 |
| `complexity:high` | Architecture, security, cross-cutting, hard to reverse | Round 1 + 2 + 3 |
| `complexity:critical` | Irreversible, system-wide, or foundational decision | Round 1 + 2 + 3 + fresh-eyes (mandatory) |

## Consensus thresholds

An agent signals its position after each round via `Agreement: N/5` (A2A rule 6):

| N | Meaning | Effect |
|---|---------|--------|
| 5 | Full agreement | Resolved — no further action needed |
| 4 | Agree with minor reservation | Resolved — reservation carried to Synthesis |
| 3 | Neutral / uncertain | Another round triggered (within the complexity cap) |
| 0–2 | Disagree / strong objection | Another round triggered; if unresolved after cap → open question |

A debate round closes when all agents reach ≥4/5 or the complexity cap is hit.

## Hard limits

- Maximum 3 rounds. Synthesis happens after Round 3 regardless of remaining disagreement.
- All rounds use A2A format throughout. No narrative prose between entry lines.
- Ad-hoc debates (user-triggered outside a structured gate): same limits apply.

## Round 1 — Blind

Dispatch all agents in a single message. Each receives only the task prompt — no shared
context, no peer output. Parallel dispatch is the enforcement mechanism: every agent forms
its position from first principles before cross-contamination can occur. Collect all
Round 1 output before proceeding.

## Round 2 — Cross-examination

Re-invoke all agents in a single message, each receiving all Round 1 findings. Each agent:

1. States `Agreement: N/5` per A2A rule 6
2. Challenges any finding they disagree with, with evidence — A2A format
3. Raises new issues surfaced by peers — A2A format

**Anti-echo-chamber rule:** Agreement at any level (including `5/5`) requires the agent's
*own* reasoning — not a restatement or paraphrase of another agent's words. Bare agreement
(`+1`, `I agree`, reworded copy without original substance) is invalid.

## Round 3 — Resolution (`complexity:high` and `complexity:critical` only)

Skip for `complexity:low` (Round 1 is its only round) and `complexity:medium` (Round 2 is its final round).

Re-invoke only agents who stated ≤4/5 after Round 2. Synthesise after Round 3 regardless
of remaining agreement level.

## Fresh-eyes panel

- `complexity:critical` — **mandatory**. Spawn after Round 3.
- `complexity:high` — optional, orchestrator's call.
- All other levels — skip.

Spawn new agents with no Round 1/2 history. Their findings are independent — no prior
context, no convergence bias. Agreements with the debate panel strengthen a finding;
contradictions surface as open questions.

## Synthesis

Compile findings from all rounds into a single consolidated list. Any finding with explicit
disagreement after the final round is flagged as contested and presented to the user
verbatim as an open question. Never auto-apply a contested fix.
