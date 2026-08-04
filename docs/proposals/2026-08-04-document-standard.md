# Proposal: the Hercules Document Standard

**Status:** proposal, awaiting decisions in § 10
**Scope:** how Discover writes `*-business-requirements.md` and how Design writes `*-spec-NN-*.md`
**Method:** six-advisor blind Round 1 (business-analyst, senior-qa, lead-architect, challenger, tooling, simplicity), converged per `protocols/debate-consensus-protocol.md`

---

## 1. The problem, stated precisely

| # | Symptom today | Root cause |
|---|---|---|
| P1 | Requirements drift into technical prescription | No containment rule; nothing separates "Product's suggestion" from "the team's decision" |
| P2 | Specs contain sentences readable two ways | No banned-ambiguity rule; no mandated modality (`MUST`/`MAY … WHEN`) |
| P3 | Docs are long and unread | No length budget of any kind, at any tier |
| P4 | Discovery is shy; plans start below standard | Groups A–E are five open questions with no floor, no push-back, no thin-answer test |
| P5 | "The spec turned out impossible mid-flight" | Nothing is executed before a plan is shown; feasibility is asserted, never checked |
| P6 | Depth does not track complexity | Tier sizes the **advisor count** only; it does not size the **document** |
| P7 | Rules live as prose instructions to an LLM | No machine-readable rule set, no linter, no verifiable evidence |

### 1.1 What "one screen" costs today — the arithmetic

A compliant medium-tier requirements doc under a naive "add all the sections" reading:

| Content | Lines |
|---|---|
| 6 existing sections | ~17 |
| 4 main flows + user stories | ~8 |
| negative scenarios (~2/flow) | ~8 |
| corner cases | ~6–10 |
| headers + blank lines | ~27 |
| **Total** | **~70** (high tier: **~115**) |

One screen is 40–55 rendered lines. **Medium busts by 1.4×, high by 2.3×.** This is the single hardest
constraint in the request, and § 3.3 resolves it with measurements rather than good intentions.

### 1.2 Measured headroom in this repo (`dist/claude-code`, run 2026-08-04)

| File | Tokens / ceiling | Headroom |
|---|---|---|
| `commands/discover.md` | 1952 / 2020 | **68** |
| `commands/design.md` | 2128 / 2200 | **72** |
| `commands/build.md` | 3254 / 3260 | **6** |
| `protocols/workflow-protocol.md` | 1183 / 1250 | 67 |
| `skills/hercules-reference/SKILL.md` | 3847 / 3900 | 53 |

Instruction chains against `HARD_GATE = 150`:

| Chain | Now | Spare |
|---|---|---|
| orchestrator: `build.md` | **139** | 11 |
| orchestrator: `design.md` | 95 | 55 |
| orchestrator: `discover.md` | 89 | 61 |
| **skill: any `SKILL.md`** | **0–31** | **~120** |

**Conclusion, load-bearing for the whole plan:** the commands cannot absorb a rule catalogue, and a new
file under `protocols/` is summed into *every* command chain (it would push `build.md` past the gate for
a command that never reads the rules). Skill chains carry no shared-protocol tax. Rules go in **data +
a tool**; only pointers go in prompts.

---

## 2. What gets built

| # | Artifact | Path | Why here |
|---|---|---|---|
| A1 | Rule + template data | `src/scripts/tools/doc_rules.json` | Not `.md` — invisible to every budget glob. Zero prompt cost. |
| A2 | Deterministic validator | `src/scripts/tools/doc_lint.py` | Rules become exit codes, not hopes. Stdlib-only (shipped-tool hygiene rule). |
| A3 | Pointer skill | `src/content/skills/document-contract/SKILL.md` | ~40 instructions, isolated chain. Says *which* kinds exist and how to read a failure — never the rule text. |
| A4 | Feasibility evidence recorder | `doc_lint.py probe record\|verify` | The agent never types a verdict; the exit code is derived. |
| A5 | Command wiring | `discover.md`, `design.md`, `build.md` | One line each: run the gate, relay non-zero, stop. |

**The template is generated, not prompted.** `doc_lint.py template --kind spec --tier high` emits the
skeleton. A test byte-compares that output against the fenced skeleton shipped in the commands, so the
prompt and the linter cannot drift. This is the core determinism move: today's templates are prose an
LLM may paraphrase; tomorrow's are program output.

---

## 3. The Business Requirements standard

Owner: **Product**. Audience: stakeholders. Business language only.

### 3.1 Section spine

