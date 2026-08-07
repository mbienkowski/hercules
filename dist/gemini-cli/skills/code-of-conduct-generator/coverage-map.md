# Coverage map — code-of-conduct generator (internal scan aid, not CoC output)

The generator drafts **evidence-first**, then runs this map ONCE as a **gap detector**: for each
applicable point not already covered by a drafted rule, if load-bearing, recommend it in chat —
accept makes it a rule, decline drops it. Never emit a point without repo evidence or an explicit
user yes.

**Tiers:** `P0` every serious repo · `P1` most repos · `P2` situational · `P3` emerging.
**Stack flags:** `[be]` backend · `[fe]` frontend · `[mobile]` · `[data]` · `[ml]` · `[infra]` · `[ai]`.
Load only the groups whose stack the scan detected; always load A–D, H–L, Q–V, Z, AB.
**Sources:** backbone points cite a primary standard; `(conv)` = established convention, not a cited spec.
Each point: `name [tier][stack] — scan signal → rule shape.`

## § Scan playbook (SKILL Step 3 runs `coc_scan.py`; this is what the tool cannot decide)

The tool reports what the repo declares, what its history shows, and which directories are still
worked on. It resolves under a fifth of the points below; the rest is yours:

- **Read from `liveness.top_files`, never the tree** — take ~20–30 from its head and name the
  design patterns, test conventions and idioms in them; it is ranked because alive code is the
  standard.
- **`arch.families` is the only architectural fact the scan states** — a directory several files
  share a suffix in, which is one way this repository grows. It needs no allowlist of suffixes and
  therefore misses nothing: a family of `.tf`, `.proto` or `.sql` counts exactly as much as code.
- **Everything else about the architecture is yours to extract** — see § Architecture extractor.
  The tool learned no languages on purpose: a catalogue is forever behind the repository in front
  of you, and the one that shipped here reported its own coverage as complete while missing the two
  commonest layouts of a language it claimed.
- **Record each further confirmed reading as an observation** `{id, path}`. An observation is as
  citable as a validated fact — the gate accepts `code:<id>` for ids the envelope carries, the
  linter holds each path against HEAD. A pattern with no file to show is a question, not evidence.
- **Weigh by `status`** — `alive` is what the repo converges on; `cooling` is current, not
  frontier; `dormant` describes what nobody maintains, so rules from it bind work nobody does.
  A `generated: true` directory states nothing.
- **Reconcile config against code** — a rule the config states but the code visibly violates is a
  Step-4 question, never an enforced rule.
- **Two live patterns for one concern → a question, never majority rule.** Report both in the
  extractor's `conventions` and name no winner; neither do you — a pattern is edited while being
  adopted and while being torn out.
- **Anything marked `unknown`, or not locally observable** — branch protection, required reviewers,
  self-merge policy live in the forge, not the repo — is a Step-4 question.
- **Determinism & resume** — the document is byte-identical per commit; a fixed question order
  carries the rest. Plan mode blocks writes, so hold results in memory; after the write step the
  draft, answers and mode persist to `~/.hercules/state/{slug}-coc.json`.

## § Architecture extractor (SKILL Step 3b writes it; `coc_scan.py extract` runs and judges it)

The scan states no architecture beyond families, because a tool that knew languages would be a
catalogue forever behind the repository in front of you. You know the language. Write a small
extractor FOR THIS REPOSITORY, and hand it to `extract` to be run under a bound.

