# Code-of-conduct generator — research findings and draft requirements

**This is a dated record, not a living document.** Its measurements are pinned to the HEADs named in
§ 3 and are never updated to track the shipped skill. §§ 2 and 6 are superseded the moment the
technical spec lands; §§ 1, 3, 4, 5 age as history. Read it for how the decisions were reached, not
for the current state of the code.

This document records the research behind evolving the `code-of-conduct-generator` skill from prose-only
instructions into a scripted, testable pipeline. It contains: the criteria for a good code-of-conduct
(§ 1), a gap audit of the current skill against them (§ 2), feasibility-spike results with measurements
(§ 3), the boundary between script-resolvable facts and LLM judgment (§ 4), the integration constraints
any implementation must respect (§ 5), draft business requirements (§ 6), and the advisory review that
reshaped them (§ 7). Spike code is throwaway and intentionally not committed; only its measurements
appear here. The next phase turns § 6 into technical specs; nothing in this document changes shipped
content.

**One finding does not wait for the spec phase.** § 7.1 records a shipped-today vulnerability in the
opencode target, found while threat-modelling this redesign and confirmed by inspection. It is
independent of this work and needs its own fix.

## 1. What makes a good code-of-conduct (criteria checklist)

A generated `code-of-conduct.md` is read by AI agents on every task, so its format is an
instruction-following problem, not a documentation-style preference.

**Two kinds of criteria, kept apart deliberately.** C1, C2, C5, C6, C7 are *derived from evidence* —
external research or the shipped skill's own standards. C3's bands, C8, and C9 are *owner decisions*:
they encode what this product wants to be, and a prose-only skill grades poorly against them by
construction. That circularity is real, so the two groups are labelled rather than blended; a reader
who rejects the owner decisions should discount the rows that depend on them (§ 2), not the rest.

- **C1 — Categorized.** Rules grouped in themed sections, most load-bearing first, with a
  `Non-negotiables` lead block. *Source: the skill's own § Output format; mirrored by the section
  structure of `CODE_OF_CONDUCT.md`.*
- **C2 — Atomic bullets, not prose.** One imperative rule per bullet, normatively tagged (MUST/SHOULD,
  RFC-2119 style). A rule that needs a paragraph is two rules or none. *Source: § Output format;
  coverage-map § U (MUST=CI-blocking, SHOULD=reviewer-enforced).*
- **C3 — Bounded volume.** *Evidence-derived (bands), owner decision (mechanical counting).*
  Instruction-following degrades as simultaneous directives grow (§ 1.1); the skill's own budget model
  (30–40 directives, 70 hard ceiling, ~150-directive adherence line for the delegate total) already
  encodes this. That the count should be *mechanical rather than estimated* is an owner decision, not
  a research finding. **Unresolved tension:** the research behind C3 bounds *volume*, not just
  directive count — "target under ~200 lines", "a huge file buries the rules that actually matter" —
  while C4 and C5 add annotation mass at constant directive count. The exemplar itself is 559 lines,
  2.8× the guidance this document cites approvingly. C3 and C4/C5 pull against each other; § 6 bounds
  annotation volume rather than pretending the tension away.
- **C4 — Per-group WHY.** *Evidence-derived, with scope adjusted.* A WHY changes how an agent
  generalizes a rule to unlisted cases; it is annotation, not an extra directive. *Source:
  `CODE_OF_CONDUCT.md` line 10 — rules follow "**the rule in bold**, a one-line WHY, and a DON'T/DO
  pair where one fits."* Note the exemplar attaches WHY **per rule** (18 occurrences) and Google's
  guide attaches rationale to every non-obvious rule; per-*group* is this document's weaker
  compromise, chosen to respect C3's volume pressure.
- **C5 — DO/DON'T pairs with real fragments.** *Evidence-derived; conditional, not universal.*
  Contrastive examples mined from the repo (≤3 lines, citable) pin a rule's meaning to this codebase's
  idiom. *Source: `CODE_OF_CONDUCT.md`'s format — its naming rules cite `scope.mts` vs
  `variable-scope.mts` — plus the contrastive-prompting evidence in § 1.1.* The exemplar carries 11
  pairs against 18 WHY lines and says "where one fits": pairs belong where idiom is at stake, not on
  every rule. The gap in the current skill is that it never requires them **at all**, not that it
  fails to require them everywhere.
