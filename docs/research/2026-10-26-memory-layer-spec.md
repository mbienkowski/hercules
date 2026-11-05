# Memory layer — implementation specification

Date: 2026-10-26. Status: implementation specification, not yet coded. The write-capable lifecycle hook (the one standards change in §7) is **approved** 2026-10-26.
Supersedes: the "not implemented" design portions of
`2026-10-26-project-memory-and-code-intelligence.md` (the **research doc**, source of truth for
decisions). This document pins **contracts** — data formats, core operations, on-disk layout,
activation, and the fail-first tests — before dependent code is written, per research doc §15
("contracts before implementation"). It does **not** freeze arbitrary numeric limits; limits are
named constants with rationale, and exact values are fixed by the §11 measurement, not here.

Locked decisions carried in: memory is separated from methodology; the four phases and approval
rules are untouched; two stores with a one-way promotion path; canonical human-readable `.md` first,
retrieval backend deferred; no time-based decay; detect-and-degrade code engine; no per-repo config.

---

## 1. What this spec covers, and what it deliberately does not

In scope (first version):

- One machine-local, host-independent project **auto-memory** store, activated without per-repo setup.
- **Six core operations** plus extraction and promotion, as thin shared CLI tools.
- One **versioned** entry / request / result format shared by the CLI and every host adapter.
- **Automatic, host-event-driven activation** of capture and retrieval, with per-host capability
  honestly disclosed; capture that depends on the agent choosing to run is a named **limited mode**,
  not full automation.
- **Detection-and-degrade** use of `codebase-memory-mcp` (CBM) as the code engine; no binary bundling.
- The single **standards change** required: a write-capable **session-lifecycle** hook kind, gated so
  it can write only under `~/.hercules/memory/`, never the repo, committed learnings, or code-of-conduct.

Out of scope (unchanged from research doc §5): cloud sync, cross-user sharing, model training, full
transcripts, a custom parser, a web UI, a vector/binary retrieval backend, and any change to the
Discover→Design→Build→Ship phases or their approval gates. Methodology improvements are a later task.

---

## 2. Two stores, one promotion path (recap, binding)

- **Committed learnings** — `docs/learnings.md` + the `learnings` skill. Human-curated, committed,
  shared; reconciled by a human at Build close-out. **Unchanged** by this layer.
- **Auto-memory** — `~/.hercules/memory/<slug>/`, machine-local, auto-generated, grows across chats.
  **This layer's new store.**

A decision rises auto→committed only by **explicit user decision** (`promote`), never by auto-capture.
Invariants, all enforced in code and covered by tests in §10:

- **I1** — auto-capture writes **only** auto-memory; anything reaching `docs/learnings.md` or
  `code-of-conduct.md` came from an explicit `promote` call (AC 22).
- **I2** — no double-load: the two stores dedupe by meaning; a promoted entry is not loaded twice
  (AC 23).
- **I3** — transparency: `auto_memory_path` points at a human-readable, browsable, correctable,
  deletable file, even though it lives outside the repo (AC 24).

---

## 3. Versioned data formats