You do not run it yourself. `coc_scan.py extract --root <root> --extractor <script>` spawns it with
a deadline, a cap on what it may print, and — on POSIX — a kill that takes down anything it started,
because a plain timeout leaves a grandchild running under init. It never reads your script, only
runs it: deciding in advance whether a regex can backtrack catastrophically is undecidable, so the
answer is a bound around the program, not a prediction about it.

    read the tracked file list and the ranked sample
    decide, from the files themselves, how this language states a dependency
    for each source file:
        find the references it makes to other files IN THIS REPOSITORY
        resolve each to a tracked path, or drop it — never guess
    aggregate:
        areas        the directories the work actually divides into, and what each is for
        edges        which area depends on which, and how heavily
        chokepoints  the files or directories many others reference
        entrypoints  where execution starts, however this stack starts it
        conventions  a concern done two ways, with each side's file count and an example
        toolchain    what builds, tests and checks this repository, and the file proving it
    print one JSON object: those keys, plus files_processed and files_at_head

Blueprint. Everything here is the same in any repository; the one function you write is
`references`, and it is the only place a language appears.

```python
#!/usr/bin/env python3
"""Architecture extractor for THIS repository. Read-only. Prints one JSON object."""
import json, subprocess, sys
from collections import Counter

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
MAX_FILES, MAX_BYTES, DEPTH, CAP = 2000, 400_000, 2, 40

def tracked():
    """Paths and their modes. The mode matters: a tracked SYMLINK points wherever its author
    chose, and opening one let a repository read a credentials file outside the checkout."""
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "-sz"],
                         capture_output=True, check=True, timeout=60).stdout
    for row in (r.decode("utf-8", "replace") for r in out.split(b"\0") if r):
        mode, _, rest = row.partition(" ")
        path = rest.split("\t", 1)[-1]
        if mode != "120000" and "\\" not in path:   # never a link, never a backslash name
            yield path

def area(path):                      # the directory an edge is drawn between
    parts = path.split("/")
    return "/".join(parts[:DEPTH]) if len(parts) > DEPTH else "/".join(parts[:-1]) or "."

# ── THE ONE PART YOU WRITE ─────────────────────────────────────────────────
# Given one file's text, return the repository-relative paths it references.
# Resolve against `at_head` and DROP anything that does not land there.
def references(path, text, at_head):
    ...

def main():
    # Root-level files INCLUDED. A flat repository keeps its entrypoint there, so dropping the
    # paths without a `/` starves the one section they were most likely to fill.
    files = list(tracked())
    at_head, fan_in, edges = set(files), Counter(), Counter()
    read = 0
    for path in files[:MAX_FILES]:
        try:
            with open(f"{ROOT}/{path}", "rb") as fh:
                text = fh.read(MAX_BYTES).decode("utf-8", "replace")
        except OSError:
            continue
        read += 1
        for target in references(path, text, at_head):
            if target == path:
                continue
            fan_in[target] += 1
            if area(path) != area(target):
                edges[(area(path), area(target))] += 1
    print(json.dumps({
        # How far this actually got. Without the pair, an artifact that read a fifth of the files
        # is shaped exactly like one that read all of them.
        "files_processed": read, "files_at_head": len(files),
        "edges": [{"from": a, "to": b, "weight": n} for (a, b), n in edges.most_common(CAP)],
        "chokepoints": [{"path": p, "fan_in": n} for p, n in fan_in.most_common(12) if n >= 3],
        # areas, entrypoints, conventions, toolchain: fill from what you read, at most CAP each.
    }, sort_keys=True))

main()
```

Constraints, and each of them is a refusal, not a preference:

- **You write it; the repository never does.** Do not assemble any part of the extractor from file
  contents, names, or configuration you just read. A repository that can write your script has
  written itself a way out.
- **Read-only and no network.** It opens files and prints; it creates nothing, changes nothing,
  fetches nothing. Nothing enforces this — there is no sandbox behind it, only you.
- **Single-threaded, one process.** Aggregate in the main thread and spawn nothing. Threads race on
  the counters and make two runs at one commit disagree, and a grandchild is the one thing the
  bound cannot reach on every platform.
- **Resolve or drop.** A reference that does not land on a tracked path is not reported. An
  extractor that guesses produces exactly the confident wrong answer this design exists to refuse.
