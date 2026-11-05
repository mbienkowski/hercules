# Project memory and code intelligence independent of methodology

Date: 2026-10-26. Status: business and technical proposal; the functionality is not implemented.
Baseline: Hercules `a683900e1bbcf5aa6df05e2a3cd44955a0a65228`, Codeflows `7cd95497ad09fbbb247a3f8fc5c0446b30351f00`.
This document records decisions and findings as of this date. An approved implementation specification or a later product decision supersedes it.
The implementation specification is `2026-10-26-memory-layer-spec.md` (data formats, core operations, on-disk layout, activation, fail-first tests).

## 1. Business objective

The agent should become more effective within a project by using previous decisions, user corrections, and the current code structure.
Users should repeat fewer explanations, while the agent spends less time and fewer tokens rediscovering the repository.

“Learning” means updating durable context and selecting information more accurately for a task. It does not mean training model weights.
Each new chat should use relevant knowledge from earlier chats without loading the entire history or growing the prompt after every task.

**Installation requirement:** users install Hercules and work in a repository. Memory and the code engine activate without per-repository setup.
Users do not install the engine separately, register an MCP (Model Context Protocol) server, create settings files, or initialize each project.
Only plugin installation/enabling and trust required by the AI host remain. Hercules does not bypass the host's permission mechanisms.

## 2. Problem confirmed in the source

- Capturing learnings is an instruction at Build close-out: `src/content/commands/build.md`, “Capture learnings”.
- Reading learnings and the session index happens in Discover: `src/content/commands/discover.md`, step 0.
- Delivery state supports resuming Build but does not replace memory for ordinary chats: `src/content/skills/hercules-reference/SKILL.md`.
- The inspected Codex hooks guard operations before writes: `src/content/targets/codex/hooks/hooks.json`.
- Effective capture and retrieval therefore depend on entering the relevant workflow phase and the model following its instructions.

The user's specific failed sessions have not been investigated. These findings explain an architectural gap, not every instance of lost context.

## 3. Intended user experience

1. The user installs and enables Hercules in a supported AI tool.
2. They start an ordinary chat in any local repository; running Discover is not required.
3. Hercules identifies the project, selects relevant memory, and checks code-index availability and freshness.
4. The agent finds the relevant area through the index, then reads the current source fragments needed for the task.
5. A material correction, decision, or verified finding is saved without a separate “remember this” command.
6. Interrupted work leaves a checkpoint of completed steps, evidence, and the next action.
7. A fresh chat, including one in another supported host on the same machine, uses the same project memory.

Not every chat must add an entry. A conversation without useful new knowledge does not grow memory.
Users can inspect, correct, pin, or delete an entry and disable memory. These operations are available outside the methodology phases.

## 4. Three separate kinds of context

| Layer | Contents | Source of truth and lifecycle |
|---|---|---|
| Code index | Symbols, files, dependencies, calls, locations | Rebuildable from the current checkout; refreshed after changes |
| Project memory (auto-memory) | Decisions, rationale, constraints, corrections, verified pitfalls | **Machine-local** under the project's `auto_memory_path` inside `~/.hercules/`; entries with provenance, scope, and status; updated or superseded |
| Task state | Progress, verification results, blockers, next step | Checkpoint for a specific task and worktree; replaced as work progresses |

Memory does not duplicate every function's documentation or file contents. The index answers “where and what”; memory adds “why and what to watch”.
Memory is context, not authorization to act. It cannot override the user's current instructions or project rules.

### Two stores, one promotion path

Two distinct stores, kept separate by design:

- **Committed learnings** (`docs/learnings.md`, the `learnings` skill) — human-curated, whole-project "going decisions" (architecture, design, approach). Committed to git, shared with the team, reconciled by a human at Build close-out. Unchanged by this layer.
- **Auto-memory** (`~/.hercules/memory/<slug>/`) — machine-local, auto-generated from chats, grows across chats, transparent to the user's repository. This layer's new store.

Auto-memory is the working memory; committed learnings are the curated, shared knowledge. A decision rises from one to the other only by **explicit user decision** (promotion), never by auto-capture. The path is one-way and deliberate: when auto-memory holds something worth sharing and committing, the user promotes it into `docs/learnings.md` (or `code-of-conduct.md`), and the auto-memory entry is superseded so the same fact is not held in two places.

Invariants that keep the split from leaking (tested, not noted):