| # | Section | Contains | Banned here |
|---|---|---|---|
| 0 | Frontmatter | `owner`, `tier`, `date`, `status` | free text |
| 1 | `## Goal` | the problem in the user's words + the change wanted | vision statements |
| 2 | `## Users & today` | `Actor — today: …` per actor | personas, demographics |
| 3 | `## Scope` (`In` / `Out`) | noun phrases; `Out` must be non-empty | rationale essays |
| 4 | `## Flows` | per flow: story line + `M` / `N` / `C` scenario lines | UI description, tech steps |
| 5 | `## Success criteria` | a number or a named standard, one per Goal bullet | "fast", "intuitive", "scalable" |
| 6 | `## Risks & unknowns` | risk + `ASSUMPTION:` items from discovery | mitigation plans (that is Design's job) |
| 7 | `## Technical suggestions (non-binding)` | the **only** place tech vocabulary is legal | any imperative |
| 8 | `## References` | links only | inline content |

### 3.2 The flow notation — one line per scenario

Rejected: Gherkin in the requirements doc (3+ lines per scenario; 20 scenarios = 60 lines — it is what
busts the screen budget). Rejected: wide tables (horizontal scroll). **Chosen: one-line ID form.**
Given/When/Then survives where it is machine-consumed — the spec's acceptance criteria and the test
names generated at Build.

```markdown
### F2 — Reschedule a booking (Customer)
Story: As a customer I move my appointment without calling the salon.
- M1 | Slot free and ≥2h away → booking moves; customer and stylist both notified.
- M2 | Stylist reschedules on behalf → same result; customer sees who changed it.
- N1 | Slot taken between viewing and confirming → refused, next 3 free slots offered, original untouched.
- N2 | Under 2h before start → refused; cancellation-fee policy shown.
- C1 | Both confirm different slots in the same minute → last confirm wins; the other sees the new time.
- C2 | Booking spans a daylight-saving change → shown in salon local time, no silent shift.
```

Line rules: ≤ 25 words, must contain `→`, must name an **observable** outcome (a status, a count, a
state, a message class). `M` main · `N` negative · `C` corner.

**IDs never renumber.** Deleting `M2` leaves a hole. Holes are cheap; renumbering breaks every
downstream reference.

### 3.3 Budgets — how "one screen" and "depth scales" both hold

Three separate meters, because one meter cannot do both jobs:

| Meter | Applies to | Why |
|---|---|---|
| **Words** (excluding frontmatter and fenced blocks) | narrative sections | stable, scriptable, maps to reading time |
| **Items** | enumerable sections (flows, scenarios, criteria) | a word cap on enumerables silently becomes a *coverage* cap — the exact content the rule exists to protect |
| **Fenced lines** | code/example blocks | ≤ 25 lines per document |

| Tier | BR soft / hard / floor | Spec soft / hard / floor | M | N | C |
|---|---|---|---|---|---|
| trivial | 200 / 300 / 100 | 250 / 375 / 100 | 1 | 1 | 0 |
| low | 350 / 500 / 180 | 400 / 600 / 180 | 2 | 2 | 1 |
| medium | 500 / 750 / 250 | 600 / 900 / 250 | 4 | 4 | 3 |
| high | 700 / 1050 / 350 | 850 / 1275 / 350 | 6 | 6 | 5 |
| critical | 900 / 1350 / 450 | 1100 / 1650 / 450 | 8 | 8 | 8 |

- **Soft** = warning the agent must answer in-session. **Hard** = block. **Floor** = block.
- The **floor is what enforces "low complexity still goes deep"** — a 60-word low-tier doc is not
  concise, it is absent.
- **`N ≥ M` always.** Six mains and two negatives means the failure space is unexamined, not absent.
- No single `##` section exceeds 40 % of the doc's soft cap.
- Spec caps are **per spec file**. Splitting into two specs is the legitimate escape hatch.

### 3.4 Which corner cases earn a line

A corner case is admitted only if it scores **≥ 2 of 4**:

1. **Irreversibility** — wrong costs data, money or access a redeploy cannot undo.
2. **Boundary adjacency** — it sits exactly on a number already named in an `M` or `N` line.
3. **Concurrency / ordering** — two actors, retries, replays, partial failure.
4. **Observed before** — it appears in `docs/learnings.md` or is a known incident class.

Everything scoring 0–1 goes into a single `Considered and dropped:` line. **This is what kills the
200-row matrix**: dropped cases stay visible without being enumerated.

### 3.5 Containment — technical detail as suggestion, never mandate

Three mechanical layers plus one judgement layer:

| Layer | Mechanism | Enforced by |
|---|---|---|
| Vocabulary containment | identifier shapes (backticks, `CamelCase`, `path/like/this`, `FILE.ext`, `CONSTANT_CASE`) illegal outside § 7 | `doc_lint DOC204` |
| Mandate phrases | `(?i)\b(must\|shall\|should\|needs? to\|has to)\s+(be\s+)?(implemented\|built\|stored\|cached\|indexed\|deployed\|hosted\|refactored)\b` and friends | `doc_lint DOC206` |
| § 7 hedging | every bullet matches `^- (Option\|Prior art\|Existing constraint\|Worth considering):` and contains `could\|might\|may`; section closes with a fixed sentence: *"These are suggestions from Product, not decisions. Design owns the technical choice."* | `doc_lint DOC207` |
| Intent | "the report should come out of the nightly job" — no banned token, still a mandate | `cynical-reviewer` |

Design must record in the spec when it **rejects** a § 7 suggestion. That is what stops § 7 becoming a
side channel for orders.

---

## 4. The Solution Design standard

Owner: **the team**. Audience: whoever builds it. "Rigid technical requirements answering the
business requirements document."

### 4.1 One spine, three profiled slots

Chosen over a template-per-deliverable (two sources of truth, guaranteed drift) and over fully abstract
wording ("Affected artifacts" — abstraction *is* the ambiguity being complained about). A `profile:`
header (`code` | `deck` | `sheet` | `doc`) changes the **vocabulary** of exactly three sections;
everything else is domain-neutral by construction. This is what makes the standard reusable for slide
decks, Word documents and spreadsheets later without forking it.

| # | Section | Mandate | Banned here | Unlocks at |
|---|---|---|---|---|
| 1 | **Challenge & restatement** | THE prose slot: the requirement in the author's words + the single hardest thing | bullets; any technology name; > 150 words | all tiers |
| 2 | **Decision record** | one row per real decision (§ 4.3) | prose | all tiers |
| 3 | **Scope / non-scope** | two symmetrical bullet lists | "etc."; open-ended items | all tiers |
| 4 | **Affected surface** *(profiled)* | code: files/classes · deck: slide IDs · sheet: workbook/ranges | unnamed targets ("the service layer") | all tiers |
| 5 | **Structure & patterns** | each pattern named + WHY + one real use-case line; deviations get a WHY row | a pattern named without a why | medium+ |
| 6 | **Naming contract** | domain vocabulary + rejected names + why rejected | vendor tokens outside adapters | high+ |
| 7 | **Contracts & interfaces** *(profiled)* | signatures / slide contract / column schema + types | types or nullability omitted | medium+ |
| 8 | **DO / DON'T** | two columns, imperative, each row testable | advice ("prefer"), unconditioned MAY | high+ |
| 9 | **Examples & fragments** | ≥ 1 concrete fragment | pseudo-code, `...` bodies | medium+ |
| 10 | **Risks & mitigations** | risk → trigger signal → mitigation → owner-at-build | a risk with no mitigation | medium+ |
| 11 | **Verification** *(profiled)* | test suite + mocking rules / review checklist + tolerances | "test thoroughly" | all tiers |
| 12 | **Acceptance criteria** | Given/When/Then, each bound to a scenario ID | criteria not traceable to § 1 | all tiers |
| 13 | **Known violations / deletion note** | unchanged from today | — | all tiers |

Sections 3/4/11/12/13 are today's `Scope` / `Affected code` / `Test suite` / `Acceptance criteria` /
`Known violations`, renamed. **This is an extension of `design.md` Step 9, not a rewrite.**

Sections 11 and 12 are **exempt from the word cap** (item caps instead) — they are machine-consumed,
and trimming them causes exactly the uncovered behaviour the coverage gate then blocks.

### 4.2 Worked fragment

```markdown
## 1. Challenge & restatement
Finance needs a refund to be safe to retry. Today a client that times out and retries creates a
second refund, and the money leaves twice. The requirement is that any number of identical retries
of one refund request produce exactly one movement of money and the same response body. The hard
part is not storage — it is deciding what "identical" means when the same client sends the same key
with a different amount, under concurrent duplicates, without holding a transaction open across the
payment provider call.

## 5. Structure & patterns
| Pattern | Where | Why | Real use-case |
|---|---|---|---|
| Idempotency key + request fingerprint | `RefundRequestGuard` | Distinguishes a retry from a conflicting reuse of a key | Same key + different amount → 409, not a silent second refund |
| Port / adapter | `IdempotencyStore` (port), adapter in `infrastructure/` | Storage is a swap candidate within 12 months | Store moves to Postgres with zero domain edits |
| Compensating action (not 2PC) | `RefundSaga` | The provider call is not transactional | Provider succeeds, local commit fails → replay from stored provider reference |

**Deviation:** no repository-per-aggregate here. WHY: the guard owns one key/value pair with a TTL,
not an aggregate; a repository would add a lifecycle we never use.

### DO / DON'T
| DO | DON'T |
|---|---|
| Reserve the key BEFORE calling the provider | Call the provider first and record after |
| Store the request fingerprint (SHA-256 of amount+currency+paymentId) | Store the raw request body |
| Return the stored response verbatim on a replay | Recompute the response on replay |
| Fail closed when the store is unreachable (503) | Fall through to the provider when the store is down |
| Set TTL from config `refund.idempotency.ttl` | Hardcode any duration |

## 6. Naming contract
| Concept | Name | Rejected | Why rejected |
|---|---|---|---|
| Port | `IdempotencyStore` | `RedisIdempotencyCache` | Vendor token + "cache" implies evictable; this is authoritative |
| Adapter | `RedisIdempotencyStore` (in `infrastructure/redis/`) | — | Vendor token legal ONLY in an adapter class name |
| Reserve op | `reserveKey(key, fingerprint): Reservation` | `setNx()` | Leaks the Redis command |
| Replay op | `findCompletedRefund(key)` | `getData(key)` | Not behaviour-revealing |
```

### 4.3 Decision record — exact format

```markdown
| Decision | Chosen | Rejected (why) | Risk of choice | Mitigation | Revisit when |
|---|---|---|---|---|---|
| Idempotency storage | Redis behind `IdempotencyStore` | Postgres table (write on hot txn path); in-memory (lost on restart) | Redis outage blocks all refunds | Fail closed + alert; adapter swap is one class | p99 > 400 ms OR Redis availability < 99.9 % for 2 consecutive weeks |
```

Rules: one row per decision · ≤ 12 words per cell · **"Revisit when" must be an observable condition**
(a metric, a date, an event) — never "if problems arise".

### 4.4 Naming discipline — "would I rename this if I swapped the library?"

Lexicons live in `doc_rules.json` and are extended per project by `code-of-conduct.md`:
`VENDOR` (redis, jackson, kafka, hibernate, axios, pandas, openpyxl …) · `FORMAT` (json, xml, csv, xlsx …) ·
`WEAK` (data, info, manager, helper, util, processor, handler, misc, item, temp) ·
`WEAK_VERB` (do, handle, process, manage, perform, execute, run, check — as the *whole* verb).

| ID | Rule | Severity |
|---|---|---|
| N1 | vendor token in an identifier outside an `infrastructure\|adapters?\|drivers?` path | **error** |
| N2 | a port / interface / `Repository` / `Store` name carries a vendor token | **error** (no exception) |
| N3 | method named `to\|from{Vendor\|Format}…` | error |
| N4 | method starts with a weak verb, or `get\|set` on a non-accessor | warn |
| N5 | identifier ends in a weak noun | warn |
| N6 | **swap test** — for each decision naming library L, any L brand token outside the adapter row | error |
| N7 | abbreviation not in the dictionary or project glossary | warn |

**Honest false positives:** `JsonSchemaValidator` when JSON *is* the domain; `HttpClient` in a
networking library; `CsvExport` when the user-facing feature is literally "export CSV". This is why
**errors are path- or type-scoped** and everything else is a **warning silenced by a one-line
justification in § 6** — the justification is the deliverable, not the silence.

### 4.5 Ambiguity elimination

**Banned outside § 1 (the prose slot):** `should` · `must be able to` · `as needed` · `as appropriate` ·
`appropriately` · `properly` · `correctly` · `robust` · `efficient` · `scalable` · `user-friendly` ·
`etc.` · `various` · `several` · `some` · `might` · `where possible` · `if necessary` · `TBD` ·
`handle … appropriately` · `make sure` · `ensure that … works`.

**Replacement obligations:**

| Instead of | Write |
|---|---|
| `should` | `MUST` / `MUST NOT` / `MAY <action> WHEN <condition>` |
| any adjective of degree | a number + unit (`fast` → `p99 < 200 ms`) |
| `etc.` | finish the list, or state the closing rule ("…and no other status codes") |
| a bullet starting `It` / `This` / `They` | name the subject |

**One counter-rule, and it matters.** Bullet fragments elide subject and modality, which is the *most*
ambiguous prose form per word — banning prose can therefore raise ambiguity while the linter reports
green. So: **every normative bullet must carry a named subject and an RFC-2119 modal.** Bullet-only
style and precision are then pulling the same direction instead of against each other.

Shape rules: H3 max · ≤ 7 `##` sections · one level of bullet nesting · ≤ 25 words per bullet ·
every bullet opens with a bolded 1–4 word key then an em-dash · lead with the answer, rationale after ·
prose ceiling 2 paragraphs of ≤ 3 sentences outside § 1.

### 4.6 Anti-padding

The failure mode of any rigid template is **hollow compliance**: an agent that cannot say something
precise emits a well-formed table of nothings, which reviews *better* than honest prose while being
worse.

- **Omit, don't stub.** A section with nothing real to say is deleted, heading included.
  `None identified` / `N/A` / `TBD` / `standard practices apply` are lint errors.
- **Two exceptions** — `## Known violations` and `## Out of scope` carry information by being empty;
  they render exactly `None.` The closed list is two entries.
- **Every bullet carries a referent** — an identifier, path, number, endpoint or proper noun.
- **No heading restatement** ("## Scope → This section describes the scope of this spec.").
- Detectors: banned-phrase list · section < 15 words with zero referents · bullet with no verb ·
  Jaccard ≥ 0.8 between two bullets · **referent-carrying bullets ÷ total bullets ≥ 0.7** (this last one
  catches padding that survives every per-bullet check).

### 4.7 Progressive disclosure — appendices at medium+

```
docs/YYYY-MM-DD-{desc}/
  YYYY-MM-DD-{desc}-business-requirements.md
  YYYY-MM-DD-{desc}-business-requirements-appendix-{topic}.md
  YYYY-MM-DD-{desc}-spec-NN-{slug}.md
  YYYY-MM-DD-{desc}-spec-NN-{slug}-appendix-{topic}.md
```

- `{topic}` ∈ `scenarios` | `evidence` | `alternatives` | `research`. Closed set. Max 3 per parent.
- **Flat siblings, deliberately** — the existing retirement rule globs `*-spec-NN-*`, so appendices are
  collected and deleted with their parent for free.
- Appendices are exempt from the word cap and inherit the parent's `satisfies:`.
- **Forbidden at trivial/low** — there, deep material is cut, not moved.
- Demotion rule — content moves to an appendix when any one holds: it is enumerable and exceeds 7 rows;
  it is *evidence* rather than *instruction*; removing it would not change what a builder types.
- **The pointer must carry the count**: `Scenarios: 14 total → see …-appendix-scenarios.md`. A bare
  "see appendix" is a lint error — the count is what tells a scanner whether to click.

---

## 5. Requirements gathering — fixing "shy"

Groups A–E are replaced by **CORE** (always) + **conditional banks** (triggered by keyword or tier).

- **CORE (6):** `PROBLEM` · `ACTORS` · `MAIN-FLOW` · `FAILURE-MODES` (what must fail gracefully) ·
  `DONE` (a number) · `NOT-DOING`.
- **Conditional banks:** `DATA-PRIVACY` · `MONEY` · `ACCESS-ROLES` · `INTEGRATION` · `VOLUME-SCALE` ·
  `RECOVERY-UNDO` · `REGULATORY` · `MIGRATION-LEGACY` · `ADOPTION-CHANGE` · `EXIT-DEPRECATION` ·
  `AUDIENCE-FORMAT` (non-code deliverables: audience, format, distribution, review chain).

| Tier | CORE | Conditional banks | Counter-positions Hercules must argue | Research |
|---|---|---|---|---|
| trivial | 6 (one message) | 0 | 0 | none |
| low | 6 (one message) | 2 auto-selected | 1 | none |
| medium | 6 | 4 | 2 (one = "do nothing / cheaper") | light |
| high | 6 | 6 | 3 | advisors + web |
| critical | 6 | all applicable | 4 + a pre-mortem | full |

**Thin-answer test** (mechanical): under 8 words · or matches
`(?i)^(yes|no|sure|whatever|any|all of them|tbd|don't know|you decide|standard)\b` · or restates the
question's nouns with no new noun · or, for `DONE`, contains no digit and no named standard.

**Push-back ladder** on a thin answer to a CORE bank:
1. Re-ask with three concrete options **and a recommended default**.
2. Offer "shall I assume X?" and log `ASSUMPTION:` into § 6.
3. A second thin answer on the same CORE bank, at **medium+**, stops the phase:
   *"I can't write requirements for this — without [X] the Flows section would be invented. Give me one
   sentence, or point me at someone who can."*

Guards on the ladder: at most **one refusal per CORE bank per session**, and a refusal always ships a
default the user can accept in one word. No `ASSUMPTION:` line may survive into a `high`/`critical`
document.

**On the tier override.** The tier is user-lowerable, so a user who finds rigour tedious can currently
opt out of it by declaring "low". Do not fight that — make it **informed**: the tier prompt must state
what lowering *drops* ("low drops the corner-case floor, the risk table, and the probe budget").

---

## 6. The feasibility gate — and the one promise that cannot be kept

### 6.1 The concession, stated plainly

> **"I never, ever want to hear that the spec turned out impossible mid-flight" cannot be delivered as
> written.** It reads as "no information discovered during implementation may invalidate the plan",
> which is the halting problem in process clothing: the only way to know a plan works is to execute it,
> at which point it is not a plan. Every probe samples the state space; passing samples cannot certify
> absence of failure.

**The honest reframe, which delivers most of the value:**

> Before approval, name the ≤ 3 assumptions whose falsity would invalidate this plan, state the cheapest
> check for each, run the checks that are cheap and possible, and record the rest as accepted risk with
> a named fallback and the build step that settles it.

The gate is **falsification, not verification.** It does not prove the plan works. It kills the plan
that *cannot* work, cheaply, before anyone reads it. That is a real and large fraction of P5.

### 6.2 Where it runs

**Design, new Step 6.5** — after the draft, **before** the coverage gate and before Plan approval. A
feasibility check that runs after the user has committed is not a gate, it is a post-mortem with better
timing.

It runs in **Design, not Discover** — deliberately. Probing requires naming modules, endpoints and
migrations; a requirements document that names those is no longer business-language. Keeping the probe
in Design resolves that conflict instead of papering over it.

### 6.3 Probe classes, in rank order

| Class | What actually runs | Proves |
|---|---|---|
| P1 Dependency existence | resolve/install the named lib at the named version in a throwaway env | it exists and installs |
| P2 Symbol / API shape | reflect on the symbol; type-check a 10-line stub against the real signature | the API has the assumed shape |
| P3 External contract | one real call to the cheapest endpoint (or fetch its OpenAPI doc) | auth works, endpoint real, field present |
| P4 Runtime capability | 15-line script: does this engine support that window function / lookbehind / syscall | the mechanism exists here |
| P5 Data reality | run the actual query against a real sample: column exists, nullability, cardinality | the data supports the requirement |
| P6 Seam probe | walk `M1` and `N1` end-to-end with **real external deps and 5-line fakes for not-yet-written internals** | the seams line up |

**Greenfield is P6's job.** If `M1` cannot be walked even with internals faked, the plan is not
deliverable — that is precisely the failure being complained about, caught for the cost of 30 lines.

### 6.4 Budgets and verdicts

| Tier | Probes | Wall-clock ceiling (`timeout`-enforced) |
|---|---|---|
| trivial | 0 (compile/lint only) | — |
| low | 1 main | 60 s |
| medium | 1 main + 1 negative | 3 min |
| high | 2 main + 2 negative | 6 min |
| critical | 2 main + 2 negative + 1 corner | 10 min |

| Verdict | Meaning | Consequence |
|---|---|---|
| **PASS** | ran, exit 0, output asserted against an expectation **stated before the run** | plan may be presented |
| **FAIL** | ran and contradicted the plan | plan is **not** presented; back to draft with the contradiction quoted |
| **UNPROVEN** | not checkable here (no credentials, no network, needs prod data) | plan may be presented **only** with the item surfaced verbatim at approval as a named risk, with an owner and the build step that settles it |

Timeout ⇒ UNPROVEN, never FAIL. A probe that needs more than its budget is telling you the assumption is
too big to check cheaply — itself a finding.

### 6.5 Anti-theatre controls

| Risk | Control |
|---|---|
| Probe that asserts nothing | **Expectation-first:** the expected observable is recorded *before* execution. No pre-stated expectation ⇒ UNPROVEN by definition, never PASS. |
| Probe that mocks the thing under question | **Mock ban at the boundary.** A probe may fake only internal, not-yet-written units. Faking the dependency, API, runtime or data the probe exists to check is an automatic FAIL. The fake list is recorded; an empty fake list on a P3/P5 probe is itself suspicious. |
| UNPROVEN as a universal escape hatch | **Capped.** > 50 % UNPROVEN at medium+, or any UNPROVEN on a high-risk surface (auth, money, data, deletion), blocks approval until the user accepts the risk in their own words. |
| "The agent says it ran" | `doc_lint.py probe record … -- <cmd>` **executes** the command and records `{label, argv, cwd, exit_code, duration_ms, stdout_sha256, head_2k, recorded_at}` into session state. The agent never types a verdict; the exit code is derived. |

**Stated limit, in the tool's own docstring:** this proves *a* command ran, not that it was the right
one. That residual is closed socially — the probe command is shown to the user before it runs.

### 6.6 Artifacts and the plan-mode conflict

- Evidence file: `docs/{session}/feasibility-probe.md` — a **rendering**; session state is authoritative.
- Probe scripts: `docs/{session}/probes/probe-{ID}.{ext}`. Retired with the spec, same rule as today's
  deletion note. Probes are evidence, never `src/`.
- **Plan mode forbids writes, and a probe must write.** The probe step is therefore declared in
  `workflow-protocol.md` as the *one sanctioned write span* in Design, confined by path to
  `docs/{session}/probes/` and the state file. Without that declaration this gate cannot run at all on
  hosts with an enforcing write hook — this is the single most important implementation detail in § 6.

### 6.7 Non-code deliverables

The gate degrades to an **artifact-generation probe**: produce one real slide, one real formula row, one
real chart, with real (or realistically shaped) data, using the actual toolchain — then check the number
in the exec summary reconciles with the source. The "impossible to deliver" failure for a deck is almost
always *the data does not say what the narrative assumes*, and that is probeable in two minutes.

---

## 7. Scenario IDs — the highest-leverage single change

`{SESSION-SLUG}:{REQ}:{CLASS}{n}`, abbreviated to `{CLASS}{n}` inside a document.

| Stage | Where the ID lives | Gate |
|---|---|---|
| Business requirements | `## Flows`, authored with QA | every requirement has ≥ 1 `M` and ≥ 1 `N`, or `scenarios: n/a` with a reason |
| Spec | `covers: [login:M1, login:N1]` beside `satisfies:` | every ID resolves to exactly one spec's `covers:`; an unowned ID is a ✗ |
| Test name | appended, greppable: `…__login_M1` / `it('… [login:M1]')` | `write-test-scenarios` step 3 |
| Build traceability | matrix keyed by ID, not by requirement section | `build.md` step 7 |

**Why this matters more than it looks.** Today's coverage gate asks an LLM reviewer to match a
requirement *paraphrase* to a spec sentence. At ~40 enumerated items and 95 % per-item accuracy, a
first-pass clean run has probability ≈ 13 % — Design would rarely reach approval, and users would learn
to answer "mark it out of scope". **ID → test is a grep.** It is deterministic, so the stochastic stall
disappears and the reviewer's judgement is spent on adequacy instead of string matching.

---

## 8. What is deterministic, and what is judgement wearing a costume

Being honest about this is what stops "all gates passed" from being read as "the document is good".

| Truly mechanical (script) | Detectable with false positives (warn + justify) | Irreducibly judgement (agent/human) |
|---|---|---|
| section set, order, nesting | ambiguity via banned words (routed around by "must, where feasible") | whether the flows are the **right** flows |
| word / item / line budgets, floors and caps | vendor-name leakage (`Session`, `Channel`, `Stream` are both generic and branded) | whether the negatives cover the real failure space |
| bullet-only shape, RFC-2119 modal present | weak-noun and weak-verb naming | whether a corner case is a corner case |
| placeholder tokens, empty sections | passive voice, sentence length | whether a rationale is a rationale or a tautology ("Strategy, because flexible") |
| `satisfies:` / `covers:` resolve to real anchors | referent ratio, Jaccard duplication | whether the design will actually work |
| every `Affected surface` path exists or is tagged NEW | | whether QA "checked" anything |
| scenario ID → named passing test (a grep) | | whether depth matches the tier |
| risk rows each paired with a mitigation | | tier correctness |
| probe recorded: argv, exit code, output hash, timing | | whether a mitigation actually mitigates |

Consequences accepted: `DOC202`/`DOC205` (ambiguity, unquantified adjectives) ship as **warnings**, not
errors — auto-rewriting them just trains authors to swap synonyms. And **QA's sign-off must name at
least one thing it changed or rejected**, or state "no changes — reviewed N scenarios, checked the N ≥ M
pairing". A bare "LGTM" is not a check.

---

## 9. Delivery plan

Ordered so the deterministic base exists before anything depends on it, and the riskiest item lands last.

| Phase | Deliverable | Touches | Done when |
|---|---|---|---|
| **0** | `doc_rules.json` + `doc_lint.py` (`check`, `template`, `rules`) + Python tests | `src/scripts/tools/`, `tests/scripts/tools/doc_lint/` | linter runs standalone on a hand-written good and bad document; no prompt changes yet |
| **1** | `document-contract` skill; ship it | 7 recipes, `dist/` ×7, 6 TS spec files | `make build-check` clean; every ecosystem ships it |
| **2** | BR standard live | `discover.md` (+1 line), template generation, question banks in the skill | Discover emits a doc that passes `doc_lint check --kind business-requirements` |
| **3** | Spec standard live | `design.md` (+1 line), profiles, naming + ambiguity rules | Design emits specs that pass `--kind spec`; commands still under their **existing** token ceilings |
| **4** | Scenario IDs threaded | `design.md` `covers:`, `write-test-scenarios`, `build.md` traceability | traceability matrix is produced by grep, not paraphrase |
| **5** | Feasibility gate | `doc_lint probe`, `design.md` Step 6.5, `workflow-protocol.md` **G9**, sanctioned write span | a plan with a false load-bearing assumption is blocked before it is shown |
| **6** | Non-code profiles | `deck` / `sheet` / `doc` profiles + worked examples | one non-code session runs end to end |

### 9.1 Budget discipline during the work

`discover.md` has 68 tokens of headroom and `design.md` has 72. **The rule for this project: commands may
not grow.** Every line added to a command is paid for by moving operational prose out of it into the
skill or the tool's failure messages. `build.md` has 6 tokens and 11 instructions of headroom — phase 4
must offset before it adds. Only `workflow-protocol.md`'s ceiling is proposed for a raise (one guardrail
row, ~15 tokens), with the reason recorded in the budget list.

