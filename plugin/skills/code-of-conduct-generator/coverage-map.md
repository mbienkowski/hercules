# Coverage map — code-of-conduct generator (internal scan aid, not CoC output)

The generator drafts **evidence-first** from the repo, then runs this map ONCE as a **gap detector**:
for each applicable point, was a rule already drafted from scan evidence or a user answer? If not and
the point is load-bearing, surface it in chat as a recommendation — accept makes it a real rule,
decline drops it. Never emit a point from this map without repo evidence or an explicit user yes.

**Tiers:** `P0` every serious repo · `P1` most repos · `P2` situational · `P3` emerging.
**Stack flags:** `[be]` backend · `[fe]` frontend · `[mobile]` · `[data]` · `[ml]` · `[infra]` · `[ai]`.
Load only the groups whose stack the scan detected; always load A–D, H–L, Q–V, Z, AB.
**Sources:** backbone points cite a primary standard; `(conv)` = established convention, not a cited spec.
Each point: `name [tier][stack] — scan signal → rule shape.`

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

## H. Security  (OWASP ASVS 5.0 — owasp.org/ASVS; ~350 "Verify that…" reqs)
- Secrets management [P0] — hardcoded secrets, vault/env, scanner → no literals; env/vault; scanner gates CI. 12-Factor III (12factor.net)
- Input validation & output encoding [P0] — injection sinks, sanitizers → allowlist/schema at edge; parameterized queries; contextual encoding. ASVS
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
- Prompt-injection isolation [P2][ai] — LLM input handling → isolate untrusted input in agent flows. (conv)

## I. Privacy & data governance (GDPR/PII) [data]
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
- Commit signing [P2] — signed commits → verified commits. (conv)
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
