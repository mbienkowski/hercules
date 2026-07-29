# Debate Consensus Protocol

Two or more advisors examining the same work return their findings, and the orchestrator converges
them before they reach a draft. A single advisor is a review, not a debate, and skips this protocol.

All advisor output follows the
[A2A Communication Protocol § Agent-Injected Core](a2a-communication-protocol.md) — format, STATUS
values and the debate reply shape are defined there. Built-in Explore/Plan/Workflow agents receive
the mechanics via Rule 7 in the Core; this file is the full reference for human and custom-agent
orchestrators who read files.

## complexity

Complexity is settled before the first round — the orchestrator's responsibility, performed before
dispatching Round 1. Inside the delivery workflow the complexity **is** the session tier, scored once
in Discover and never re-derived (`workflow-protocol.md` G7); an ad-hoc debate outside a workflow
gate is classified on its own.

The tier is the higher of two signals scored separately, never their average: how much work the
change is, and how far a mistake in it would reach.

A change touching auth, secrets, money, data migration, deletion, production config, concurrency or
personal data floors at `complexity:high` however small the diff.

Those name examples rather than a closed catalogue. A project's own code-of-conduct may add to them,
and so may the orchestrator, whose test is whether a bug here could damage data, money or access that
a redeploy cannot undo. It says so when it applies one.

| complexity | Effort signals | Blast-radius signals | Advisors | Rounds |
|---|---|---|---|---|
| `complexity:trivial` | typo, config value, single-line fix | no user-visible change | 0 | 0 |
| `complexity:low` | simple change, single scope, easily reversible | one bounded flow affected | 2 | 1 |
| `complexity:medium` | feature, multiple files, requires tests | multiple flows affected | 2–3 | 1–2 |
| `complexity:high` | architecture, cross-cutting, hard to reverse | data at risk, deletion, production config | 3–5 | 1–2 |
| `complexity:critical` | irreversible, system-wide, foundational | user data, security primitives, money | 4–6 | 2–3 + fresh eyes |

Advisors run in parallel inside a round; rounds run one after another. The advisor column sizes the
first round. The high end of the rounds column is a ceiling, never an itinerary — a further round
runs only when the one before it left something contested. The low end binds only at
`complexity:critical`, which runs its second round and its fresh-eyes panel whatever the convergence
state, because that is the level where a missed problem is least recoverable.

A debate needs two advisors and two rounds. Where the table allows a single round the advisors return
their findings in parallel and the orchestrator synthesises them; that is a set of opinions, and no
cross-examination takes place.

## Round 1 — Blind

Dispatch every advisor in a single message. Each receives only the task prompt — no shared context,
no peer output. Parallel dispatch is the enforcement mechanism: every advisor forms its position from
first principles before cross-contamination can occur. Collect all Round 1 output before proceeding.

## Converging a round

The orchestrator groups the entries by topic — one entry is one topic, per A2A rule 1 — and reads the
positions taken on each.

A topic is settled — two or more advisors spoke on the topic and state the same position. It is then
folded into the draft and reported as applied. Every other state is listed below.

| The topic | State | What happens |
|---|---|---|
| positions differ | contested | carried into the next round |
| one speaker, Blocker or High | contested | where the range allows a further round it is carried, and that round adds an advisor who has not spoken on it; at the ceiling it goes to the casting vote at `complexity:low` and to the user elsewhere |
| one speaker, lower severity | folded in | entered with the advisor who raised it named |
| raised by some, unaddressed by others | not settled | silence is never agreement, so it blocks closure until someone speaks to it |

A debate closes when every topic is settled and the level's floor is met. On closing a round the
orchestrator states in one line, per topic, the topic, its state, which roles spoke on it and who
carries each position, so a narrowing board is visible rather than silent.

## Carrying a position

A contested topic carries one advisor per position, including the position that found nothing wrong,
so that view is argued rather than dropped. Two advisors holding the same position count once, and
the next round's roster is the number of distinct positions rather than a figure from the table
above, bounded by that level's advisor maximum.

Where several advisors hold one position it is carried by the more senior voice, judged by the
standing the role would hold in an engineering organisation — architect over developer, QA engineer
over tester — which needs no maintained ranking, so a newly added advisor participates with nothing
to update and an ad-hoc expert's briefed agenda establishes its standing. Among equal standing it is
carried by whichever entry states the position most completely, and where that still ties, by the
first by role name, so the same input yields the same choice.

Each carried advisor receives the contested topics and every position taken on them, and either
revises its own position with reasons or holds it with evidence. Agreement with another position
requires the advisor's own reasoning — a restatement or paraphrase of a peer is invalid, as is bare
agreement.

## Fresh-eyes panel

`complexity:critical` convenes a panel after its final round, drawn inside its advisor maximum and
carrying no history of the rounds before it. Its findings are independent — no prior context, no
convergence bias. Agreement with the debate panel strengthens a finding; contradiction surfaces as an
open question. Every other level skips it.

## Synthesis

The orchestrator compiles the settled topics into the draft and reports them as applied. A debate
resolves only when every raised topic is settled.

Anything short of that which survives the level's ceiling is put to the user as a decision.
The choices are accept as-is, another angle, or override; a surviving finding is never auto-applied.

A reservation is carried to the user's decision, never resolved by the orchestrator, and any
contested finding is presented to the user verbatim as an open question.