### 9.2 Test surface to update

`tests/scripts/tools/test_tool_hygiene.py` (roster of shipped tools) · new `tests/scripts/tools/doc_lint/`
(each file needs a rationale docstring — `tests/repo/test_every_test_file_says_why_it_exists.py`) ·
`tests/dist/everyComponentShips.spec.ts` · `nothingIsSilentlyDropped.spec.ts` ·
`universalConformance.spec.ts` · `tests/content/skillsAndAgents/{fileShapeMatchesItsFolder,skillPromises}.spec.ts` ·
`tests/content/promptBudgets.spec.ts` · `tests/content/commands/commandPromises.spec.ts` ·
`tests/content/workflowAndProtocols/stateKeysAgreeWithTheGuard.spec.ts` · new
`documentContract.spec.ts` (template ↔ linter drift).

### 9.3 Enforcement per host, and the uniform backstop

| Ecosystem | Mechanism | Verdict |
|---|---|---|
| claude-code, grok-build | `PreToolUse`, exit 2 blocks | can block on `Write`; `Edit`/`MultiEdit` carry no full content, so fail open there |
| codex | `write_gate.json` `before_write` | blocks by path, not content |
| cursor | `afterFileEdit` | lints on disk, after the fact |
| copilot-cli, gemini-cli | hook ends `\|\| exit 0` | warn only, structurally |
| opencode | no hooks at all | nothing runs |

