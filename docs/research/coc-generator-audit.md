# Code-of-conduct generator — research findings and draft requirements

This document records the research behind evolving the `code-of-conduct-generator` skill from prose-only
instructions into a scripted, testable pipeline. It contains: the criteria for a good code-of-conduct
(§ 1), a gap audit of the current skill against them (§ 2), feasibility-spike results with measurements
(§ 3), the boundary between script-resolvable facts and LLM judgment (§ 4), the integration constraints
any implementation must respect (§ 5), and draft business requirements (§ 6). Spike code is throwaway
and intentionally not committed; only its measurements appear here. The next phase turns § 6 into
technical specs; nothing in this document changes shipped content.

## 1. What makes a good code-of-conduct (criteria checklist)

A generated `code-of-conduct.md` is read by AI agents on every task, so its format is an
instruction-following problem, not a documentation-style preference. Criteria, each sourced:

- **C1 — Categorized.** Rules grouped in themed sections, most load-bearing first, with a
  `Non-negotiables` lead block. *Source: the skill's own § Output format; mirrored by the section
  structure of `CODE_OF_CONDUCT.md`.*
- **C2 — Atomic bullets, not prose.** One imperative rule per bullet, normatively tagged (MUST/SHOULD,
  RFC-2119 style). A rule that needs a paragraph is two rules or none. *Source: § Output format;
  coverage-map § U (MUST=CI-blocking, SHOULD=reviewer-enforced).*
- **C3 — Bounded volume.** Instruction-following degrades as simultaneous directives grow; the skill's
  own budget model (30–40 directives, 70 hard ceiling, ~150-directive adherence line for the delegate
  total) exists for this reason and must be *counted mechanically*, not estimated.
- **C4 — Per-group WHY.** Each rule group opens with one evidence-grounded reason. A WHY changes how an
  agent generalizes a rule to unlisted cases; it is annotation, not an extra directive. *Source:
  `CODE_OF_CONDUCT.md` line 10: rules follow "the rule in bold, a one-line WHY, and a DON'T/DO pair".*
