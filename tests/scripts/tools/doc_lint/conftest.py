"""Fixture tree for the document linter: one compliant business-requirements document and one
compliant spec, plus the helper that runs the tool and parses its reply.

The two clean documents are the load-bearing fixtures. Every rule test perturbs one of them, so a
rule that fires on the UNperturbed document is a false positive caught here rather than in seven
shipped distributions — which is the § "a rule is a hypothesis until it has met the whole corpus"
obligation, met by a corpus the suite owns.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from tests.scripts.tools.tool_harness import load_tool

main = load_tool("doc_lint")

REQUIREMENTS_NAME = "2026-08-04-booking-reschedule-business-requirements.md"
SPEC_NAME = "2026-08-04-booking-reschedule-spec-01-move-booking.md"

CLEAN_REQUIREMENTS = """# Business Requirements: booking-reschedule

## Goal
- **Problem** — customers who cannot make an appointment ring the salon, and 3 in 10 calls go unanswered.
- **Change wanted** — a customer moves an appointment without speaking to anyone.

## Users
- **Customer** — today rings the salon during opening hours and waits on hold.
- **Stylist** — today writes the change on paper and re-enters it later that day.

## Scope
### In scope
- Moving one confirmed appointment to another free slot.
- Telling both people when an appointment moves.

### Out of scope
- Cancelling an appointment outright, which already works today.
- Paying for an appointment, which the existing checkout already covers.

## Flows
### F1 — Customer moves a booking
- **Story** — as a customer I move my appointment without ringing the salon.
- M1 | Slot free and at least 2 hours away → appointment moves and both people are told.
- N1 | Slot taken while the customer was deciding → refused, and the next 3 free slots are offered.
- N2 | Under 2 hours before the start → refused, and the cancellation policy is shown.

### F2 — Stylist moves a booking
- **Story** — as a stylist I move an appointment when I am running late.
- M2 | Stylist picks a later free slot → appointment moves and the customer sees who changed it.
- N3 | Stylist picks a slot another customer already holds → refused, and the clash is named.

## Constraints
- Salon opening hours bound every offered slot, and no slot outside them is ever offered.
- The existing message service delivers every notice, and this work adds no new channel.
- A change made by one person is visible to the other within 60 seconds.

## Success criteria
- 8 in 10 reschedules finish without a phone call, measured over the first 30 days.
- No reschedule leaves two people holding one slot, measured by a daily clash count of 0.
- Median time to move an appointment stays under 90 seconds, measured from opening the booking.

## Risks & unknowns
- Adoption may stall where customers do not notice the option, measured by weekly usage.
- ASSUMPTION: the salon accepts a 2 hour cut-off, which the owner has not yet confirmed.
- A busy salon may see more clashes than the daily count of 0 allows, which needs watching.
"""

CLEAN_SPEC = """# Spec 01: move-booking
satisfies: [2026-08-04-booking-reschedule-business-requirements.md §Flows]
complexity: medium
profile: code

## Challenge
Moving an appointment looks like one write, and it is not. Two people can accept different slots in
the same minute, and the salon can never end the day holding two customers in one chair. The hard
part is choosing the winner without holding a database transaction open across the notification
call, because that call leaves the building and can hang for a long time.

## Scope
- Moving one confirmed appointment to a free slot inside the booking service.
- Emitting one notice per affected person once the move commits.

## Affected code
- `BookingCalendar` — gains a move operation alongside its existing create operation.
- `SlotClaim` — NEW, holds the winning claim for one slot and one time.

## Decision record
| Decision | Chosen | Rejected (why) | Risk of choice | Mitigation | Revisit when |
|---|---|---|---|---|---|
| Clash resolution | Optimistic claim on the slot row | Table lock, which blocks the whole calendar | A loser retries against a stale view | Return the 3 next free slots with the refusal | Clash refusals exceed 2 in 100 moves |

## Structure & patterns
| Pattern | Where | Why | Real use case |
|---|---|---|---|
| Optimistic concurrency | `SlotClaim` | Two claims in one minute cannot both win | The second claim is refused and offered alternatives |
| Compensating action | `BookingMove` | The notice is not transactional | Move commits, notice fails, replay from the stored move |

## Implementation
- **Claim first** — the slot claim MUST be taken before the appointment row moves.
- **Release on failure** — a failed move MUST release the claim it took.
- **Notify late** — the notice MUST be sent after the move commits, NEVER inside the transaction.

## Risks & mitigations
| Risk | Signal | Mitigation | Owner at build |
|---|---|---|---|
| Two winners for one slot | Daily clash count above 0 | One claim per slot and time | backend |
| Repeat notices on retry | Two notices within 60 seconds | Notify once per committed move | backend |

## Test suite
- **Unit:** claim wins, claim loses, claim released on failure — mock the clock, never the store.
- **Integration:** two concurrent moves against one slot resolve to exactly one winner.

## Acceptance criteria
- Given a free slot 3 hours away, When the customer confirms, Then the appointment moves. [F1:M1]
- Given a slot claimed 1 second earlier, When the customer confirms, Then the move is refused. [F1:N1]

## Known violations
None.

## Deletion note
Remove this file once the move operation ships. Code is the source of truth after delivery.
"""


def lint(tmp_path: Path, text: str, name: str, kind: str = "", tier: str = "medium",
         strict: bool = False, place_requirements: bool = True):
    """Write the document and run the tool over it, returning ``(exit_code, payload)``.

    The requirements document is placed alongside by default because that is where a spec actually
    lives, and its ``satisfies:`` reference has to resolve to something. Pass
    ``place_requirements=False`` to leave the reference dangling on purpose.

    The payload is PARSED, never matched as text — an unparseable reply is a real defect in a
    program whose whole output contract is one JSON object.
    """
    if place_requirements and name != REQUIREMENTS_NAME:
        (tmp_path / REQUIREMENTS_NAME).write_text(CLEAN_REQUIREMENTS, encoding="utf-8")
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    argv = ["check", "--path", str(path)]
    if kind:
        argv += ["--kind", kind]
    if tier:
        argv += ["--tier", tier]
    if strict:
        argv.append("--strict")
    return run(argv)


def run(argv):
    """Invoke the tool's ``main`` and parse the single JSON object it prints."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(list(argv))
    return code, json.loads(buffer.getvalue())


def fired(payload) -> set:
    """The rule identifiers present in a reply."""
    return {finding["rule"] for finding in payload.get("findings", [])}


def pad_words(text: str, bullets: int) -> str:
    """Grow a requirements document by whole bullets, so a budget test moves word count without
    introducing a second violation."""
    filler = "\n".join(
        "- **Note %d** — the salon confirms this rule with the owner before launch day." % index
        for index in range(bullets))
    return text.replace("\n## Success criteria", filler + "\n\n## Success criteria")


@pytest.fixture()
def clean_requirements() -> str:
    return CLEAN_REQUIREMENTS


@pytest.fixture()
def clean_spec() -> str:
    return CLEAN_SPEC