Every format carries a `format_version` integer. A reader that meets an unknown version does **not**
silently reset the store: it emits a `store-upgrade-required` result and the upgrade path is a tested
migration (§11.4), never an implicit wipe (research doc §15 "an unsupported format does not justify
silently resetting memory").

### 3.1 Entry (the unit of auto-memory)

```jsonc
{
  "format_version": 1,
  "id": "stable-uuid",            // assigned on first capture, never changes; basis for in-place supersession
  "revision": 3,                  // monotonic per id; a correction writes revision+1, not a new id
  "slug": "acme-payments",        // project, resolved by the registry — NOT model-supplied
  "scope": "project",             // project | branch:<name> | symbol:<ref> | worktree:<id> | task:<id>
  "kind": "decision",            // decision | correction | constraint | verified-finding | hypothesis
  "statement": "writes are async; sync writes deadlock under load",  // present-tense standing rule
  "rationale": "the 2026-09 load test showed sync writers block the pool",
  "evidence": {
    "basis": "code-test",        // user-correction | explicit-decision | code-test | hypothesis
    "source": "load-test-2026-09",
    "refs": [
      {"kind": "file", "ref": "src/writer.py", "hash": "sha256:…"},
      {"kind": "commit", "ref": "a683900"}
    ]
  },
  "provenance": {
    "captured_by": "extraction", // extraction | user-promotion | manual
    "extraction_model": "…",
    "extraction_version": 1,
    "captured_at": "2026-10-26T12:00:00Z"
  },
  "status": "active",            // active | superseded | pending-verification
  "supersedes": [{"id": "…", "revision": 2}],
  "superseded_by": null,
  "pinned": false,
  "related_code_version": "a683900"   // the checkout the evidence referred to; drives M4 re-verification
}
```

Rules:

- `kind=hypothesis` is **never** presented as governing (M3). A `decision`/`correction`/`constraint`
  with `evidence.basis=hypothesis` is a validation error.
- `scope != project` entries are never presented project-wide (M1/M3).
- `supersede` never deletes: the old revision keeps `status=superseded` with `superseded_by`; git and
  the entry history carry "we changed our mind" (research doc §4).
- A correction writes the **same `id`** at `revision+1`; it does not allocate a new id.

### 3.2 Request

```jsonc
{
  "format_version": 1,
  "command": "select_context",
  "project": "acme-payments",     // resolved by the registry from cwd; model-supplied value is untrusted and re-resolved
  "task": {"task_id": "…", "worktree": "…"},
  "query": "fix the async writer deadlock",   // model-supplied, treated as untrusted input
  "layers": ["auto-memory", "committed-learnings", "checkpoint"],
  "budget": {"tokens": 4096},
  "policy_version": "policy-1",
  "include_hypotheses": false
}
```

The registry re-resolves `project` from the host's working directory; a model-supplied `slug` is
accepted only if it matches the resolved one, else the request is refused (model input is untrusted,
research doc §15).

### 3.3 Result

```jsonc
{
  "format_version": 1,
  "status": "ok",              // ok | no-match | verification-required | conflict | error | unavailable
  "policy_version": "policy-1",
  "index_version": 7,
  "entries": [
    {
      "id": "…", "revision": 3,
      "statement": "…", "rationale": "…",
      "scope": "project", "kind": "decision",
      "evidence_summary": "code-test, src/writer.py@a683900",
      "selection_reason": "matches query area: async writer; relevance 0.91, confidence high"
    }
  ],
  "conflicts": [
    {"id_a": "…", "id_b": "…", "note": "two governing versions; explicit correction supersedes"}
  ],
  "checkpoint": null,          // task state when the layer is requested, else null
  "sources": ["auto-memory/acme-payments"],
  "truncation": {"omitted": 2, "reason": "budget"},
  "notes": []                  // e.g. "index stale since 3 local commits" — never implies completeness
}
```

Result semantics (research doc §15, §10): `no-match` and `unavailable` are **distinct** — a read
failure or empty-but-healthy store are not conflated. `status=ok` never claims the search was
exhaustive of the codebase; a missing graph edge is not proof of absence.

---

## 4. Core operations

All persistence goes through the shared core (`src/scripts/tools/memory_core.py`), the `registry_sync`
/ `state_patch` pattern: argparse subcommands, fixed exit codes, fail-closed `Internal`, atomic
writes via same-dir temp + fsync + `os.replace`, read-back verification, and a single JSON shape on
stdout for **every** path including refusals. Host hooks and the CLI are thin; they call the core and
never rank, merge, or touch the store directly (research doc §15 "writes go through the core").

| # | Operation | Signature | Read/Write | Enforces |
|---|---|---|---|---|
| C1 | `select_context` | `request → result` | read | M1, M2, M3, M4, M5, M7 |
| C2 | `save_or_supersede` | `entry → {id, revision}` | write | M3, M5, M21 |
| C3 | `report_usage` | `report → {counted, rejected}` | write | M6 |
| C4 | `save_checkpoint` | `task_state → {rev}` | write | task state |
| C5 | `inspect_state` | `query → listing` | read | I3, transparency |
| C6 | `delete_knowledge` | `id \| task → …` | write | I1, data control |
| — | `capture` (model-driven) | `extraction → C2` | write | M3, M4 |
| — | `promote` (explicit only) | `id → committed-entry` | write | I1, AC22 |

### C1 select_context — retrieval + selection + ranking

1. Resolve `project` from cwd via the registry; re-resolve, do not trust the request's `slug`.
2. Filter by project, then scope, then task relevance **before** any usefulness ranking (M1).
3. Rank survivors by relevance → confidence → usefulness. Popularity **never** surfaces an unrelated
   entry (M1). No minimum entry count; zero relevant entries yields `status=no-match` (M2) — a missing
   `query` does **not** trigger a full-store read, only the applicable checkpoint and explicitly
   governing project context may be supplied.
4. Drop, from *confirmed* context: `hypothesis` entries (M3), entries whose `related_code_version` no
   longer matches a source hash (M4 → `verification-required`, not deletion), and one side of an
   unresolved contradiction (M5). Pinned entries are not exempt from scope, status, or budget filtering.
5. Apply the fixed response budget over the **entire** response — entries, sources, selection reasons,
   checkpoint, conflict notices. On overflow, omit the **whole** lowest-priority entry and report it in
   `truncation`; never cut an entry mid-sentence (M7).
6. Dedupe against committed learnings by meaning so a promoted fact is not loaded from both stores
   (I2, AC23).

### C2 save_or_supersede — capture / merge / supersede

- Transactional. The caller passes `expected_revision` (or absent for a new id); the write proceeds only
  if the stored revision matches, else it fails rather than clobbering a newer decision (optimistic
  concurrency, research doc §15).
- Reconcile by meaning: a near-duplicate updates in place (same id, `revision+1`) instead of stacking
  (M21); a contradicting correction supersedes the old revision (`status=superseded`, `superseded_by`
  set), never leaving two governing versions (M5).
- Validates `kind`/`evidence.basis` consistency, `scope` legality, and secrets/PII before writing.
- Writes only under `auto_memory_path` (I1).

### C3 report_usage

- A report names a **retrieved** `id`+`revision` and a concrete decision/change/check it was applied to.
- The core rejects reports for revisions that were never retrieved and dedupes by `task`+`entry-revision`
  regardless of tool-call count or chat resumptions (M6, AC5). Unknown application outcomes stay
  unknown — not auto-counted as success or rejection.

### C4 save_checkpoint / C5 inspect_state / C6 delete_knowledge

- C4 writes task state (completed steps, evidence, blockers, next action) keyed by `task`+`worktree`;
  a resumed task **re-verifies the current checkout** before continuing (research doc §9).
- C5 is the transparency surface: list, show, correct, pin, delete — available outside the phases.
  `delete_knowledge` never cascades into the repo, git history, or the committed store (research doc §12).

### capture (model-driven extraction, the non-deterministic half)

The model extracts a compact `(statement, rationale, scope, evidence, basis)` from the event and calls
`save_or_supersede`. The **deterministic** core validates format, scope, basis, secrets, and
duplicates and commits the transaction; the model only supplies content and rationale. Extraction
failure is **not** a successful save (research doc §9).

### promote (the only auto→committed path)

Explicit user call only. Copies the entry into the committed store (the `learnings` reconcile path),
sets `superseded_by` so auto-memory stops re-loading it (I2), and requires the same reconcile/secret
discipline as the `learnings` skill. Auto-capture can never reach the committed store (I1, AC22).

---

## 5. On-disk layout and state

`auto_memory_path` is `~/.hercules/memory/<slug>/`, stored as a field on the registry project entry
(next to `state_file`), **default-derived from the slug** and relocatable — no per-repo config,
activation needs only plugin install + host trust (research doc §6, §1).

```
~/.hercules/memory/<slug>/
  entries.md        # canonical source of truth: human-readable, one section per entry,
                    #   each with a machine-parseable block (id, revision, scope, kind, basis, refs)
  index.db          # rebuildable FTS5 search index over entries.md (stdlib sqlite3); vector/binary later
  stats.json        # authoritative usage counters per id+revision — NOT rebuildable; survives index rebuilds
  checkpoints/      # task state per task+worktree
  processing.json   # idempotent-event state: seen event ids, last processed, per-event status
```

Two distinct kinds of on-disk state, kept separate on purpose:

- **Canonical store** = `entries.md` (human-readable) + `stats.json` (machine counters). This is the
  store of record. `stats` is **not** derivable from `entries.md`, so it is not "rebuildable" — the
  "rebuildable index" phrase in the research doc means the **search** index (`index.db`), not the
  counters.
- **Search index** = `index.db`, rebuilt from `entries.md` at any time; loss is not data loss.

The registry entry gains `auto_memory_path`; a new project's first `capture` creates the tree
(create-or-update), mirroring the `state_file` default. `project_reset` and reset-scope tests are
extended to include this tree without changing what deletion of **existing** data means (research doc
§14 "New data under ~/.hercules/ requires updates to storage rules and reset scope").

Transactions: `atomic_write_json`-style (same-dir temp + fsync + `os.replace`) with a per-slug lock so
concurrent sessions preserve their writes and a failed transaction leaves no corrupted store (AC10).
`entry`+`revision` and `task` ids prevent lost writes and double-counted usage.

---

## 6. Project identity and concurrency

- Default boundary = the **automatically identified local repository** via the registry, not a
  directory name or remote (research doc §6).
- Worktrees of one repo **share applicable project decisions** but keep **separate** task state and
  per-checkout indexes (AC3 isolation + sharing).
- Entries tied to a branch/symbol/worktree carry that `scope`; they are not project-wide facts.
- Two independent clones are **not** auto-merged; linking repos is optional.

---

## 7. Activation — the one standards change

Today every hook in `src/scripts/hooks/` is a **read-only guardrail** (the `write_gate` denies/allows
a write; `frozen_tests` blocks frozen edits). To auto-capture we need a **write-capable
session-lifecycle hook** — a new hook kind. This is the single deliberate change to the LOCKED
"Hooks" standard in `CODE_OF_CONDUCT.md`; it is disclosed, not hidden.

**Decision — approved 2026-10-26.** The user approved the write-capable lifecycle hook. The
justification, stated precisely so it cannot later be misread: the LOCKED "read-only over
`~/.hercules`" rule exists **because a hook writing state would race the model's atomic writes**
(`CODE_OF_CONDUCT.md` § Hooks, "Read-only over `~/.hercules`, fail-open"), **not** because hooks are
forbidden from touching `~/.hercules/`. A memory hook is safe *and* consistent with that rule when:

- it writes **only** to the memory subtree `~/.hercules/memory/<slug>/` — a different subtree from
  `~/.hercules/config.json` and `~/.hercules/state/<slug>.json`, which are `registry_sync`'s and
  `state_patch`'s domain. No two writers own the same file, so there is no unmanaged race.
- every memory write routes through the **same** shared core (`memory_core.py`) with the **same**
  per-slug lock + atomic `os.replace` + revision-check discipline the model-invoked tools use, so a
  hook-triggered write and a model-triggered write **serialize** rather than interleave.

The change is therefore "permit a new sanctioned write kind, gated and serialized like the existing
tool writes," not "let hooks write freely to `~/.hercules/`." The locked invariants the change keeps
are:

- Hooks stay **Python, stdlib-only, byte-copied to every ecosystem** (unchanged): the lifecycle hook
  is *thin* — it resolves the project, reads the event, and invokes the **shared core tool**; it
  contains **no memory algorithm** (research doc §6 "hooks contain no separate memory algorithms").
- The **frozen-test guards keep their contract** untouched.
- The **new write kind is gated** by a per-host `hooks/memory_gate.json` (a `writeGate`-class dialect,
  validated against the recipe schema like `write_gate.json`) that restricts what the lifecycle hook
  may write to **roots under `~/.hercules/memory/` only**. A path outside that root — including the
  repo, `docs/learnings.md`, or `code-of-conduct.md` — is refused in code via the existing
  `is_within` / `is_strict_descendant` tools. This is how **I1** (auto-capture never writes the
  committed store) is enforced by code, not prose.
- The **no-race invariant** is enforced, not assumed: the `memory_gate` root is the *only* writable
  subtree, and it is disjoint from `config.json`/`state/`, so a hook write and a model write never
  target the same file; within `memory/<slug>/` the per-slug lock serializes the two writer kinds.
- Superseded: containment is enforced in memory_core.py; no memory_gate.json ships.

### 7.1 The activation contract (per host)

For each of the seven targets, a thin `lifecycle` adapter fires on a host event the host **actually
exposes** and calls the core. The adapter must not assume an event the host does not deliver. The
capability each target claims is **verified by an integration test**, not asserted from CBM's table
(research doc §8 "a shared core does not mean identical hooks").

- **Retrieval:** on task start / area change → `select_context` → supply the result.
- **Capture:** after a material correction, agreed decision, or verified finding → `capture` →
  `save_or_supersede`. **During work**, not only at Build close-out or chat end.
- **Checkpoint:** after a significant stage or when blocked → `save_checkpoint`.
- Each event has an **id** and **persisted processing state** (`processing.json`); repeated delivery is
  **idempotent**; state distinguishes `startup | failure | complete`; retries are bounded and do not
  re-count the same events or applications (research doc §9, AC19, AC5).

**Limited mode, honestly disclosed:** where a host exposes **no write-capable event** (CBM already
withholds some hooks, e.g. it discards stdout for Cursor and Grok Build), capture depends on voluntary
agent action. That target's **full-automation requirement is unmet**; it is reported as a gap, not
claimed. A working hook or CLI alone does not satisfy full automation (research doc §9). The
capability matrix (verified / limited / untested) ships per target; a failed activation test blocks a
"fully supported" claim for that target (research doc §13, §15).

### 7.2 The write capability, without a second API key

The integration provides a supported way to pass available context to **the model already in use** and
receive its extraction, without requiring another user API key (research doc §9). A host that cannot
supply this falls to limited mode.

---

## 8. Code engine — detection and degrade

The engine is `codebase-memory-mcp` (DeusData, pinned `v0.10.8` per Codeflows). It is the
code-intelligence layer the proposal wanted: native per-OS/arch binary, 158 languages, tree-sitter +
hybrid LSP, 15 MCP tools, no language runtime or API key; its `install` auto-configures 43+ client
surfaces.

**Detect-and-degrade** (decision 2a). Hercules does **not** become a binary packager (no binary-asset
mechanism exists in the recipe renderer today, research doc §7):

1. If `codebase-memory-mcp` is on `PATH` (or once auto-installed at the install layer), use it for
   bounded queries.
2. Otherwise **fall back to reading files directly** and say so explicitly; **never block coding**
   (AC11, research doc §7 "a missing engine does not block coding").
3. No download in an edit hook, no per-repo download, no global `install` across all hosts.

**First use / freshness:** the cwd identifies the repo and selects the index; a large first index may
build in the background and is **not** presented as complete; a query checks checkout + index state +
changes since indexing — **commit SHA alone is insufficient when local edits exist**; a missing graph
edge is not proof of no call; before editing, the agent reads the current source fragments (M8, AC9).

**Limitation to record:** CBM withholds some per-host hooks, so full automatic code-index activation is
not uniform across all seven hosts — disclosed per target, like the capture matrix.

---

## 9. Safeguards M1–M9 as testable invariants

Each is a core behavior with a failing test in §10. They guard the user's central risk — supplying
irrelevant or stale memory that costs tokens and worsens decisions.

- **M1** relevance before popularity; project+scope+task filters precede usefulness ranking.
- **M2** empty results are valid; no minimum count; missing query ≠ full-store read.
- **M3** provenance+status: `hypothesis` never in confirmed context; pinning cannot bypass this.
- **M4** changed evidence re-verifies: retain `related_code_version`; a changed/unavailable source
  excludes the entry from *confirmed* context (→ `verification-required`), not auto-delete; a file
  hash match does not prove a decision is current (check newer decisions/corrections too).
- **M5** no silent conflict resolution; an explicit correction supersedes; unresolved versions stay
  visible via a compact `conflicts` notice; the agent resolves against current sources or the user.
- **M6** application-with-evidence: report names a retrieved revision + concrete use; core rejects
  unretrieved-revision reports and dedupes by task+revision; verify by independent sampling.
- **M7** fixed budget over the **whole** response; omit whole entries, never mid-sentence; pinning
  bypasses neither budget nor scope.
- **M8** memory authorizes no action and replaces neither current code nor user instructions; a memory
  description is not evidence of a test run in the current checkout.
- **M9** evaluate omissions, not just hit rate; do not inflate hit rate by avoiding candidates or
  dropping hard tasks.

**No time-based decay** (research doc §10): ranking is relevance → confidence → usefulness; an old but
valid decision keeps its value; pinned decisions never expire by age; rare use does not drop an
important constraint; related-code change triggers **verification, not deletion**; limits also bound
candidates, inactive entries, and usage history — no unlimited conversation archive.

---

## 10. Behavior tests (fail first)

Written **before** the core, each initially red because the behavior is absent, each mapped to a
requirement and (from §13) to an acceptance criterion. The same dataset passes through the core, the
CLI, and the available adapters; results are compared by **semantics** after excluding transport
metadata (research doc §15).

| ID | Scenario | Requirement | Checks | AC |
|---|---|---|---|---|
| T1 | popular payments entry, styling query | M1, M2 | no unrelated entry; empty result valid | 15 |
| T2 | hypothesis + changed/unavailable evidence | M3, M4 | absent from confirmed context | 16 |
| T3 | conflicting decisions + explicit correction | M5 | one governing version; correct supersede | 6 |
| T4 | two reports + a report for an unretrieved revision | M6 | one application counted; unretrieved not counted | 5, 18 |
| T5 | excess entries + large checkpoint + pinned entry | M7 | whole response within budget; no partial entries | 8, 17 |
| T6 | memory describes code before a local edit | M8 | `verification-required`; agent reads current code | 17 |
| T7 | dataset with hits + deliberately irrelevant knowledge | M9 | report includes omissions and irrelevant retrievals | 14 |
| T8 | two repos, same name; two worktrees | isolation | separate projects/checkpoints, shared decisions | 3 |
| T9 | concurrent corrections + interrupted write + restart | durability | no lost write, no corruption, no silent overwrite | 10 |
| T10 | auto-capture reaches committed store | I1 | refused; only `promote` writes committed | 22 |
| T11 | same fact in both stores | I2 | loaded once, deduped by meaning | 23 |
| T12 | browse `auto_memory_path` | I3 | human-readable file present and correctable | 24 |
| T13 | repeat extraction of one decision | M21 | same id, revision+1, no new rule | 21 |
| T14 | same event delivered twice | idempotency | processed once; counters not doubled | 19 |
| T15 | fresh chat, no Discover/Build ran | capture+retrieve | decision from prior chat retrieved | 2 |
| T16 | clean install, two repos, no CBM on PATH | degrade | works via file fallback, no per-repo config | 1, 11 |
| T17 | store-upgrade: unknown `format_version` | migration | `store-upgrade-required`, no silent reset | 13 |

Semantic tests state the **expected decision and the forbidden memory use in advance**; the author's
declaration alone is insufficient (research doc §15).

---

## 11. Determinism, limits, and migration

### 11.1 Determinism boundaries (as the user specified)

- **Process reliably fires** — activation is driven by explicit host events with id, permitted
  transitions, transactions, bounded retries, and visible `startup|failure|complete` state; this half
  is deterministic (AC19).
- **Results need not be byte-identical.** Given the same inputs + `policy_version` + store state, the
  **core** selection and validation are deterministic (entry age never affects ranking). **Extraction**
  is non-deterministic; reconciliation by stable `id`+`revision` prevents duplicate rules; evaluation
  compares **meaning**, not wording.
- The near-identical outcome the user wants follows from deterministic core + idempotent events +
  meaning-based eval, **not** from byte-identical extraction.

### 11.2 Limits (named, not frozen)

Named constants with rationale, fixed by the §11 measurement, not by this spec: response budget
(default token cap), active-entry cap, candidate cap, usage-history cap, and retrieval top-k. No
numeric value is frozen here (research doc §15 "do not freeze arbitrary values"). The ranking is a
simple, explainable function — **no learned selection model**.

### 11.3 Measurement (research doc §11)

No percentage is promised before measurement; CBM's vendor benchmarks are not Hercules results.
Compare four variants — **none / index-only / memory-only / both** — on comparable tasks, same model
and settings, isolated stores, separate cold/warm trials, balanced order, including sessions after a
decision or code change. Report trial counts, median/spread of time and **total** cost (all model
calls, including memory), errors, and interventions. A worse variant is reported.

### 11.4 Migration

`format_version` + a tested store-upgrade path. An unsupported version emits
`store-upgrade-required` and never silently resets (T17, AC13).

---

## 12. Acceptance-criterion traceability (research doc §13)

| AC | Satisfied by |
|---|---|
| 1, 11 | §8 degrade + T16 |
| 2 | §7 capture/retrieve + T15 |
| 3 | §6 identity + T8 |
| 4 | §7 "no new knowledge ⇒ no entry" |
| 5, 18 | C3 / M6 + T4 |
| 6 | C2 supersede + T3 |
| 7 | §9 no-decay + T8 |
| 8, 17 | C1 budget/M7 + T5 |
| 9 | §8 freshness + T6 |
| 10 | §5 transactions + T9 |
| 12, 13 | §7.1 per-host tests + T17 |
| 14 | §11.3 measurement + T7 |
| 15 | M1/M2 + T1 |
| 16 | M3/M4 + T2 |
| 19 | §7.1 idempotency + T14 |
| 20 | §10 staged tests (activation/context/extraction/durable separately) |
| 21 | C2 + T13 |
| 22 | I1 + T10 |
| 23 | I2 + T11 |
| 24 | I3 + T12 |

---

## 13. Implementation sequence and affected surfaces

Sequence (research doc §14): (1) verify delivery/capability matrix across hosts — output is a verified
matrix + an install test **without** per-repo config, not the full system; (2) build the shared core
(C1–C6, transactions, limits, selection, provenance, contradictions, stats); (3) connect chat
continuity — a compact shared agent contract, capture during work, checkpoints, host-boundary
adapters; (4) connect the index — repo detection, freshness, bounded queries, degrade; (5) integrate
with the methodology — Discover and Build use the same memory; import existing `docs/learnings.md`
**without deleting its source**; (6) measure (four variants) and release.

Affected surfaces:

- `src/scripts/tools/memory_core.py` (new, stdlib-only) + `src/scripts/tools/` identity helpers
  (`is_within`, `is_strict_descendant`, `canon`, `load_registry` reused).
- `src/scripts/hooks/` thin `lifecycle` adapters (stdlib, byte-copied) + per-host
  `hooks/memory_gate.json` dialects (schema-validated).
- `src/content/` a short shared agent contract available **without** starting the workflow.
- `src/targets/*.json` recipes for all seven + `recipe.schema.json#/$defs/writeGate`-class `memoryGate`.
- `CODE_OF_CONDUCT.md` the one standards change (the write-capable lifecycle hook), **approved** 2026-10-26 and scoped to the `memory/` subtree, serialized like existing tool writes; `learnings`
  skill's "phase-anchored" role reconciled with auto-memory capture; `project_reset.py` + reset-scope
  tests extended to the new tree.
- Registry `config.json` gains `auto_memory_path` per project (default-derived from slug).
- Tool / host / budget tests, generated `dist/` (build-check: byte + permission bits), README, and
  permission/disclosure updates (network access for one-time CBM install, if used).

**Open questions for the spec author (implementation, not user config):** per-host write-capable
event surface (verified, not assumed); CBM delivery through each marketplace; platforms without a
suitable binary; reliability of reported memory applications (sampling, M6).

---

## 14. Security and data control (binding, from research doc §12)

Storage is local; selected memory and code fragments go to the model the host already uses; no promise
of local-model processing when the user uses a remote model. No full transcripts, secrets, or
unnecessary PII; secret-pattern filtering is not a complete guarantee. Repos and tasks are isolated; a
document or source comment is **not** automatically a trusted user instruction. Users inspect an entry's
source and selection reason, correct it, and delete memory with its stats. Deleting the index does not
delete decisions; deleting memory does not delete code or git history. Auto-capture never modifies
project standards; promotion to `code-of-conduct.md` needs an explicit user decision (I1).