- **Auto-capture writes only to auto-memory**, never to the committed store or `code-of-conduct.md`; writing to committed learnings requires an explicit user decision.
- **No double-load:** the agent reads both stores, but a promoted decision is not loaded twice; the two stores dedupe against each other by meaning.
- **Transparency:** `auto_memory_path` points at a human-readable file the user can browse, correct, pin, or delete, even though it lives outside the repository.

## 5. First-version scope

- One local project knowledge store, independent of host, model, and Hercules phases.
- Automatic context selection for the task and capture of material decisions during work.
- Bounded storage for active entries and candidates, and bounded context sent to the model.
- Separate tracking of retrieval, declared application, rejection, and correction.
- Handling of contradictions, duplicates, provenance, and changes to related code.
- Reuse of an existing code-analysis engine with automatic dependency delivery.
- Integration across all seven Hercules distributions, with automation differences disclosed and tested.
- No manual repository configuration or changes to tracked repository files to activate memory.
- Human-readable, versioned auto-memory as the canonical source of truth; the retrieval backend is a rebuildable index over it and is deferred (the first version is plain text, to validate the layer before any vector or binary backend).

Out of scope: cloud synchronization, sharing memory between users, model training, recording complete conversations,
a custom code parser, a separate web interface, a vector database, and redesigning Discover → Design → Build → Ship.
Methodology improvements are a separate task after this layer is implemented; memory integration does not change phases or approval rules.

## 6. Shared architecture and distribution builds

Preserve Hercules's architecture: shared sources, declarative recipes, generated `dist/<ecosystem>/`.

- **Memory core:** shared persistence, retrieval, selection, validation, and statistics logic in `src/scripts/tools/`.
  The canonical source of truth is human-readable, versioned, machine-parseable entries under the project's `auto_memory_path`; any retrieval store (SQLite now, FTS/vector/binary later) is a **rebuildable index** over that text, not the store itself. The first version is plain text; the backend is deferred and chosen from measurement. SQLite from the standard library handles the index and transactions with no extra service.
- **Agent instructions:** short, shared content in `src/content/`, available without starting the workflow.
- **Host integrations:** capability and packaged-file declarations in `src/targets/`; integration formats in `src/content/targets/`.
- **Hooks:** thin, shared, and based on real host events. They contain no separate memory algorithms for individual tools.
- **Code engine:** an external binary accessed through MCP or a CLI (command-line interface), with shared scope and response-size policies.
- **Build:** reproduces each distribution from its recipe; the build engine gains no branches based on host names.

Proposed minimum core operations: select context, save/supersede an entry, report use, save a checkpoint, inspect state, delete knowledge.
Command names and data formats require an implementation specification; this list describes responsibilities, not an existing API.

### Project identity and concurrency

- The default memory boundary is an automatically identified local repository, not just a directory name or remote address.
- Worktrees of the same repository share applicable project decisions but retain separate task state and indexes of their current checkouts.
- Entries tied to a specific branch or symbol have scope; they are not presented as unconditional project-wide facts.
- Two independent clones are not automatically merged. Linking several repositories into one product remains optional.
- The store lives in a private user directory under `~/.hercules/`, outside the repository and plugin installation directory.
- The registry entry carries an `auto_memory_path` pointing inside `~/.hercules/` (default-derived from the slug, stored as a field so it is visible and relocatable), linked to that project, derived the same way as `state_file`.
- Transactions plus task and entry-revision identifiers prevent lost concurrent writes and double-counted usage.

## 7. Code engine and installation without repository setup

Codeflows uses `codebase-memory-mcp`, pinned to `v0.10.8` in its `Dockerfile`; the CLI adapter is in `server/src/infra/engine/cbm.ts`.
`server/src/features/scan/repoIndex.ts` uses symbols, call relationships, and source text to answer questions during a scan.

