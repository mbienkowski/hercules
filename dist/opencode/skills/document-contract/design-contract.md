# Solution design — the contract

Owner: **the team**. Audience: whoever builds it. A spec answers the business requirement it names
in `satisfies:`, and answers it precisely enough that two engineers reading it build the same thing.

A `profile:` header says what is being delivered — `code` today, with `deck`, `sheet` and `doc` to
follow. It changes the vocabulary of three sections (Affected code, Contracts, Verification) and
nothing else, which is what lets one contract serve a service and a slide deck without forking.

## Sections, in this order

| Section | What belongs | From tier |
|---|---|---|
| `## Challenge` | **The one prose slot.** The requirement restated in your words + the single hardest thing | all |
| `## Scope` | What this spec delivers, and which service | all |
| `## Affected code` | Existing classes and modules touched; each named, or marked NEW | all |
| `## Decision record` | One row per real decision (below) | all |
| `## Structure & patterns` | Each pattern named, why, and one real use case | medium |
| `## Naming contract` | Domain vocabulary, names rejected, why | high |
| `## Implementation` | Key decisions, and what the code-of-conduct binds | all |
| `## Rules — DO / DON'T` | Two columns, imperative, each row testable | high |
| `## Risks & mitigations` | Risk, the signal it is happening, the mitigation, who owns it | medium |
| `## Test suite` | Unit / integration / API / E2E, and what must never be mocked | all |
| `## Acceptance criteria` | Given / When / Then, each bound to a scenario identifier | all |
| `## Known violations` | Rules expected to fail at scaffold time. `None.` when there are none | all |
| `## Deletion note` | How this spec retires once delivered | all |

`## Test suite` and `## Acceptance criteria` are exempt from the word budget. They are read by Build,
not skimmed by a person, and trimming them causes exactly the uncovered behaviour the traceability
gate then blocks.

## Ambiguity is the defect this document exists to prevent

A sentence two engineers read differently has already cost the rework. Replace, don't soften:

| Instead of | Write |
|---|---|
| the token should expire quickly | the token expires 15 minutes after issue |
| handle errors appropriately | 401 on an expired token, 429 after 5 attempts a minute, 503 when the provider is unreachable |
| returns 200, 409, etc. | returns 200, 409 or 503, and no other status |
| It is written before the row moves | the slot claim MUST be taken before the appointment row moves |

The last one matters more than it looks. Bullets drop the subject and the modality a sentence
carries, so a terse document can be **more** ambiguous than a wordy one. In `## Implementation` and
`## Rules — DO / DON'T`, every bullet names its subject and states its obligation — `MUST`,
`MUST NOT`, or `MAY … WHEN …`.

## Decision record — one row per decision

```markdown
| Decision | Chosen | Rejected (why) | Risk of choice | Mitigation | Revisit when |
|---|---|---|---|---|---|
| Clash resolution | Optimistic claim on the slot row | Table lock, which blocks the whole calendar | A loser retries against a stale view | Return the 3 next free slots with the refusal | Clash refusals exceed 2 in 100 moves |
```

**Revisit when** must be observable — a metric, a date, an event. "If problems arise" is not a
trigger, it is a hope. A rejected alternative with no reason is worse than no row: it looks
considered.

## Naming — two questions, both from the code-of-conduct

The project's own Working principles already ask these of its code; a spec answers them before the
code exists.

1. **Would the name survive swapping the implementation?** Name the role, not the vendor. A vendor
   token is legal in an adapter class and nowhere else. `IdempotencyStore` is a port;
   `RedisIdempotencyStore` is its adapter; `RedisIdempotencyCache` is a design that cannot change
   its storage without a rename — and "cache" implies evictable when the data is authoritative.
2. **Would a reader with no context know what it does?** `findCompletedRefund(key)` says what it
   does; `getData(key)` sends the reader off to check. Avoid whole-word verbs that name a category
   rather than a job — do, handle, process, manage, check — and nouns that fit anything — data,
   info, manager, helper, util, processor.

```markdown
## Naming contract
| Concept | Name | Rejected | Why rejected |
|---|---|---|---|
| Port | `IdempotencyStore` | `RedisIdempotencyCache` | Vendor token, and "cache" implies evictable; this is authoritative |
| Reserve | `reserveKey(key, fingerprint): Reservation` | `setNx()` | Leaks the storage command into the domain |
```

## Patterns — named, warranted, and deviations explained

```markdown
| Pattern | Where | Why | Real use case |
|---|---|---|---|
| Idempotency key + fingerprint | `RefundRequestGuard` | Tells a retry apart from a conflicting reuse of a key | Same key, different amount → 409, not a second refund |
| Port / adapter | `IdempotencyStore` | Storage is a swap candidate within 12 months | Store moves to Postgres with no domain edits |

**Deviation:** no repository-per-aggregate here. WHY: the guard owns one key and a TTL, not an
aggregate, so a repository would add a lifecycle nothing uses.
```

A pattern named without a why is decoration. A deviation without a why is a bug someone will
"correct" later.

## DO / DON'T

```markdown
| DO | DON'T |
|---|---|
| Reserve the key BEFORE calling the provider | Call the provider first and record afterwards |
| Store a fingerprint of the request | Store the raw request body |
| Return the stored response verbatim on a replay | Recompute the response on replay |
| Fail closed when the store is unreachable | Fall through to the provider when the store is down |
```

Each row is one imperative a reviewer could check against a diff. "Prefer immutability" is advice,
not a rule — it belongs in the code-of-conduct if it belongs anywhere.

## Risks carry a signal, not just a worry

```markdown
| Risk | Signal | Mitigation | Owner at build |
|---|---|---|---|
| Two winners for one slot | Daily clash count above 0 | One claim per slot and time | backend |
```

A risk with no mitigation is an entry in a worry list. A mitigation with no signal cannot be known
to have worked.

## The prose slot

`## Challenge` is the only section that takes paragraphs, and it earns them by doing something
bullets cannot: stating what is genuinely hard before anyone proposes a solution.

> Moving an appointment looks like one write, and it is not. Two people can accept different slots
> in the same minute, and the salon can never end the day holding two customers in one chair. The
> hard part is choosing the winner without holding a transaction open across the notification call,
> because that call leaves the building and can hang.

Under 150 words, no technology named. If it needs a technology to be explained, it is not the
challenge — it is a decision, and it belongs in the decision record.
