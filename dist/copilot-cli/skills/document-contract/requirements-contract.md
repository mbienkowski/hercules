# Business requirements — the contract

Owner: **Product**. Audience: stakeholders. Committed forever, never deleted. Business language
only: it says what the business needs and how anyone would know it arrived, never how it is built.

## Sections, in this order

| Section | What belongs | From tier |
|---|---|---|
| `## Goal` | The problem in the user's own words, and the change wanted | all |
| `## Users` | Each actor, and how they cope today without this | all |
| `## Scope` | `### In scope` / `### Out of scope`, as noun phrases. Out is never empty | all |
| `## Flows` | Per flow: a story line, then the scenarios (below) | low |
| `## Constraints` | Business, time, regulatory, integration | all |
| `## Success criteria` | Measurable — a number or a named standard, one per goal | all |
| `## Risks & unknowns` | What could bite, and the assumptions still open | medium |
| `## Technical suggestions (non-binding)` | The **only** place technical vocabulary is legal | optional |
| `## Design references` | Links to Figma, wireframes, PRDs, contracts. Links only | optional |

## Flows — one line per scenario

Gherkin belongs in the tests, not here: three lines per scenario means twenty scenarios fill the
page and nobody reads to the end. One line each keeps the whole contract scannable, and Build
expands them into Given/When/Then when it writes the tests.

```markdown
### F2 — Reschedule a booking (Customer)
- **Story** — as a customer I move my appointment without ringing the salon.
- M1 | Slot free and at least 2 hours away → booking moves; both people are told.
- N1 | Slot taken while the customer decided → refused; the next 3 free slots are offered.
- N2 | Under 2 hours before the start → refused; the cancellation policy is shown.
- C1 | Both confirm different slots in the same minute → last confirm wins; the other sees the change.
```

- `M` main · `N` negative · `C` corner. Identifiers are **never renumbered** — deleting `M2` leaves
  a hole, and holes are cheaper than breaking every downstream reference.
- Each line: a trigger, an arrow, an **observable** outcome. "refused, and the next 3 slots offered"
  — not "handled gracefully". A tester must be able to tell whether it happened.
- Every flow names at least one way it can **fail**. A flow that cannot fail has not been thought
  about; if it genuinely cannot, write `scenarios: n/a` and the reason.
- Failure cases should not be outnumbered by happy paths. Six mains and one negative means the
  failure space is unexamined, not absent.

### Which corner cases earn a line

Admit one that scores **two or more** of: it is irreversible (money, data, access a redeploy cannot
undo) · it sits on a boundary already named in another line · it involves two actors, retries or
partial failure · it has bitten before (`docs/learnings.md`).

Everything else goes on one `Considered and dropped:` line. That single line is what stops a
200-row matrix: the thinking stays visible without the rows.

## Keeping technical detail as a suggestion

The most common drift is a technical decision arriving dressed as a requirement. The containment is
simple: technical vocabulary is legal in `## Technical suggestions (non-binding)` and nowhere else,
and even there it is offered, never settled.

| Instead of | Write |
|---|---|
| The `BookingCalendar` table must be refactored to hold a move | An appointment can move to another slot without being cancelled and rebooked |
| Store the reschedule in a nightly job | A change made by one person is visible to the other within 60 seconds |
| Use the existing queue for notifications | Both people are told when an appointment moves |

Every suggestion bullet is hedged (`could`, `might`, `one option`, `worth considering`) and the
section closes with its fixed sentence:

> These are suggestions from Product, not decisions. Design owns the technical choice.

Design records in the spec when it **rejects** one. That is what stops the section becoming a side
channel for orders.

## Gathering the requirement

Six questions are always asked, whatever the tier — at trivial and low they fit in one message:

**PROBLEM** the real problem · **ACTORS** who is affected · **MAIN-FLOW** the path that matters ·
**FAILURE-MODES** what must fail gracefully · **DONE** a number · **NOT-DOING** the boundary.

Further banks open when the subject calls for them: data & privacy · money · access & roles ·
integrations · volume & scale · recovery & undo · regulatory · migration from what exists ·
adoption · deprecation. Higher tiers open more of them, and argue more counter-positions — at
medium and above, one of those is always "do nothing, or something cheaper".

### When an answer is too thin to build on

An answer under eight words, or one that just restates the question, or a "done" with no number in
it, is not an answer yet. Do this, in order:

1. **Re-ask with three concrete options and a recommended default.** Most thin answers are a
   symptom of an abstract question.
2. **Offer an assumption:** "shall I write it as X?" — and log it as `ASSUMPTION:` in
   `## Risks & unknowns` when they accept.
3. **Say plainly that you cannot proceed** — but only once per question, only at medium and above,
   and always with a default they can accept in one word:
   > I cannot write requirements for this. Without [X] the Flows section would be invented. One
   > sentence is enough, or point me at whoever knows.

No `ASSUMPTION:` line should survive into a `high` or `critical` document — by then it is either
confirmed or it is a risk with a name on it.

**On the tier.** The user can lower it, and lowering it is legitimate. Say what it costs — "low
drops the corner-case floor and the risk section" — so the choice is informed rather than a way to
make the questions stop.

## Worked fragment

```markdown
## Goal
- **Problem** — customers who cannot make an appointment ring the salon, and 3 in 10 calls go unanswered.
- **Change wanted** — a customer moves an appointment without speaking to anyone.

## Success criteria
- 8 in 10 reschedules finish without a phone call, measured over the first 30 days.
- No reschedule leaves two people holding one slot, measured by a daily clash count of 0.

## Risks & unknowns
- Adoption may stall where customers do not notice the option, measured by weekly usage.
- ASSUMPTION: the salon accepts a 2 hour cut-off, which the owner has not yet confirmed.
```

Note what each bullet carries: a number, a measurement point, or a named owner. A bullet made only
of adjectives is padding, and reads as considered when nobody considered anything.