**Uniform backstop, because all seven ship `tools/`:** `doc_lint check --record` writes
`{path, sha256, clean, rules_version}` into session state, and `state_patch.py` / `retire_spec.py` refuse
to advance the phase when the recorded hash ≠ the file's current hash, or `clean` is false. Warn-only
hosts still hit a hard stop at the phase boundary — the same trick `frozen_tests.py` already uses.

---

## 10. Risks accepted, and decisions needed

### 10.1 Ranked residual risks

| # | Risk | Likelihood × damage | Mitigation in this plan |
|---|---|---|---|
| R1 | **Hollow compliance** — schema-satisfying filler is the cheapest passing strategy | near-certain × high | § 4.6 anti-padding, referent ratio, omit-don't-stub, floors as well as caps |
| R2 | **Abandonment** — gathering + probes push Discover past ~30 min and users go back to raw prompting | high × fatal | trivial/low stay one-message; probe budget is 0–60 s there; refusal capped at one per bank |
| R3 | **False assurance** — the first "the probe passed and it still broke" | certain eventually × severe | § 6.1 concession stated in the shipped text, not just here; UNPROVEN never silently upgraded |
| R4 | **The repo's own budgets freeze CI**, ceilings get raised, ceilings stop meaning anything | certain without discipline | § 9.1: commands may not grow; exactly one ceiling raise, with a recorded reason |
| R5 | **Linter gaming** — "must, where feasible"; "Strategy — because flexible" | high × medium | ambiguity rules ship as warnings; the `cynical-reviewer` keeps the judgement gates |
| R6 | **Truncation** — length caps eat corner cases, the content the rule existed to protect | medium-high × high | § 3.3: enumerables are item-capped, never word-capped; `N ≥ M`; appendix demotion at medium+ |

### 10.2 Decisions I need from you

| # | Decision | My recommendation |
|---|---|---|
| D1 | Accept the § 6.1 reframe (falsification, not a guarantee)? | **Yes** — the alternative is a gate that is faked or unbounded |
| D2 | Scope of the first cut | **Phases 0–3** (standard + linter + both documents), then review before the probe gate |
| D3 | Word budgets in § 3.3 — right numbers? | Ship as proposed, tune after three real sessions; they are data in `doc_rules.json`, not code |
| D4 | Blocking severity — hard-block on structure violations, or warn for a release or two? | **Block on structure, warn on style** from day one; a warning-only linter is ignored |
| D5 | Non-code profiles (phase 6) — now or later? | **Later** — but the spine ships profile-aware from phase 3 so it is not a rewrite |