- **Every path is repository-relative and real.** `extract` holds each one against HEAD and refuses
  the artifact if any does not resolve — so a fabricated path fails the run rather than entering
  the record.
- **Its output is evidence only after it validates.** Exit 0 admits the facts; any finding names
  what to fix, and the extractor is corrected and re-run.

Sections may be omitted where the repository genuinely has none. An empty section says "none
found"; a missing one says "not looked for" — say which you mean by including it or not. The two
counters are not a section and are never omitted: `files_processed` below `files_at_head` records
that the cap cut the reading short, and every section is then partial. Claiming to have read more
files than the repository has is refused outright.

## § Output format (SKILL Step 5 formats per this; Step 6b gate checks it)

The emitted CoC is enforced-only, plain text — no bold, no italics; markup spends every agent's
context — ordered rule-before-argument:

- **Section order** follows the scan: Architecture naming the real mechanisms, how the repo is
  extended, Testing, Quality Gates, Security & Data, Delivery. SKILL Step 5 carries the shape
  itself — orientation, summaries, tier headers over numbered runs, multi-line directives, the
  eight-per-heading cap. What follows is what the spine does not say.
- **Why numbering and grouping.** A number is how a review cites one rule; a tier header states the
  posture once instead of on every line.
- **Why a code block.** A fragment of the real thing pins a rule to THIS codebase as prose cannot,
  and it is exempt from the prose checks because it quotes the file.
- **Ground every number, and ship none that rots** — a threshold quotes an answer or a computed
  statistic, never a padded default. A measured tally justifies a rule in the envelope and never
  enters the file: "17 files today" is stale on the next addition. Name the mechanism and the
  directory, never today's count or a version literal.
- **A `Check:` names something a reader can run or open**, in backticks — or says plainly that
  nothing enforces the rule. Prose in that position reads as verification and supplies none.
- **Never claim a universal you did not verify** — "the only X anywhere", "on every host",
  "nowhere else". A path check proves existence and can NEVER prove an absence, so these clear every
  gate while being false; blind review found them the largest source of wrong statements. Say what
  you read. A requirement may sweep; evidence may not.
- **Cover every `arch.families` entry the scan reported, or record that you are skipping it.** Each
  is a way this repository grows; one left unnamed is an extension path the next reader guesses at.
- **Gate (Step 6b) — every rule clears all four**: reads exactly one way; conflicts with no other;
  is backed by a fact, an answer or an observation; names an **objective** check. The last three are
  decided by `coc_gate.py draft`; the first stays a reading. Citations live in the envelope, never
  as an appendix — that would spend every agent's tokens on every task, forever.

## § Rules envelope (Step 7 submits this; `coc_gate.py draft` judges it)

One JSON object on stdin; rule sentences are the only free text:

```json
{ "contract": 2,
  "facts":   [{"id": "cfg.lint.formatter"}],
  "answers": [{"id": "q3"}],
  "observations": [{"id": "obs.engine-strict", "path": "internal/builder/engine.mts"}],
  "rules":   [{"id": "style.formatter", "section": "Development",
               "subsection": "Formatting", "tag": "MUST",
               "text": "Format every file with the repository formatter before committing.",
               "check": "CI runs the formatter in check mode",
               "citations": ["fact:cfg.lint.formatter", "answer:q3"]}] }
```

- `tag` is `MUST`, `SHOULD`, `AVOID` or `NEVER_DO`, nothing else; `check` names the grep, lint rule,
  job or threshold.
- Every citation reads `fact:<id>`, `answer:<id>` or `code:<observation-id>` and must name evidence
  the envelope carries — an id nothing produced is a rule invented and justified afterwards.
- Every observation names the repository-relative path that shows it; the gate refuses one pointing
  outside, and the linter verifies each against HEAD (`"paths"` on its stdin, beside the draft).
- `subsection` names the concern inside its section; the gate refuses a group past eight
  directives, so it is what a split is expressed in.