- **C6 — Every rule enforced and evidenced.** A rule names its mechanical check inline and traces to a
  captured observation or an explicit user answer; anything recommended-but-unmet stays out of the
  file. *Source: SKILL.md Invariants; § Output format gate.*
- **C7 — Present-truth only.** A rule cites paths, commands, and checks that exist *now*; dangling
  references are defects detectable by machine. *Source: `CODE_OF_CONDUCT.md` § Documentation ("every
  written word describes the present state"); § 3.3 shows detection is mechanizable.*
- **C8 — Reflects the code that is alive.** *Owner decision.* Standards derive from the modules being
  worked on today, not from dormant legacy mass; where old and new patterns conflict, the
  recent-dominant pattern leads and the legacy one is named. § 3.1 shows liveness is *measurable*; it
  does not show that churn is a valid proxy for "conventions that should drive standards" — hot code
  can be code being deprecated, reformatted, or ripped out. That proxy is assumed, not demonstrated.
- **C9 — Reproducible.** *Owner decision.* Two runs at the same HEAD produce the same rule *set*
  (wording may vary; elements may not). *Source: owner direction; `CODE_OF_CONDUCT.md` § "Executable
  over wishful".* **Deliberately unfalsifiable as scoped:** measuring end-to-end rule-set agreement
  needs repeated live LLM runs, which the owner ruled out of test scope. Determinism in the facts and
  the gate is therefore a *necessary* condition being pursued, never a demonstrated sufficient one —
  the middle layer (which rules an agent drafts from identical facts) stays judgment. Any claim that
  scripting "achieves" a consistency percentage is unsupported and is not made in § 6.

### 1.1 External sources

- **agents.md** defines the agent instruction file as "a README for agents": plain Markdown, focused
  sections of short imperative bullets with exact commands, no schema
  (https://agents.md/, https://github.com/agentsmd/agents.md). OpenAI's Codex guide warns that "a huge
  file buries the rules that actually matter"
  (https://developers.openai.com/codex/guides/agents-md), and OpenAI's own `AGENTS.md` is a flat
  imperative list with explicit negative rules and inline preferred code shapes
  (https://github.com/openai/codex/blob/main/AGENTS.md) — supporting C1/C2/C5.
- **Anthropic's Claude Code guidance**: "keep it short and human-readable"; per line, "Would removing
  this cause Claude to make mistakes? If not, cut it. Bloated CLAUDE.md files cause Claude to ignore
  your actual instructions"; include only what the model cannot infer from the code; target under
  ~200 lines; contradictory rules get picked between arbitrarily
  (https://code.claude.com/docs/en/best-practices, https://code.claude.com/docs/en/memory) —
  supporting C2/C3/C6, and the gate's no-conflicts check.
- **Instruction-capacity research**: prompt-level compliance declines roughly exponentially with the
  number of simultaneous instructions ("Curse of Instructions",
  https://openreview.net/forum?id=R6q67CDBCH); at high instruction density even top models drop to
  ~68% adherence (IFScale, https://arxiv.org/abs/2507.11538); mid-context content is recalled worst
  ("Lost in the Middle", https://arxiv.org/abs/2307.03172) — quantitative backing for C3's counted
  budget and C1's Non-negotiables-first ordering.
- **Few-shot and contrastive examples**: examples reliably steer output beyond instructions alone
  (https://arxiv.org/abs/2005.14165; Anthropic recommends 3–5 relevant, diverse examples,
  https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview); pairing valid
  with *invalid* demonstrations outperforms positive-only prompting (Contrastive CoT,
  https://arxiv.org/abs/2311.09277) — direct evidence for C5's DO/DON'T pairs.
- **Structured outputs**: schema-constrained generation removes malformed/missing-field drift that
  prompting alone cannot (https://platform.claude.com/docs/en/build-with-claude/structured-outputs;
  https://openai.com/index/introducing-structured-outputs-in-the-api/) — supporting C9's
  structured-before-prose pipeline. Caveat worth designing around: rigid format constraints can
  degrade reasoning-heavy steps unless the schema leaves room to reason before answering
  (https://arxiv.org/abs/2408.02442, with replications at https://blog.dottxt.ai/say-what-you-mean.html
  and https://dylancastillo.co/posts/say-what-you-mean-sometimes.html) — so the envelope constrains
  rule *shape*, while scanning and judgment happen before schema-filling.
- **Human style-guide practice**: Google's style guide requires each rule to "pull its weight" and
  attaches explicit rationale blocks to every non-obvious rule
  (https://google.github.io/styleguide/cppguide.html); PEP 8 grounds rules in readability and licenses
  documented exceptions (https://peps.python.org/pep-0008/) — supporting C4 and C2's normative split.

## 2. Gap audit: the current skill against § 1

| Criterion | State | Evidence |
|---|---|---|
| C1 categories | ✅ | § Output format mandates Non-negotiables lead + themed sections |
| C2 atomic tagged bullets | ✅ | "one atomic imperative per rule, tagged MUST or SHOULD" |
| C3 bounded volume | 🟡 | Budget bands exist (30–40/50/70) but counting is wishful — no program counts |
| C4 per-group WHY | ❌ | Only optional: "a section *may* open with one evidence-grounded WHY sentence" |
| C5 DO/DON'T + fragments | ❌ | Not required anywhere; the generator's output format is weaker than the repo's own `CODE_OF_CONDUCT.md` format |
| C6 enforced + evidenced | 🟡 | The four-part gate exists as prose; "dry-run each cited check" is an LLM instruction with no tool behind it |
| C7 present-truth | 🟡 | Update mode surfaces conflicts by LLM judgment; no mechanical dangling-reference detection |
| C8 alive-code weighting | ❌ | History mining covers conventions only; "two live patterns → a question" has no recency tiebreak, so a dormant monolith drags rules toward dead conventions |
| C9 reproducibility | ❌ | coverage-map claims "two runs ~identical" via canonical sampling — asserted, never tested, no scripts |

Summary: structure and evidence-discipline are designed well; **examples, liveness, and every
deterministic mechanism are missing or wishful**. Zero shipped code backs the skill today.

**The load-bearing limitation of this whole audit.** Every verdict above says a *mechanism is absent*.
None says an *output was bad* — because the current skill was never run. No baseline CoC was
generated, no two-run divergence was measured, no bloated or dead-convention output was exhibited. The
one empirical probe of a real CoC (§ 3.3) cuts against urgency: the hand-maintained
`CODE_OF_CONDUCT.md` had **zero** true dangling references, so the failure C7 exists to catch was not
observed in the wild. This document therefore establishes **feasibility** (scripts can compute these
facts fast and repeatably) and **conformance to owner-chosen criteria** — it does not establish
**necessity**. The C6 row also overstates its evidence: the agent does execute greps via its shell
today, so the real gap is that nothing *proves* the dry-run happened, not that the capability is
absent. Closing the necessity gap is the first item in § 8.

## 3. Spike results (throwaway scripts; measurements reproducible at the stated HEADs)

### 3.1 Churn heatmap (criterion C8)

Method: one `git log --since --name-only` pass over a 12-month window; per-file touch weights decayed
exponentially (half-life 90 days) **anchored to the HEAD commit's committer date, never wall clock**;
aggregated to directories at fixed depth; plus a top-N weighted file list. Canonical JSON out.

- **Hercules** (HEAD `5ed8976`, 50 non-merge commits in window): runtime **0.10 s**. Hottest:
  `src/content` (weight 0.105). Byte-identical across repeated runs.
- **django/django** (blob-less bare clone, 1123 commits in window, 1612 files touched): runtime
  **0.19 s**. Hottest: `django/contrib/admin`, then `docs/releases` and `django/db/models`.
  Byte-identical across repeated runs. **Two honest caveats:** ranking hot directories by commit
  activity is true by construction, so "the hot areas look plausible" validates nothing — and the
  dormant count from this run is unreliable anyway, since never-touched directories are invisible to
  `git log` (defect 3 below). Whether churn is a good proxy for "conventions worth codifying" remains
  untested.
- **Decay sensitivity — the result that changed the design.** On Hercules the test was vacuous: the
  repo is ~5 weeks old, so every commit sits inside ~36 days and half-lives of 30/90/180 d cannot
  differentiate. Re-run on django's real 12 months (half-lives 30/90/180/365 d), the top-10 directory
  set is **9–10 of 10 identical across the whole range**; only adjacent ranks swap (`docs/releases`
  and `django/contrib/admin` trade #1/#2 above ~180 d). Conclusion: **decay does not pull its weight.**
  A plain windowed touch-count excludes dormant mass just as well, and two windows (12-month and
  recent) give the recent-vs-overall shares the conflict rule needs — with zero tuning parameters and
  an auditable number ("17 touches this quarter" is debuggable at 3am; a decayed 0.105 is not). § 6
  drops decay accordingly. Note this also removes the reason for HEAD-anchoring the clock, though the
  determinism requirement that motivated it stays.
- **Output size**: top-50 file list ≈ 3.8 KB JSON — cheap LLM ingestion; the model samples reads from
  this list instead of walking the tree, which is the token-economy win.
- **Data-quality findings a real tool must handle** (all observed, not hypothesized):
  1. Generated trees pollute the ranking — on Hercules, seven `dist/*` directories fill the top 12.
     The tool must tag or exclude paths a repo marks generated (and let the skill confirm).
  2. Renamed-away paths rank — `src/builder` scored 3rd on Hercules but does not exist at HEAD.
     Weights must be intersected with `git ls-files` at HEAD.
  3. Never-touched directories are invisible to `git log` — true dormancy must be computed against the
     full HEAD tree, or the dormant monolith mass the heatmap exists to expose is silently absent.

### 3.2 Deterministic facts (criteria C6, C9)

Method: known-config catalogue probe + value-level reads of parseable configs (JSON) + commit-subject
classification over the last 200 commits. Canonical JSON facts with ids, confidence, citations.

- **Scope limit:** the catalogue was written against Hercules and validated on Hercules — textbook
  overfitting. The django clone was blob-less, so config *contents* were never read there; no repo
  with ESLint, Prettier, or YAML-heavy CI ever exercised the positive paths the catalogue exists for.
  The "0.05 s, 17 facts" result is a lower bound on cost, not a measure of accuracy in the wild.
- On Hercules: **17 facts in 0.05 s, byte-identical across runs**. Correct positives: conventional
  commits at 0.88 share with scopes; 10/10 npm deps exact-pinned; TypeScript `strict: true`;
  Node `>=22`; zero merge commits (linear history); vitest + pytest + Makefile + CI + dependabot +
  `.githooks` + CONTRIBUTING + LICENSE present. Correct negatives: no ESLint/Prettier fact emitted —
  which matches the repo's documented stance that `tsc` strictness and review hold the bar.
- JSONC (`tsconfig` comments) needs a hardened reader; YAML/TOML values are out of reach for stdlib
  3.9 (`tomllib` is 3.11+), so those checks stay textual — an honest-scope limit, reported as such.

### 3.3 Stale-scan of an existing CoC (criterion C7)

Method: extract backticked tokens from a CoC-like markdown, classify (path / make target /
placeholder / other), verify paths against `git ls-files` (with prefix and suffix fallback) and make
targets against the Makefile.

- **Specificity** on `CODE_OF_CONDUCT.md` (559 lines): **63 verified, 5 flagged, 113 unparsed**
  (non-verifiable kinds: concepts, commands, placeholders). All 5 flags are false positives in three
  *identifiable* classes: DO/DON'T example names (`scope.mts`), npm import specifiers
  (`js-tiktoken/lite`), and files the text says will be created (`code-of-conduct.md`). ≈7% FP rate on
  parseable tokens, all three classes filterable.
- **Sensitivity**, measured by injected fault rather than assumed: five realistic staleness faults
  (three renamed paths, one renamed tool, one removed make target) were injected into a copy of the
  file. The scanner flagged **5 of 5**, each as a new dangling entry distinct from the baseline noise.
  Detection is real, not an artifact of a clean document.
- **Coverage limit, stated plainly:** 113 of 181 tokens (62%) are unparseable kinds. Mechanical
  verification therefore covers roughly a third of a document's citations — a useful third, since
  paths and make targets are exactly what rots, but nowhere near the whole file. Any requirement
  leaning on this scanner inherits that ceiling.
- Consequence: for **generated** CoCs the rule→citation link must ship as machine data (a citation
  envelope persisted to state), so update-mode verification is exact re-checking, never prose
  re-parsing. Best-effort parsing is only for CoCs the generator did not write, presented as a report
  for a human decision, never auto-acted-on.

### 3.4 Hostile-input probe (added after the security review)

The spikes assumed a friendly repository. One adversarial test was then run against a crafted repo
containing a file named `src/eve<newline>il.py`:

- The heatmap spike emitted **two phantom directories** (`'"src'` and `'src'`) and a mangled file path
  from that single filename. Line-splitting `git log --name-only` output is therefore unsafe: git
  C-quotes such names by default, and a repository can set `core.quotePath` in its own `.git/config`.
  Real tools must consume NUL-delimited plumbing output.
- This also bounds the determinism claim: "byte-identical" was demonstrated same-machine, same git
  version, same config, minutes apart. It proves the design has no wall-clock dependence — a real
  property — but git output is config-sensitive, so byte-identity across environments needs pinned
  `-c` overrides and remains an untested requirement rather than a measured result.

## 4. The deterministic/LLM boundary

What the spikes establish scripts can own, versus what stays judgment:

| Layer | Owner | Basis |
|---|---|---|
| Sizing, config inventory, dep pinning, strictness flags, CI/hook/owner file presence | Script | § 3.2 — config-first resolves these exactly |
| Commit convention, merge shape, tags, branch names | Script | § 3.2 history classification |
| Churn heatmap, alive/dormant, top-N sample list, conflict shares (recent vs overall) | Script | § 3.1 |
| Directive counting, citation-id validation, cited-path/target existence checks | Script | § 3.3 mechanics |
| Final markdown skeleton (section order, tags, annotation placement) | Script (renderer) | C9 — format must not drift |
| Naming design patterns from sampled reads; config-vs-code reconciliation; picking the DO/DON'T fragments | LLM | Judgment over sampled code the heatmap selects |
| Rule *sentences*, WHY lines, question phrasing | LLM | Last step, inside structured fields |
| Intent, thresholds, gate accept/decline, conflict-resolution confirmation | User | The skill's existing single-batch interview |

## 5. Integration constraints (verified in-repo)

- Shipped executables are stdlib-only Python ≥3.9 in `src/scripts/tools/`, patterned on
  `project_reset.py`: fail closed, exit-code contract, `CONTRACT_VERSION`, no shebang.
- Recipes are explicit per-file — a new tool needs one entry in each of the seven
  `src/targets/<eco>.json`, and `make build` regenerates `dist/` in the same commit (drift gate).
- Skills invoke shipped tools as `python3 {{ plugin_root }}tools/<name>.py` (the mechanism
  `hercules-reference` already uses for `registry_sync.py`); the opencode target resolves
  `plugin_root` to an empty string — a pre-existing wrinkle shared with `registry_sync.py`.
- `tests/scripts/tools/test_tool_hygiene.py` must register every tool; its git-subcommand allowlist is
  a single module-level set today and needs to become per-tool before any tool may use `git log`.
- Token budgets are immovable without an explicit owner request: SKILL.md 3000, coverage-map 6600
  (`tests/content/promptBudgets.spec.ts`); `skillPromises.spec.ts` pins the nine step labels.
- Step 7 of the skill runs in plan mode where nothing may be written — any draft-gating tool must read
  its input from stdin.
- A shipped tool must never execute commands mined from a target repository (lint/CI invocations are
  an arbitrary-code surface); verification is existence and matchability only.

## 6. Draft business requirements

Outcome-phrased; each traces to a finding. This set is **post-advisory** — § 7 records what the board
changed and why. Eight requirements: BR-1..3 the evidence layer, BR-4..6 the drafting layer,
BR-7..8 the update and delivery layers. Each carries its safety clauses inline rather than in a
separate security requirement, so an implementer cannot satisfy the requirement while dropping them.

- **BR-1 — Evidence is a deterministic program (C6, C9; § 3.2).** A shipped tool emits canonical facts
  JSON: at the same HEAD, two runs are byte-identical. Every fact carries an id, a confidence tag, and
  a citation; absent evidence yields no fact; cap breaches degrade to explicit unknowns that become
  interview questions. The document distinguishes **probes attempted from probes matched**, so a stale
  config catalogue is visible per run rather than indistinguishable from a correct negative. Bounds on
  commits examined, distinct paths tracked, and wall-clock are enforced, each degrading to unknowns.
- **BR-2 — Facts reflect the code that is alive (C8; § 3.1).** Facts include per-directory touch counts
  over two plain windows — a long one (default 12 months) and a recent one — so every candidate pattern
  carries a recent share and an overall share. **No decay kernel:** § 3.1 measured the top-10 set as
  9–10/10 stable across half-lives from 30 d to 365 d on a real 12-month history, so decay bought
  nothing and cost a tuning parameter and auditability. Liveness is computed against the full HEAD tree
  (not just touched paths), renamed-away paths are excluded by intersecting `git ls-files` at HEAD, and
  generated trees are tagged. A bounded top-N weighted file list is emitted; the drafting agent samples
  its reads from that list rather than walking the tree.
  **Open decision, not settled by evidence (§ 7.3):** where two patterns serve one concern, this
  requirement would make the recent-dominant one a recommended default with the other named legacy —
  which *overturns* the shipped invariant "two live patterns for one concern → a question, never
  majority rule" (coverage-map § Tag & capture). Recency-weighted dominance is majority rule with a
  window. The spikes showed recency is computable, never that recency-defaults beat asking. The owner
  decides: keep asking always (invariant intact, facts merely inform the question), or default and
  flag. Conflicting values are never averaged either way.
- **BR-3 — Scanning an untrusted repository is safe (§ 7.1).** The target repo is attacker-controlled
  input. Therefore: git output is consumed NUL-delimited (a crafted filename must not fabricate paths —
  demonstrated in § 7.2); git runs with hostile-config neutralised; every path opened or emitted
  resolves inside the target root with symlinks refused; secret-bearing paths are never read and
  emitted values are restricted to typed forms rather than free strings, so credentials cannot ride a
  fact into an LLM context or a state file; author and committer identities are never emitted;
  free-text drawn from the repo (commit subjects, file names, fragments) is length-capped,
  control-stripped, and marked as evidence the agent must not treat as instructions.
- **BR-4 — Rules are structured before they are prose (C9; § 4).** Draft rules exist as validated data
  (id, section, MUST/SHOULD tag, check, fact/answer citations) before any markdown. A shipped validator
  rejects untagged, uncited, unknown-id, or checkless rules; free text never bypasses it. Directive
  counts are **reported** against the 30/40/50/70 bands with only the 70 ceiling hard-failing — a soft
  numeric gate would invite writing to the number. The validator binds **new rules only**; pre-existing
  bullets pass through unvalidated (see BR-7). Oversized or over-nested input is refused, not parsed.
- **BR-5 — Cited checks are verified without executing anything (C6; § 5).** Verification is existence
  and matchability: cited paths verify by membership in the HEAD file set (absolute paths and `..`
  segments are dangling by construction, never filesystem probes); make targets and config/CI keys
  verify textually; check patterns are treated as fixed strings by default, with anything regex-shaped
  compiled-but-not-executed or bounded, so a pathological pattern cannot hang the tool. Commands mined
  from a target repo are never run — by the tool, and by the skill, whose residual "dry-run each cited
  check" instruction is withdrawn rather than merely delegated.
- **BR-6 — The emitted file teaches, not just commands (C1–C5).** It leads with Non-negotiables, groups
  rules in themed sections, opens each group with one WHY line, and attaches a DO/DON'T pair using a
  real repo fragment (≤3 lines, evidence-cited) where a group's meaning depends on local idiom. WHY and
  example lines are annotations outside the directive budget, and are themselves count-bounded so the
  file cannot double in length through annotation. Format conformance is **checked** on the emitted
  markdown (section order, lead block, tag presence, annotation placement) rather than produced by a
  renderer — detection keeps one code path and survives update mode, where a full-file renderer would
  clobber the user's own edits.
- **BR-7 — Update mode verifies exactly where it can and advises where it cannot (C7; § 3.3).**
  Generator-written CoCs persist their rule→citation envelope, so a later run re-verifies citations
  exactly and reports each rule verified, dangling, or changed before proposing any edit. **Scope
  boundary, stated rather than hidden:** the envelope lives in the user-local, uncommitted
  `~/.hercules/state/`, so exact re-verification holds for the same person on the same machine; a
  teammate, a fresh clone, or CI falls back to the advisory path, which § 3.3 bounds at ~a third of
  citations. The envelope
  carries a schema version from v1; an unreadable or older envelope degrades **audibly** to the
  advisory path rather than silently, and unknown fields survive a rewrite so an older ecosystem cannot
  destroy a newer one's data. For CoCs the generator did not write, a best-effort stale report
  (verified / dangling / unparsed, with the known false-positive classes filtered) informs the user and
  never auto-edits. Additions-only semantics hold throughout: existing bullets are never cut, merged,
  reformatted, or retro-fitted with annotations — gaps surface as report lines, never rejections.
- **BR-8 — It ships and stays shipped (§ 5).** Stdlib-3.9 tools with their own pytest islands and
  hygiene registration, wired per-recipe across all seven ecosystems, within unchanged token budgets
  and step-label promises. Prose and tool agree through an explicit contract-version handshake that
  refuses a mismatch with an actionable message. The token swap — scan mechanics leaving the
  coverage-map, tool contracts entering it — is **measured** as an acceptance criterion, not assumed;
  so is the claimed net token-economy gain. Shipped Python carries the fortnightly report's ≥85%
  mutation-kill expectation, and byte-exact golden-output tests are the intended way to meet it, since
  determinism makes exact output the business fact worth pinning.

## 7. Advisory review

Four advisors reviewed the first draft of this document — challenger, simplicity-advocate,
security-expert, maintainer — each returning findings only. Their verdicts reshaped § 6 from twelve
requirements to eight and changed three design decisions outright. What follows records what was
accepted, what was corrected, and what was rejected, so the spec phase does not re-litigate it.

### 7.1 Shipped-today vulnerability, independent of this work

The security review flagged the opencode target's empty `plugin_root` as an execution risk. Verified
by inspection, and it is broader than the review claimed: **every** opencode command ships
cwd-relative invocations — `python3 tools/project_reset.py`, `python3 tools/state_patch.py`,
`python3 hooks/frozen_tests.py` — while the other six targets emit an absolute plugin-root env var.
Those commands already run with the user's project directory as cwd, so a repository that ships its
own `tools/state_patch.py` has it executed with the user's authority. This is a defect in shipped code
today, not one this redesign introduces; the redesign only makes it fatal rather than incidental,
since steps 3/5/7 would become tool invocations. **It needs its own fix on its own branch**, and the
spec phase must require working invocation on all seven targets, not merely a recipe entry.

### 7.2 Accepted, with the evidence they forced

- **No demonstrated failure of the current skill** (challenger, blocking). Accepted in full; § 2 now
  carries the limitation and § 8 makes closing it the first task. This is the single biggest weakness
  of the research as delivered.
- **Circular criteria** (challenger, blocking). Accepted; § 1 now separates evidence-derived criteria
  from owner decisions instead of presenting all nine as findings.
- **The consistency goal is unfalsifiable as scoped** (challenger, blocking). Accepted; C9 now says so
  plainly, and § 6 makes no "achieves N%" claim.
- **Untested sensitivity of the stale scanner** (challenger). Accepted and *closed by measurement*: an
  injected-fault run now shows 5/5 detection (§ 3.3), plus the 62% unparseable ceiling stated.
- **Vacuous decay-sensitivity test** (challenger). Accepted and *closed by measurement* on django's
  real history — which then killed the feature: decay is out of BR-2 (§ 3.1).
- **The renderer exceeds its criterion** (simplicity, blocking). Accepted: BR-6 became a
  format *lint* on emitted markdown, not a generator. C9 asks for the same rule set, never identical
  bytes, and a full-file renderer would fight additions-only update mode.
- **Requirement inflation** (simplicity). Accepted: twelve BRs merged to eight, with safety clauses
  folded into the requirement they protect rather than parked in a separate one.
- **Secrets, symlinks, hostile filenames, ReDoS, git-config execution, author PII, envelope
  permissions** (security). All accepted into BR-3 and BR-5; the `.env` rule had indeed fallen out of
  the BRs, surviving only as skill prose — exactly the wishful-control class this redesign exists to
  replace. The hostile-filename finding was confirmed empirically (§ 3.4).
- **Envelope versioning and audible degradation; contract handshake; validator scoped to new content;
  probe-coverage visibility; the ≥85% mutation bar; a supersession clause for this document**
  (maintainer). All accepted into BR-1, BR-4, BR-7, BR-8 and the header.
- **BR-4 overturns a shipped invariant** (challenger). Accepted as a *decision to surface*, not a
  change to make silently — see BR-2's open decision.
- **Quotation integrity** (challenger). Accepted and corrected: the exemplar says "a DON'T/DO pair
  **where one fits**", and carries 11 pairs against 18 WHY lines. The truncation had inflated the
  standard the current skill was being judged against.

### 7.3 Rejected or corrected

- **"The mutation report is weekly"** (maintainer). Incorrect: the cron is weekly but
  `internal/release/ci/mutation_report.sh` exits early on odd ISO weeks, so it is fortnightly. The
  ≥85% kill expectation on shipped Python is real and was accepted.
- **"Drop the stale scanner entirely"** (simplicity). Rejected on evidence: the sensitivity test run
  after that finding shows 5/5 detection, so it is not code replacing prose that was fine. Its
  *sequencing* recommendation was accepted — it ships last.
- **"Collapse to one tool"** — the simplicity advocate probed and rejected this itself; recorded
  because the spec phase will be tempted: the split is a privilege boundary (scanner needs git, auditor
  needs none) that the per-tool hygiene allowlist can enforce.

## 8. What this research did not settle

1. **Run the current skill and measure its output.** Generate a CoC on two or three real repositories,
   twice each, and record: rule-set overlap between runs, directive count against the budget, dangling
   citations in the output, and whether dead conventions surface. Until this exists, the redesign rests
   on principle. If the baseline turns out good, the cheap fixes in § 7.2 (prose changes for C4/C5) may
   be the whole job.
2. **The owner decision in BR-2** — keep "always ask" on split patterns, or default to recent-dominant.
3. **Whether churn proxies for "conventions worth codifying"** — the C8 assumption, untested.
4. **Catalogue accuracy off the home repo** — validate against repos with ESLint/Prettier/YAML CI.
5. **A token baseline** for the current skill, so BR-8's "net gain" has a comparator.

## Appendix A — candidate architecture (hypothesis for the spec phase, not a commitment)

Two stdlib tools: **`coc_scan.py`** (emits the § 3.1–3.2 facts document; one shipped mode, with
granular probes as internal functions rather than frozen CLI surface) and **`coc_audit.py`** (validate
a draft envelope from stdin per BR-4/BR-5; lint emitted markdown per BR-6; stale-report an existing
CoC per BR-7). The two-tool split is a privilege boundary, not decomposition for its own sake: the
scanner needs `git log`, the auditor needs no git surface at all, and the hygiene table's per-tool
allowlist can then say so.

The skill's nine steps survive; steps 3/5/7 become tool invocations plus structured-envelope filling,
and the coverage-map's § Scan playbook shrinks **in the same commit** that wires the scanner, so the
skill never carries two authorities for one job.

**Suggested sequence** (smallest risk-retiring slice first): the draft validator alone — the scan side
is already de-risked by § 3.2's measurements, while every unproven bet (can the agent fill an envelope
reliably? does stdin-in-plan-mode work? does gating stop being wishful?) lives on the drafting side.
It also exercises every integration constraint at once. Then the coverage-map prose changes for BR-6,
which need no code at all. Then the scanner, then liveness. The renderer stays unbuilt unless observed
drift proves the lint insufficient.