- **C5 — DO/DON'T pairs with real fragments.** Contrastive examples mined from the repo itself (≤3
  lines, citable) beat abstract rules: they pin the rule's meaning to this codebase's idiom. *Source:
  the exemplar format of `CODE_OF_CONDUCT.md` (e.g. its naming rules cite `scope.mts` vs
  `variable-scope.mts` as DON'T/DO); external sources in § 1.1.*
- **C6 — Every rule enforced and evidenced.** A rule names its mechanical check inline and traces to a
  captured observation or an explicit user answer; anything recommended-but-unmet stays out of the
  file. *Source: SKILL.md Invariants; § Output format gate.*
- **C7 — Present-truth only.** A rule cites paths, commands, and checks that exist *now*; dangling
  references are defects detectable by machine. *Source: `CODE_OF_CONDUCT.md` § Documentation ("every
  written word describes the present state"); § 3.3 shows detection is mechanizable.*
- **C8 — Reflects the code that is alive.** Standards derive from the modules being worked on today,
  not from dormant legacy mass; where old and new patterns conflict, the recent-dominant pattern leads
  and the legacy one is named. *Source: owner direction; § 3.1 shows liveness is measurable.*
- **C9 — Reproducible.** Two runs at the same HEAD produce the same rule *set* (wording may vary;
  elements may not). Achievable only when facts, gating, and rendering are deterministic programs and
  free prose enters last. *Source: owner direction; `CODE_OF_CONDUCT.md` § "Executable over wishful".*

### 1.1 External sources

- **agents.md (OpenAI et al.)** frames the agent instruction file as "a README for agents": standard
  Markdown, focused sections (commands, style, testing), kept short enough to be loaded whole.
- **Anthropic's Claude Code best-practices guidance** recommends keeping `CLAUDE.md`-class files
  concise, human-readable, iterated like any prompt, and using emphasis sparingly for the rules that
  matter most — supporting C2/C3.
- **Instruction-capacity research** (many-instruction benchmarks; "lost in the middle" positional
  effects on long contexts) shows compliance drops as simultaneous constraints grow and mid-document
  content is recalled worst — supporting C3 and the Non-negotiables-first ordering of C1.
- **Few-shot/contrastive prompting literature** shows examples — including explicit negative examples —
  improve conformance over instructions alone, supporting C5.
- **Structured-output guidance** (JSON-schema-constrained generation) shows schema-forced intermediate
  steps remove format drift, supporting C9.
- **Google's engineering style guides** attach a rationale to rules and mark rules vs guidance
  normatively, supporting C4 and the MUST/SHOULD split of C2.

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

## 3. Spike results (throwaway scripts; measurements reproducible at the stated HEADs)

### 3.1 Churn heatmap (criterion C8)

Method: one `git log --since --name-only` pass over a 12-month window; per-file touch weights decayed
exponentially (half-life 90 days) **anchored to the HEAD commit's committer date, never wall clock**;
aggregated to directories at fixed depth; plus a top-N weighted file list. Canonical JSON out.

- **Hercules** (HEAD `5ed8976`, 50 non-merge commits in window): runtime **0.10 s**. Hottest:
  `src/content` (weight 0.105). Byte-identical across repeated runs.
- **django/django** (blob-less bare clone, 1123 commits in window, 1612 files touched): runtime
  **0.19 s**. Hottest: `django/contrib/admin` (0.107), `django/db/models` (0.035) — known-alive areas;
  49 of 268 touched directories classify dormant. Byte-identical across repeated runs.
- **Decay sensitivity** (half-life 30/90/180 d): top-5 ordering stable on Hercules; weights shift
  smoothly. Default 90 d is defensible; the parameter matters less than having decay at all.
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

- On `CODE_OF_CONDUCT.md` (559 lines): **63 verified, 5 flagged, 113 unparsed** (non-verifiable kinds:
  concepts, commands, placeholders). All 5 flags are false positives in three *identifiable* classes:
  DON'T/DO example names (`scope.mts`), npm import specifiers (`js-tiktoken/lite`), and files the text
  says will be created (`code-of-conduct.md`). A well-maintained doc yields zero true danglings — the
  scanner works, and its noise is classifiable.
- Consequence: for **generated** CoCs the rule→citation link must ship as machine data (a citation
  envelope persisted to state), so update-mode verification is exact re-checking, never prose
  re-parsing. Best-effort parsing is only for CoCs the generator did not write, presented as a report
  for a human decision, never auto-acted-on.

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

Outcome-phrased; each traces to findings above. BR-1..5 are the evidence layer, BR-6..9 the drafting
layer, BR-10..12 the update/delivery layer.

- **BR-1 (C9, § 3.1–3.2)** — Evidence collection is a shipped program: at the same HEAD, two runs
  emit byte-identical canonical facts JSON. Proven feasible at < 0.2 s even on a 1100-commit/year repo.
- **BR-2 (C8, § 3.1)** — Facts include a churn heatmap over a configurable window (default 12 months)
  with recency decay anchored to the HEAD commit date; alive/dormant is computed against the full HEAD
  tree; renamed-away paths are excluded; generated trees are tagged.
- **BR-3 (C8, § 3.1)** — The scan emits a bounded, weighted top-N file list; the drafting agent
  samples its reads from this list, never from tree-walking.
- **BR-4 (C8)** — When two patterns serve one concern, the facts state each candidate's recent and
  overall share; the recent-dominant pattern is the recommended default, the other is named legacy,
  and a tie remains a user question. Conflicting values are never averaged.
- **BR-5 (C6, § 3.2)** — Every fact carries an id, a confidence tag, and a citation; absent evidence
  produces no fact, and cap breaches degrade to explicit unknowns that become interview questions.
- **BR-6 (C9, § 4)** — Draft rules exist as structured data (id, section, MUST/SHOULD tag, check,
  fact/answer citations) before any prose; a shipped validator rejects untagged, uncited, unknown-id,
  or checkless rules and counts directives against the 30/40/50/70 bands. Free-text never bypasses it.
- **BR-7 (C1–C5)** — The emitted file leads with Non-negotiables, groups rules in themed sections,
  opens each group with one WHY line, and attaches a DO/DON'T pair using a real repo fragment (≤3
  lines, evidence-cited) wherever a group's meaning depends on idiom. WHY and example lines are
  annotations outside the directive budget.
- **BR-8 (C9)** — The final markdown is rendered deterministically from the validated structure:
  identical envelope, identical bytes. LLM sentences enter only as fields inside that structure.
- **BR-9 (C6, § 5)** — Cited checks are verified by existence and matchability (paths, patterns, make
  targets, textual config/CI keys); mined commands are never executed.
- **BR-10 (C7, § 3.3)** — Generated CoCs persist their rule→citation envelope to the existing
  state file, so update mode re-verifies citations exactly; a later run reports each rule as verified,
  dangling, or changed before any edit is proposed.
- **BR-11 (C7, § 3.3)** — For a CoC the generator did not write, update mode produces a best-effort
  stale report (verified/dangling/unparsed, with the three known false-positive classes filtered);
  the report informs the user's decisions and never auto-edits. Additions-only update semantics stay.
- **BR-12 (§ 5)** — Everything ships within existing constraints: stdlib-3.9 tools with their own
  pytest islands and hygiene registration, per-recipe wiring for all seven ecosystems, unchanged token
  budgets, unchanged step-label promises, and a net token-economy gain (facts the scripts compute are
  facts the model no longer spends tokens discovering).

## Appendix A — candidate architecture (hypothesis for the spec phase, not a commitment)

Two stdlib tools: **`coc_scan.py`** (subcommands `all|size|configs|history|churn`; emits the § 3.1–3.2
facts document) and **`coc_audit.py`** (modes `draft` — stdin envelope validation per BR-6/BR-9;
`render` — deterministic markdown per BR-8; `existing` — stale report per BR-11). The skill's nine
steps survive; steps 3/5/7 become tool invocations plus structured-envelope filling, and the
coverage-map's § Scan playbook shrinks to what stays with the agent. The spec phase owns the exact
fact schema, envelope grammar, CLI contracts, and test-island layout.