According to [that version's documentation](https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/v0.10.8/README.md),
the engine analyzes code locally with Tree-sitter, maintains a graph, and exposes operations through MCP and CLI.
Indexing needs no model API key. Results supplied to the agent still consume its context.

### Distribution contract

- Hercules supplies the engine appropriate to the user's operating system and architecture; installing CBM separately is not a user step.
- Prefer packaging the binary and required assets, or using an installation dependency supported by the host.
- If a marketplace requires downloading the dependency, it happens automatically in the installation layer, once per version.
- Do not download executables in edit hooks or again for each repository. Do not run CBM's global installer across all hosts.
- Pin the version, platform, assets, and checksums; updates do not replace an active binary during work.
- Build and release must handle binary assets and marketplace size/format limits; the current recipes do not implement this.
- Compiling the plugin does not itself install a dependency on the recipient's computer: packaging and activation require separate verification.

Choose packaging before implementing integrations. Ordinary plugin installation must work even when CBM is absent from PATH.
Downloading requires an explicit update to network-access disclosures; bundled assets require verification of offline operation.

### First use and freshness

- The working directory identifies the repository; Hercules automatically creates its local record and selects the correct index.
- Indexing has resource limits and covers permitted files, accounting for exclusions, untracked files, and working-tree changes.
- A large first index may build in the background. The agent uses files in the meantime and does not present an unfinished graph as complete.
- Queries check the checkout, indexing state, and changes since indexing; the commit SHA alone is insufficient when local edits exist.
- Compact results identify symbols, dependencies, and source ranges. Before editing, the agent reads the relevant current code.
- A missing graph relationship does not prove there are no calls. Unsupported constructs and incomplete analysis require source inspection.
- A missing engine or indexing failure does not block coding; status explicitly identifies fallback operation instead of claiming readiness.

## 8. Differences between AI tools

CBM documentation lists native integrations with six Hercules hosts. Installation has not been tested in those hosts.

| Hercules distribution | Identified CBM access | What our integration must provide |
|---|---|---|
| Claude Code | Native MCP integration declared by CBM | Packaging, activation, and actual session context |
| Codex | Native Codex CLI integration declared by CBM | Separate verification in the app and CLI |
| Cursor | Native MCP integration declared by CBM | No assumption of reliable automatic context injection through hooks |
| Gemini CLI | Native MCP integration declared by CBM | Verified host-event input/output contracts |
| GitHub Copilot CLI | Native MCP integration declared by CBM | Verified host-event input/output contracts |
| OpenCode | Native MCP integration declared by CBM | Plugin registration or automatic CLI access |
| Grok Build | No named entry in the inspected CBM table | CLI access; native MCP needs separate confirmation |

**A shared core does not mean identical hooks.** Prefer plugin-provided MCP registration where supported.
The alternative is automatic invocation of the packaged CLI by the agent; users do not enter project-configuration commands.

Each target declares and tests tool access, initial retrieval, capture during work, and resumption after context loss.
Do not claim automatic handling of events a host does not expose. Missing automatic activation is a gap to resolve before release.

## 9. Automatic memory capture and retrieval

- **Retrieval:** when starting a task or changing its area. Load only relevant entries and the applicable checkpoint.
- **Capture:** after a material user correction, agreed decision, or verified finding. Do not wait for Build close-out or chat termination.
- **Checkpoint:** after a significant work stage or when blocked. Do not assume the host always reports window closure or a crash.
- **Meaning:** the model extracts content and rationale; the deterministic core validates format, scope, limits, and duplicates, then commits a transaction.
- **Provenance:** user correction, explicit decision, code/test evidence, or hypothesis. A hypothesis does not automatically become a standing rule.
- **Resumption:** task state contains completed steps and evidence; a new session verifies the current checkout before continuing.

**Reliable activation requirement:** telling the agent “remember to save” is insufficient as the primary activation mechanism.
A supported host event starts the shared process. Each event has an identifier and persisted processing state; repeated delivery is idempotent.
An unavailable model call or invalid extraction is not a successful save. State distinguishes startup, failure, and completion.
Retries are bounded and do not count the same events or memory applications again.
Do not promise to handle events the host never delivered or recover content lost before durable capture.

This requires explicitly changing the current read-only-hook rule: a session lifecycle adapter may invoke a tool that writes processing state and memory.
Persistence logic stays in the shared core; frozen-test guards retain their contract. The standards change must accompany implementation.
A hook alone cannot interpret decisions. The integration must also provide a supported way to pass available context to a model and receive its result,
without requiring another user API key. Do not assume every AI tool provides such a mechanism.
If a host cannot support automatic extraction, capture dependent on voluntary agent action is a limited mode,
and the target's full-automation requirement remains unmet. An existing hook or working CLI alone does not satisfy this requirement.

### Process and content repeatability

- **Process:** explicit events, identifiers, permitted state transitions, transactions, bounded retries, and visible processing outcomes.
- **Core:** identical inputs, policy version, and store state produce identical selection and validation; entry age does not change ranking.
- **Extraction:** the model receives the same compact schema for decisions, scope, and evidence. It may phrase the same information differently.
- **Reconciliation:** stable identifiers and revisions support updates; uncertain semantic equivalence does not cause silent overwrites.
- **Evaluation:** compare retained decisions, constraints, and contradictions, not identical wording. Record the model and extraction version.
- **Boundaries:** host crashes, undelivered events, and unavailable models are visible limitations, not reported successes.

## 10. Usefulness, capacity, and no age-based forgetting

### What counts as a hit

- **Retrieval:** a specific entry revision was actually supplied to the task's context.
- **Application:** the agent identified the entry and the concrete decision, change, or check where it used it.
- **Rejection:** the entry was considered irrelevant, outdated, or contradictory; record the reason.
- **Unknown:** whether the entry was applied is unknown. Do not automatically count this as success or rejection.

Deduplicate counters by task and entry revision, regardless of tool-call count or chat resumptions.
Hit rate is declared applications divided by retrievals. Report feedback coverage separately.
This is a supporting metric partly based on model declarations, not proof of a causal effect on result quality.
With small samples, do not treat a single hit as stronger evidence than repeated verification of another entry.

### Maintenance rules

- Task relevance comes first, followed by confidence and usefulness. Popularity does not surface unrelated entries.
- Explicit pinned decisions remain until revoked or a contradiction is resolved; rare use does not remove an important constraint.
- Other entries compete for space based on confirmed applications, rejections, scope, and the cost of omission.
- Candidates get an opportunity in relevant tasks. No retrievals do not prove uselessness; statistics also reflect the selection mechanism.
- Entry age and time since last use do not reduce its value. There is no automatic expiry or time-based decay.
- Related code changes trigger verification, not automatic deletion. New decisions supersede contradictory content.
- Merge duplicates. Hypotheses do not supersede explicit user decisions; unresolved contradictions remain visible.
- Limits also cover candidates, inactive entries, and usage history; do not build an unlimited conversation archive.
- If pinned memory exceeds capacity, report the need for consolidation; do not silently delete it or exceed the context budget.

The initial ranking should be simple and explainable, without a learned selection model. Measurements on real tasks determine exact limits.
Responses have a deterministic byte limit; report tokens using an available tokenizer or explicitly label them as estimates.

### Safeguards against irrelevant and outdated memory

The following identifiers are requirements to link to the specification and tests. They do not describe safeguards already implemented in code.

- **M1 — Relevance before popularity:** project, scope, and task-relevance filters run before usefulness ranking.
  A frequently used payments decision does not appear in a button-styling task merely because its hit rate is high.
- **M2 — Empty results are valid:** return no memory when no entry is relevant enough. There is no minimum entry count.
  A missing task description does not trigger a full-store read; only the applicable checkpoint and explicitly governing project context may be supplied.
- **M3 — Provenance and status:** entries identify their source, scope, revision, and basis for confidence.
  Hypotheses are not presented among governing decisions; pinning an entry cannot bypass this rule.
- **M4 — Changed evidence requires verification:** retain the version of the related source, not just its verification date.
  A changed or unavailable source excludes the entry from confirmed context until reverified.
  A matching file hash does not prove a business decision is current; check newer decisions and explicit corrections for that purpose.
- **M5 — No silent conflict resolution:** explicit corrections supersede earlier revisions; unresolved versions are not presented as consistent facts.
  Surface uncertainty in a compact conflict notice. When it affects action, the agent resolves it against current sources or with the user.
- **M6 — Application with evidence:** a usage report identifies a retrieved revision and a concrete decision, change, or check.
  The core rejects reports for unretrieved revisions and duplicates. Verifying declarations requires independent sampling.
- **M7 — Fixed budget:** the limit covers the entire tool response, including sources, selection reasons, checkpoints, and conflict notices.
  Do not cut an entry mid-sentence; omit the whole entry and report the limit. Pinning bypasses neither the budget nor scope filtering.
- **M8 — Memory directs verification:** memory authorizes no action and replaces neither current code nor the user's instructions.
  The agent checks sources relevant to the change; a memory description is not evidence of a test run in the current checkout.
- **M9 — Evaluate omissions:** evaluation includes knowledge that should be supplied and knowledge that should be withheld.
  Do not improve hit rate by avoiding new candidates or removing difficult tasks from measurement.

Semantic relevance, contradiction detection, and decision extraction cannot be fully resolved by simple validation.
Code enforces scope, permitted states, relationships, limits, and transactions; quality evaluation checks the model's interpretation.
Uncertainty or a read failure does not mean an empty, successfully searched store: results distinguish no match from unavailability.

## 11. Expected effects and measurement

| Expected effect | Mechanism | Measurement |
|---|---|---|
| Fewer tokens consumed | Narrow graph queries, memory selection, fewer repeated reads | Total task cost/tokens, including memory and all model calls |
| Better decisions | Access to rationale, constraints, and user corrections | Compliance with decisions and independent result assessment |
| Less repetition | Restoring decisions in fresh chats | Repeated explanations and repeated mistakes |
| Faster orientation | Current index and checkpoints | Time to locate the correct code and time to a correct solution |
| Adaptation alongside the project | Superseding contradictions and updating relationships | Scenarios involving changed decisions, changed code, and successive sessions |
| No growing prompt | Limits on storage and selected context | Context bytes/tokens and entry counts across a sequence of tasks |

Do not promise a percentage saving before measurement. CBM vendor benchmarks are not Hercules results.
Memory capture and retrieval can cost more than they save on a small task; improving hit rate must not compromise quality.

Compare four variants: no additions, index only, memory only, and index plus memory.
Use comparable tasks, the same model and settings, isolated stores, and separate trials with cold and warm indexes.
Balance trial order; do not carry results between variants. Include sessions after a decision changes and after code changes.
Report trial counts, median and spread of time/cost, errors, and user interventions. Missing host data means the metric is unavailable.

## 12. Security and data control

- Storage stays local. Selected memory and code fragments are passed to the model already used by the host.
- Do not promise local model processing when the user uses a remote model.
- Do not store complete transcripts, secrets, or unnecessary personal data. Secret-pattern filtering cannot provide a complete guarantee.
- Isolate repositories and tasks. A document or source comment is not automatically a trusted user instruction.
- Users can inspect an entry's source and selection reason, correct it, and delete memory together with associated statistics.
- Deleting the index does not delete project decisions. Deleting memory does not delete code or git history.
- Automatic capture does not modify project standards; promoting an entry to `code-of-conduct.md` requires an explicit user decision.

## 13. Acceptance criteria

1. A clean Hercules installation works on ordinary tasks in two successive repositories without manual CBM installation or project configuration.
2. A fresh chat retrieves a decision from the previous chat even when neither Discover nor Build close-out ran.
3. The same memory works after switching hosts on the same machine; it does not leak into an unrelated project.
4. Material corrections are saved during work; no new knowledge means no artificial entry.
5. Repeated calls and resumptions do not inflate counters; unknown application outcomes remain unknown.
6. An old but valid decision retains its value; a contradictory correction supersedes the relevant revision without retaining both as truth.
7. Rarely used pinned constraints remain available. A new candidate can be selected for a relevant task.
8. Successive chats stay within memory, candidate, usage-history, and context limits; overflow has understandable handling.
9. Checkout, branch, or uncommitted-file changes prevent an outdated index from being presented as current.
10. Concurrent sessions preserve their writes; failed transactions leave no corrupted store.
11. A missing engine, unfinished index, or unsupported language causes explicit fallback without blocking coding.
12. All seven distributions build from shared sources and pass access and activation tests appropriate to host capabilities.
13. Tests in real hosts confirm operation after installation; valid manifest JSON alone is insufficient.
14. The comparison report shows the entire mechanism's cost and solution quality, including variants that perform worse.
15. Entries with high hit rates but outside the task's area are omitted; tasks without relevant memory receive an empty result.
16. Changed evidence, hypotheses, and unresolved conflicts are excluded from confirmed memory, including for pinned entries.
17. Supplied context explains selection and provenance; the complete response fits the budget without truncating entry meaning.
18. Reports for unretrieved revisions do not increase counters; evaluation distinguishes agent declarations from verified applications.
19. Delivered events start processing without an agent choosing to invoke it; duplicates and restarts do not reprocess completed events.
20. Tests separately confirm process invocation, context access, extraction, and durable storage; failure at any stage is not overall success.
21. Repeated extraction of the same decision preserves meaning and scope; wording differences do not automatically create additional rules.
22. Auto-capture never writes the committed store; anything reaching `docs/learnings.md` or `code-of-conduct.md` came from an explicit user decision.
23. The same fact is not loaded from two stores; auto-memory and committed learnings dedupe by meaning.
24. The auto-memory canonical form is human-readable and browsable at `auto_memory_path`; the retrieval backend is a rebuildable index over it, not the store itself.

## 14. Implementation sequence and affected surfaces

1. **Verify delivery:** CBM packaging, platforms, marketplaces, and ordinary-chat activation across all hosts.
   The output is a verified capability matrix and a working installation test without repository setup, not the complete memory system.
2. **Build the shared core:** project identity, transactions, limits, selection, provenance, contradictions, and statistics.
3. **Connect chat continuity:** a compact shared agent contract, capture during work, and checkpoints; adaptations only at the host boundary.
4. **Connect the index:** repository detection, freshness, bounded queries, and fallback. Do not copy Codeflows's web stack.
5. **Integrate with the methodology:** Discover and Build use the same memory; import existing learnings without deleting their source.
6. **Measure and release:** comparative trials, host tests, distribution rebuilds, and capability-disclosure updates.

Implementation affects `src/scripts/tools/`, relevant hooks and `src/content/` instructions, all recipes and their schema,
binary-asset packaging and release, tool/host/budget tests, generated `dist/`, README, and permission disclosures.
Changing the learnings skill's role also requires reconciling the “phase-anchored” standard in `CODE_OF_CONDUCT.md`.
New data under `~/.hercules/` requires updates to storage rules and reset scope without changing what deletion of existing data means.

Key technical questions to resolve in the specification: CBM asset delivery through marketplaces,
automatic activation in each host, platforms without a suitable binary, and reliability of reported memory applications.
These are implementation and integration-test responsibilities, not additional repository-configuration steps for users.

## 15. Ensuring implementation consistency

### Contracts before implementation

- The specification assigns stable identifiers to remaining requirements and maps each to a core operation and acceptance scenario.
- Define one versioned format for entries, requests, and results. The CLI and host adapters use the same contract.
- Results distinguish valid context, no match, verification required, conflict, and error/unavailability.
  They include revision identifiers, selection reasons, and truncation/omission information without suggesting unverified completeness.
- Writes and status changes go through the core. Adapters neither modify the database directly nor implement their own ranking.
- Reads and writes verify project identity and task scope. Model-supplied data is validated as untrusted input.
- Corrections, merges, and counter updates are transactional; writes check the expected revision to avoid overwriting a newer decision.
- User data requires versioning and a store-upgrade test. An unsupported format does not justify silently resetting memory.

The implementation specification defines state representations, relevance thresholds, and limits before dependent code is written.
Do not freeze arbitrary values here or change acceptance criteria after seeing comparative test results.

### Behavior tests rather than sentence-presence tests

| Requirement | Scenario | What is checked mechanically |
|---|---|---|
| M1, M2 | Popular payments knowledge, styling task | No unrelated entry; an empty result is valid |
| M3, M4 | Hypothesis, changed or unavailable evidence | Entry is absent from confirmed context |
| M5 | Conflicting decisions and an explicit correction | No two governing versions; correct conflict and supersession handling |
| M6 | Two reports and a report for an unretrieved revision | One valid application counted; unretrieved revision not counted |
| M7 | Excess entries, large checkpoint, pinned entry | Entire response stays within budget; no partial entries |
| M8 | Memory describes code before a local edit | Verification-required status; agent test checks actual reading of current code |
| M9 | Dataset with hits and deliberately irrelevant knowledge | Report includes omissions and irrelevant retrievals, not just hit rate |
| Isolation | Two repositories with the same name and two worktrees | Separate projects and checkpoints with appropriate sharing of decisions |
| Durability | Concurrent corrections, interrupted write, restart | No loss of committed writes, database corruption, or silent overwrite |

Core scenarios are written before implementation and initially fail because the required behavior is missing.
The same dataset passes through the core, CLI, and available adapters; compare result semantics after excluding transport metadata.
Semantic tests define the expected decision and forbidden memory use in advance; the solution author's declaration alone is insufficient.

### Evidence for distributions and release

- Build checks recipes, asset completeness, shared-core consistency, and absence of drift in generated `dist/`.
- Each of the seven targets passes an ordinary-task test after a clean installation, without CBM on PATH or repository configuration.
- Fresh-chat tests inspect context actually supplied to the model and data actually persisted, not just a “remembered” message.
- Each adapter reads and writes the shared format; an additional cross-host test verifies retrieval of the same decision.
- Also test plugin upgrades, unavailable binaries, unfinished indexes, and restarting interrupted work.
- The host/OS/architecture matrix distinguishes verified, unsupported, and untested combinations. Missing tests do not become passing results.
- Reports link requirements, tests, and results. Failed installation or continuity requirements block claims of full support for that target.
- Release also requires evaluating quality and total cost across the four variants in section 11; passing core tests does not prove savings.

The document and requirements matrix are reviewed whenever scope changes. A deliberate change to an assumption updates its requirement and test,
rather than retrofitting the description to accidental implementation behavior.