- `id` is unique and stable: how an update run re-verifies the rule later.
- The reply carries `findings` (each naming its `rule_id`), `directives`, `band`, and
  `unused_evidence` — where the next question comes from.

## A. Architecture & design
- Layering & dependency direction [P0] — module graph, import cycles → deps point one way, no cycles. (conv)
- Sanctioned design patterns [P1] — repeated pattern names/dirs → name them; ban over-abstraction. (conv)
- Backward-compat contract [P0][be] — public API surface, deprecations → what may break within a version. SemVer (semver.org)
- Module size / coupling budget [P1] — file length, fan-in/out → caps with a lint/complexity check. (conv)
- Statelessness / horizontal scale [P1][be] — in-process session/state → no sticky in-process state. 12-Factor VI (12factor.net)

## B. Code style & readability
- Formatter/linter authority [P0] — formatter+lint config present → single tool is law, CI `--check`. (conv)
- Naming conventions [P0] — casing across identifiers → the repo's casing per symbol kind. (conv)
- Complexity ceiling [P1] — cyclomatic/length lint rule → cap per function/file, lint-enforced. (conv)
- Comment/docstring policy [P1] — comment density, public-API docs → why-not-what; public API documented. (conv)
- Magic-number ban [P2] — literals in code → named constants. (conv)

## C. Type safety & correctness
- Static-analysis strictness [P0] — strict/`any`/warnings config → strict on; warnings = errors. (conv)
- Null-safety default [P0] — optional/nullable usage → optionals over nullable; no unchecked null. (conv)
- Immutability default [P1] — const/readonly/value types → immutable-first for shared data. (conv)
- Exhaustiveness [P1] — switch/match on unions → cover all variants (compiler/lint checked). (conv)
- Boundary validation (parse-don't-validate) [P2] — DTO/schema at edges → validate at boundary, trust inside. (conv)

## D. Error handling & resilience
- Error taxonomy [P0] — error/exception types → categorize user/system/transient/fatal. (conv)
- No swallowed exceptions [P0] — empty catch, bare except → log-or-rethrow; grep for empty handlers. (conv)
- Timeouts on all I/O [P0][be] — client calls without deadline → every remote call has a timeout. (conv)
- Retries: bounded backoff+jitter [P1][be] — retry loops → capped, jittered, budgeted. (conv)
- Idempotent writes [P1][be] — mutation endpoints → idempotency key / natural-key upsert. (conv)
- Rate limiting / load shedding [P1][be] — throttling middleware → protect overload paths. (conv)
- Circuit breakers / bulkheads [P2][be] — resilience libs → isolate failing deps. (conv)
- Graceful degradation [P1] — fallback branches → defined partial-failure behavior. (conv)
- Cancellation / deadline propagation [P2][be] — context/cancel tokens → deadlines flow through calls. (conv)
- Dead-letter / poison-message policy [P2][data] — queue consumers → DLQ + redrive. (conv)

## E. Concurrency & state
- Shared-state guard [P1][be] — globals/statics, locks → immutable or synchronized; no data races. (conv)
- Async conventions [P1] — async/await, promises → no blocking-in-async, no fire-and-forget. (conv)
- Lock ordering [P2][be] — nested locks → canonical acquisition order; no lock across I/O. (conv)
- Consistency guarantees [P2][data] — txn/replication → state eventual vs strong per store. (conv)

## F. API & interface contracts
- REST/HTTP conventions [P0][be] — routes, status codes, verbs → codes/verbs/version scheme. (conv)
- API versioning [P0][be] — version in path/header, public API → SemVer; declare public API; 0.y unstable. SemVer (semver.org)
- Pagination/filter/sort [P1][be] — list endpoints → bounded page size; cursor or offset stated. (conv)
- Idempotency-key support [P1][be] — unsafe mutations → accept & honor idempotency keys. (conv)
- Event/message schema [P1][data] — topics, envelopes → versioned schema, keys, compat rule. (conv)
- Delivery semantics [P1][data] — consumer code → declare at-least-once vs exactly-once. (conv)
- Schema evolution/compat [P1][data] — avro/protobuf/migrations → forward/backward compat rule. (conv)
- Contract testing [P2][be] — pact/consumer tests → consumer-driven contracts on shared APIs. (conv)
- Public-API stability tiers [P1] — stable/beta labels → mark stable/experimental. (conv)

## G. Data & persistence [data/be]
- Migration discipline [P0][be] — migrations dir, DDL → expand-contract, reversible, migrate-before-code. (conv)
- Indexing rules [P1][data] — schema, slow-query logs → index query paths; avoid over-indexing. (conv)
- N+1 prevention [P1][be] — ORM loops → batch/join/eager-load; grep per-row queries. (conv)
- Transaction boundaries [P1][be] — txn scope, isolation → scope tight; isolation stated; no txn across remote calls. (conv)
- Connection pooling [P1][be] — pool config → sized pool; no leaks. (conv)
- Soft vs hard delete [P1][data] — deleted_at, tombstones → policy + audit. (conv)
- Data lifecycle / retention [P1][data] — TTL, purge jobs → retention window + automated deletion. (conv) — see I
- Caching + invalidation [P1] — cache layer → TTL + invalidation + stampede protection. (conv)
- Query cost/timeout guard [P2][data] — statement timeout → kill runaway queries. (conv)

## H. Security  (OWASP ASVS 5.0 — owasp.org/ASVS)
- Secrets management [P0] — hardcoded secrets, vault/env, scanner → no literals; env/vault; scanner gates CI. 12-Factor III
- Input validation & output encoding [P0] — injection sinks, sanitizers → allowlist/schema at edge; parameterized queries; contextual encoding.
- AuthN/AuthZ model [P0][be] — route guards, per-endpoint checks → every non-public endpoint enforces authz. ASVS
- Dependency/vuln scanning (SCA) [P0] — SCA config, lockfile → SCA gate; no known high/critical CVEs. (conv)
- Crypto standards [P1] — MD5/SHA1/custom crypto → vetted lib + current algs; no homemade. ASVS
- Secret rotation [P1][infra] — rotation config → rotation cadence + revocation. (conv)
- Security headers & TLS [P1][be/fe] — HSTS/CSP/TLS config → min TLS; required headers. ASVS
- SSRF/deserialization/path-traversal [P1][be] — risky sinks → specific class defenses. ASVS
- Least-privilege IAM [P1][infra] — wildcard roles, root containers → scoped roles; non-root. (conv)
- Supply-chain provenance [P2][infra] — signed artifacts, SBOM → require a SLSA Build level. SLSA (slsa.dev)
- Threat modeling [P2] — new-surface docs → threat model for new external surfaces. (conv)
- Audit logging (security events) [P1] — auth/admin logs → log auth/authz/admin actions. OWASP Logging Cheat Sheet
- Coordinated disclosure policy [P1] — `SECURITY.md`, contact → a documented responsible-disclosure path. (conv)
- Prompt-injection isolation [P2][ai] — LLM input handling → isolate untrusted input in agent flows. (conv)

## I. Privacy & data governance (GDPR/PII) [data]
- Data classification scheme [P1][data] — classification tags/labels → public/internal/confidential/restricted tiers with a handling rule each. (conv)
- PII classification & tagging [P0][data] — PII-like columns (email/phone/ssn/dob/ip) → tag every personal field; untagged PII fails review. (conv)
- Encryption in transit & at rest [P0][data] — TLS + KMS/at-rest config → personal data TLS≥1.2; restricted at rest via KMS. (conv)
- Retention & erasure [P1][data] — TTL, DSAR/delete paths → retention limit + automated erasure path. GDPR Art.17 (conv)
- Data minimization & lawful basis [P1][data] — collected fields → collect only justified fields; document basis. GDPR Art.5/6 (conv)
- PII/secrets never in logs [P0] — log statements with user objects → mask/redact at logging boundary. OWASP Logging Cheat Sheet
- Cross-border / residency [P2][data] — region config → transfer only to approved regions; default deny. (conv)
- Anonymization for analytics [P2][data] — analytics sinks → pseudonymize/scrub before analytics. (conv)
- Regulatory posture (SOC2/HIPAA/PCI) [P2] — compliance docs → map controls if in scope. (conv)

## J. Testing
- Unit coverage floor [P0] — coverage config → threshold on BRANCHES not just lines + meaningful asserts. (conv)
- Coverage ≠ effectiveness → mutation [P1] — mutation tool present → kill-rate gate when a mutation tool exists; else recommend adopting one. ACM 10.1145/3701625.3701629
- Test structure/naming [P1] — test dir patterns → the repo's naming + G-W-T/AAA convention. (conv)
- Integration/e2e scope [P1] — integration tests, containers → real-dep coverage of critical paths. (conv)
- Flaky-test policy [P1] — retries/skips in CI → quarantine+fix SLA; retries are not a fix. (conv)
- Test isolation/determinism [P1] — shared state, wall-clock/random → no shared state; injectable time/seed. (conv)
- Test-data management [P1] — fixtures/factories → no prod data; factories over shared fixtures. (conv)
- Property/fuzz [P2][be] — parsers/untrusted input → property-based/fuzz on parsers. (conv)
- Contract/load/visual [P2] — pact/k6/snapshot → per surface as applicable. (conv)
- Architecture/dependency rules [P1] — arch-rule tool present → narrow package patterns only; broad wildcards catch cross-cutting packages that legitimately interdepend. Exclude dto/entity/config subpackages or baseline existing violations. (conv)

## K. Observability  (Google SRE Workbook — sre.google/workbook/monitoring)
- Structured logging [P0] — logger vs print, JSON config → one JSON object per line; required fields. 12-Factor XI + SRE
- Log levels discipline [P1] — level usage → ERROR=actionable, WARN=recoverable, INFO=lifecycle, DEBUG=diagnostic (off in prod), TRACE=dev. OWASP
- Correlation/request IDs [P1][be] — MDC/context propagation → propagate a correlation id across calls. (conv)
- Metrics RED/USE [P1][be/infra] — instrumentation, /metrics → request-rate/error-rate/duration per service. SRE
- Health/readiness endpoints [P1][be/infra] — liveness/readiness → expose both. (conv)
- Distributed tracing [P2][be] — trace SDK → propagate trace context; no trace-breaking calls. (conv)
- Never-log list [P0] — see I → passwords/tokens/session-ids/PII/keys/card-data excluded. OWASP Logging Cheat Sheet

## L. Performance
- Latency budgets [P1] — SLO annotations, perf tests → p95/p99 budget per critical endpoint; perf gate. (conv)
- N+1 / query discipline [P1][be] — see G → batch/join. (conv)
- Pagination / payload limits [P1][be] — list endpoints → bounded results; no unbounded SELECT *. (conv)
- Timeouts + cache policy [P1] — see D/G → I/O timeouts; documented cache TTL. (conv)
- Resource ceilings [P1][infra] — pod/container limits → memory/CPU limits set. (conv)
- Profiling-before-optimizing [P2] — perf notes → measure first. (conv)
- Cost/FinOps [P2][infra] — cost tags → cost-per-request awareness. (conv)

## M. Frontend [fe]
- Accessibility (WCAG) [P0][fe] — a11y lint/tests → WCAG level; keyboard+contrast; a11y gate. (conv)
- i18n/l10n [P1][fe] — hardcoded strings, locale files → externalized strings; RTL. (conv)
- Bundle-size budget [P1][fe] — bundler budget config → size budget in CI. (conv)
- Core Web Vitals [P1][fe] — RUM/lighthouse → LCP/CLS/INP targets. (conv)
- State-management rules [P1][fe] — store patterns → single source; no prop-drilling abuse. (conv)
- Design-system adherence [P1][fe] — component lib → reuse over reinvention. (conv)
- Client error tracking + CSP [P2][fe] — error SDK, CSP header → capture errors; CSP for 3p scripts. (conv)

## N. Mobile [mobile]
- Offline/sync + conflict [P2][mobile] · Battery/network budget [P2] · App-size/startup [P2] · Permission minimalism [P1] · Crash-free SLO [P1] · OS/device matrix [P2]. (conv)

## O. Data/ML [ml/data]
- Reproducibility (seeds/versions) [P1][ml] · Data & model versioning/lineage [P1][ml] · Train/serve skew & leakage [P2][ml] · Eval/bias gates [P2][ml] · Model cards [P2][ml] · PII in training data [P1][ml] · Drift monitoring [P2][ml] · Pipeline idempotency/backfill [P2][data]. (conv)

## P. Infrastructure & IaC [infra]
- Everything-as-code [P1][infra] · Env parity (12-Factor) [P1][infra] (12factor.net) · Immutable infra [P2] · Container standards (non-root/size/base) [P1][infra] · Resource requests/limits [P1][infra] · Network segmentation [P2] · IaC state/drift [P2] · Tagging/ownership [P2]. (conv)

## Q. Build, release & delivery
- CI quality gates [P0] — CI config → must-pass checks before merge. (conv)
- Commit conventions [P1] — `git log` → the repo's format (type/scope/tense/ticket). Conventional Commits (conv)
- Branching & merge strategy [P1] — branches, merge shape → naming + linear/merge policy. (conv)
- Semantic versioning [P1] — tags → SemVer. semver.org
- Feature-flag lifecycle [P1] — flag SDK, stale flags → owner + expiry; cleanup obligation. (conv)
- Rollback/runbook [P1][infra] — deploy scripts → every deploy reversible. (conv)
- Progressive delivery [P2][infra] — canary/blue-green config → staged rollout. (conv)
- Migrate-before-code ordering [P1][be] — see G → decouple DB from deploy. (conv)
- Release approval / change-mgmt [P2] — CODEOWNERS, protected release → who signs off. (conv)

## R. Dependency & supply-chain
- Lockfile/pinning [P0] — lockfiles → reproducible installs; pinned. (conv)
- License policy [P1] — license scanner, deps → allowed-license list; deny copyleft unless whitelisted. (conv)
- New-dependency justification [P1] — dep diffs → add-a-dep review bar. (conv)
- Update cadence [P1] — renovate/dependabot → automated update policy. (conv)
- SBOM / provenance [P2][infra] — see H → SBOM; signed artifacts. SLSA (slsa.dev)

## S. Version control & git hygiene
- Protected branches + required reviews [P0] — branch protection, CODEOWNERS → no direct push; min approvers. (conv)
- Commit signing / sign-off (DCO/CLA) [P2] — signed commits, `Signed-off-by`, CLA bot → provenance of contribution. (conv)
- License headers [P2] — SPDX/header presence → source-file license header rule. (conv)
- Secret/large-file pre-commit scan [P1] — pre-commit hooks → block secrets/binaries. (conv)
- Monorepo vs polyrepo rules [P2] — workspace config → code-location policy. (conv)

## T. Code review & PR
- Approval rules [P0] — CODEOWNERS, required reviewers → min approvers per area. (conv)
- PR size limits [P1] — PR stats → cap diff for reviewability. (conv)
- Review rubric [P1] — review docs → what reviewers must check. (conv)
- Self-merge policy [P1] — merge settings → allowed or not. (conv)
- Author responsibilities [P1] — PR template → description, test evidence, screenshots. (conv)

## U. Process: readiness & done  (Google Eng-Practices — google.github.io/eng-practices)
- Definition of Done [P1] — PR template, CI → tested + observability + docs; net code-health improves. Google
- MUST/SHOULD normativity [P1] — RFC-2119 usage → MUST=CI-blocking, SHOULD=reviewer-enforced. RFC-2119 (rfc-editor.org)
- Definition of Ready [P2] — issue templates → entry criteria. (conv)

## V. Documentation
- README standards [P0] — README → setup/run/test in every repo. (conv)
- ADRs [P1] — adr/decisions dir → record architecture decisions. (conv)
- API docs in sync [P1][be] — OpenAPI/generated → kept current. (conv)
- Inline/docstring policy [P1] — public API docs → documented. (conv)
- Runbooks [P1][infra] — ops docs → for on-call. (conv)
- Diagram-as-code [P2] — mermaid/plantuml → versioned diagrams. (conv)

## W. Operations & SRE [infra/be]
- SLOs/SLIs & error budgets [P1][infra] · On-call/escalation [P2] · Incident response [P2] · Blameless postmortems [P2] · Backups & DR (RPO/RTO) [P1][infra/data] · Graceful shutdown/drain [P1][be] · Chaos testing [P3] · Capacity planning [P3]. (conv)

## X. Configuration & feature management
- Externalized config [P1] — hardcoded env values → config from env/file, never hardcoded. 12-Factor III
- Config validation at startup [P1] — startup checks → fail-fast on bad config. (conv)
- Secret vs config separation [P1] — see H → different handling. (conv)
- Feature-flag governance [P1] — see Q → owner + kill-switch. (conv)

## Y. Data internationalization
- UTC/timezone discipline [P1][be] — datetime usage → store UTC; no naive datetimes. (conv)
- Money as decimal [P1][be] — float money → decimal/minor-units, never float. (conv)
- Unicode/encoding [P1] — encoding config → UTF-8; normalization. (conv)
- Locale-aware formatting [P2][fe] — i18n formatting → dates/numbers/collation. (conv)

## Z. Lifecycle, debt & deprecation
- Deprecation lifecycle [P1] — deprecation notes → announce/migrate/remove timeline. (conv)
- Tech-debt tracking [P1] — debt register, TODOs → ticket-linked, budgeted. (conv)
- Dead-code removal [P2] — commented-out code → no graveyards. (conv)
- TODO/FIXME hygiene [P2] — TODO density → ticket-linked, expiring. (conv)

## AA. Analytics & telemetry (product)
- PII-free event payloads [P1][data] · Consent-gated analytics [P2][fe] · Event taxonomy [P2] · Sampling/volume governance [P3]. (conv)

## AB. AI-agent governance  (this file IS read by AI coding agents)
- Autonomy boundaries [P1][ai] — agent-config → what agents may do without approval. (conv)
- Destructive-action guardrails [P1][ai] — deletes/deploys/force-push → forbid unbounded destructive ops. (conv)
- Agent credential least-privilege [P1][ai] — agent tokens → scoped, minimal. (conv)
- AI-generated-code review [P1][ai] — AI provenance → human sign-off on AI diffs. (conv)
- Test-before-claim [P2][ai] — verification norms → agents verify, not assert. (conv)
- Prompt-injection resistance [P2][ai] — see H → untrusted-input isolation. (conv)

## AC. Developer experience
- Local-dev parity [P1] — bootstrap script → one-command setup. (conv)
- Pre-commit hooks [P1] — hooks config → lint/format/test locally. (conv)
- Reproducible dev env [P2] — devcontainer/nix → pinned env. (conv)
- Generated-code convention [P2] — codegen markers → mark & don't hand-edit. (conv)

## AD. Ownership
- CODEOWNERS / service ownership [P1] — CODEOWNERS → clear owner per area. (conv)
- Knowledge-sharing / bus-factor [P3] — ownership docs → no single-owner silos. (conv)
