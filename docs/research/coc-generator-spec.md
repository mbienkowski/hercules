# Code-of-conduct generator — technical specification

Derived from `coc-generator-audit.md` (findings BR-1..BR-8) and the multi-repo validation recorded in
§ 2 below. Like its parent, **this is a dated record**: it specifies what to build, and is superseded
by the code once built. It is not updated to track the shipped skill.

Slice 1 has shipped (`coc_audit.py draft`, commit `e50d8e3`); § 5 specifies it as built so the
contract is written down in one place, and §§ 6–7 specify what remains.

## 1. Scope

Turn the generator's evidence and gating from prose instructions into two shipped stdlib tools, and
upgrade the emitted file's format. Out of scope: the LLM's judgment (naming design patterns, choosing
example fragments, writing rule sentences), which stays where no test can rot.

| Tool | Mode | Status |
|---|---|---|
| `coc_audit.py` | `draft` — validate the rules envelope | **shipped** |
| `coc_audit.py` | `lint` — check emitted markdown's shape | § 6.1 |
| `coc_audit.py` | `existing` — stale-scan a foreign CoC | § 6.2 |
| `coc_scan.py` | `all` — emit the facts document | § 7 |

## 2. What the validation established

Six repositories, chosen for stack diversity and measured directly: `pallets/flask` (Python,
5545 commits), `expressjs/express` (JS, 6158), `spf13/cobra` (Go, 1106), `vuejs/core` (TS monorepo,
7146), `django/django` (Python monolith, bare clone), and Hercules itself.

**2.1 The v1 catalogue was Node-and-Python shaped, as the audit's advisory review predicted.** Rebuilt
per § 7.3 and re-measured, facts found per repo went 8→14 (flask), 9→12 (express), 9→12 (cobra),
15→17 (vue), 17→19 (Hercules). Three distinct causes, each a design requirement:

- **Config lives inside manifests.** flask configures ruff, mypy, pyright, pytest and coverage in
  `pyproject.toml` `[tool.*]` sections — v1 found none of them. At the 3.9 stdlib floor there is no
  TOML parser, but a `[tool.<name>]` section header is line-anchored and reads reliably without one.
  This single fix accounts for most of flask's gain and applies to any modern Python repo.
- **Exact filenames miss variants.** express uses `.eslintrc.yml`; v1 listed `.eslintrc`,
  `.eslintrc.json`, `.eslintrc.js` and missed it. Probes must glob.
- **Whole ecosystems were absent.** cobra's `go.mod` and `.golangci.yml` matched nothing at all.

**2.2 A bare repository silently reported an empty one.** `git ls-files` reads the index, which a bare
clone has none of, so django produced zeros rather than an error — the worst failure mode available.
Falling back to `git ls-tree -r HEAD` recovers all 7082 files. **Requirement:** resolve the file list
through that fallback, and refuse rather than emit zeros if both come back empty.

**2.3 Ghost paths matter enormously in some repositories and not at all in others.** Re-measured with
the shipped scanner — the exploratory spike mis-parsed git's `-z` output and inflated these badly, so
its figures are withdrawn — touches to paths absent at HEAD are: flask 0%, cobra 0%, vue 0.6%,
django 0.6%, express 3.1%, **Hercules 44%**. A repository that has never moved its layout has no
ghosts at all; one that has restructured has little else. The HEAD intersection is therefore not
tidying: without it, nearly half of this repository's own ranking would be code that no longer
exists, while a scan validated only on the calmer repositories would have shown no reason for it.

**2.4 Dormancy must be computed against the full HEAD tree.** The shipped scanner reports django as
255 directories, 86 dormant and 126 alive — the dormant ones including `tests/template_backends`
(29 files, zero touches in 12 months). Untouched mass is invisible to `git log` by construction, and
it is precisely the mass the heatmap exists to expose.

**2.5 Decay is worthless; two plain windows are not.** Re-measured on django's real 12 months at
half-lives 30/90/180/365 d, the top-10 directory set is 9–10 of 10 identical across the whole range.
Decay bought no discrimination and cost a tuning parameter plus auditability. Two counts — a long
window and a recent one — give the recent-vs-overall shares the conflict rule needs, and
"17 touches this quarter" is debuggable in a way a decayed 0.105 is not.

**2.6 Three further facts are cheap and ground numbers that would otherwise be invented.** Module-size
percentiles (flask p90 682, express 392, cobra 1024, vue 757, Hercules 430), TODO/FIXME density, and
commit-signature presence all compute in seconds. A size rule can then cite the repo's own p90 rather
than a default. Signature state distinguishes signed from unsigned but **not** valid from invalid
(`%G?` returns `E` without the key) — the fact must say "present", never "verified".

## 3. The deterministic/judgment boundary, derived

The coverage map holds **192 points across 30 sections** (A–Z, AA–AD). Classifying each against what
§ 2 measured:

| Class | Points | What it means |
|---|---|---|
| **Fact** — the scan resolves it outright | ~35 (18%) | Config presence, lockfiles, CI, commit convention, merge shape, tags, coverage/mutation config, module-size percentiles, TODO density |
| **Sample** — the scan narrows, the agent reads | ~20 (10%) | Naming conventions, comment policy, test structure — the heatmap's top-N list selects what to read |
| **Judgment** — the agent decides, no script helps | ~95 (49%) | Layering, error taxonomy, concurrency, API contracts, observability, most of D/E/F/K/L/N/O |
| **Question** — only the user knows | ~42 (22%) | Thresholds, policy, autonomy boundaries, retention, compliance posture |

The strongest sections are **Q (build/release)** — CI gates, commit convention, branching, SemVer all
resolve as facts — and **R (dependency)**, **AC (developer experience)**, **AD (ownership)**. The
weakest are **D, E, K, L, N, O**, which are almost entirely judgment.

**Correction the spec makes to the coverage map:** several points in **S** and **T** — protected
branches, required reviewers, self-merge policy — are **not locally observable at all**. They live in
forge settings, not the repository. The map currently implies a scan signal for them. They are
questions, and the scan must not pretend otherwise.

The scanner therefore resolves under a fifth of the map deterministically. That fifth is the part
every repository has, so it carries disproportionate weight — but the interview and the reading remain
the majority of the work, and the spec claims nothing more.

## 4. Shared conventions

**Exit codes** (both tools, matching `project_reset.py`): `0` ok · `1` refused (findings, or a rule of
the tool rejected the input) · `2` contract mismatch · `4` internal/unreadable. Every path prints one
JSON object carrying `contract` and `mode`, refusals included.

**Contract handshake.** Each tool declares `CONTRACT_VERSION`; the skill passes `--contract N`; a
mismatch refuses with "Update the plugin, then run this again." Prose and tool ship together per
ecosystem but seven ecosystems update independently, so the handshake is required, not optional.

**Determinism.** Canonical JSON (`sort_keys`), lists ordered by a content-derived key, and **no
timestamps or elapsed-time fields** — the only run-varying value is `head`. Determinism is defined per
commit, and byte-identity is asserted by test.

**Git invocation** (scanner only). Always `git -C <root> -c core.quotePath=false`, output consumed
NUL-delimited (`-z`). A crafted filename otherwise fabricates paths: the v1 spike emitted two phantom
directories from one file named `src/eve<newline>il.py`. Never `shell=True`.

**Untrusted input.** The target repository is attacker-controlled. Commit subjects, file names, and
mined fragments are length-capped, control-character-stripped, and carried in fields the skill
presents as evidence, never as instructions. Author and committer identities are never emitted.
Paths matching secret-bearing patterns (`.env*`, `*.pem`, `*id_rsa*`, `*.key`) are never read, and
emitted values are typed (booleans, counts, version strings, enumerated names) rather than arbitrary
strings lifted from a file.

**No execution, ever.** Neither tool runs a command mined from a target repo, and the skill's residual
"dry-run each cited check" instruction is withdrawn rather than delegated. Verification is existence
and matchability only.

## 5. `coc_audit.py draft` — as shipped

Reads one JSON envelope on stdin (`--contract 1`), bounded at 1 MiB, and is a pure function of it: no
path opened, no subprocess. Envelope and reply are specified in `coverage-map.md § Rules envelope`.

Refuses: a rule with no id, a duplicate id, a tag outside `MUST`/`SHOULD`, no named check, no
citation, a citation naming no evidence kind, or a citation naming evidence the envelope does not
carry. Reports `directives`, `band`, `bands`, and `unused_evidence`. Only the ceiling (70) refuses on
count; the intended (40) and large (50) bands report. A gate at the intended band would be answered by
merging two rules into one longer bullet — buying a number, costing a reader.

## 6. `coc_audit.py` — remaining modes

### 6.1 `lint` — the emitted file's shape

Stdin `{contract, markdown}`. Checks what a parser can see, and **only over content this run wrote**:
the `## Non-negotiables (MUST)` lead block exists and is first; section order matches the declared
order; every rule bullet carries a `MUST`/`SHOULD` tag; each themed group opens with one `**WHY:**`
line; `**DON'T:**`/`**DO:**` appear as a pair or not at all; annotation lines stay within their cap
(§ 6.3). Reports findings with line numbers; exit 1 if any.

Chosen over rendering the file. C9 asks for the same rule *set*, never identical bytes, and a
full-file renderer would fight additions-only update mode by clobbering a user's own edits. Detection
is one code path; generation would be two.

### 6.2 `existing` — stale-scan a foreign CoC

`--file <path> --root <root>`. Extracts backticked tokens, classifies them (path / make target /
placeholder / other), and verifies the verifiable kinds: **paths by membership in the HEAD file set,
never by touching the filesystem** — an absolute path or any `..` segment is dangling by construction,
which makes traversal impossible rather than merely forbidden. Make targets verify against a textual
`Makefile` parse.

Measured behaviour to preserve (audit § 3.3): 5 of 5 injected rename/removal faults detected;
≈7% false-positive rate on parseable tokens, all in three filterable classes (example names in
DO/DON'T pairs, package import specifiers, files the text says will be created); **62% of tokens are
unverifiable kinds**, so this covers about a third of a document's citations. The report states that
ceiling. It never auto-edits.

### 6.3 Annotation budget

WHY and DO/DON'T lines cost no directive, which leaves nothing bounding their volume — and the
research behind the directive budget is about total volume, not directive count alone (the exemplar
is 559 lines against ~200-line guidance). Therefore: at most one WHY line per group, at most one
DO/DON'T pair per group, each fragment ≤3 lines. `lint` enforces these; `draft` counts neither.

## 7. `coc_scan.py` — specification

### 7.1 Surface

`python3 coc_scan.py all --root <path> --contract 1 [--months 12] [--recent-months 3] [--depth 2]`.
One shipped mode. The granular probes stay internal functions: every step of the skill runs `all`, and
a subcommand is a frozen public contract needing spec, tests and a version bump for no present caller.

Hygiene declaration: `{"writes": False, "fails": "closed", "shells_to_git": True}` with a **per-tool**
git allowlist `{ls-files, ls-tree, log, tag, rev-parse}`. The allowlist in
`tests/scripts/tools/test_tool_hygiene.py` is a single module-level set today containing `rm`; it must
become per-tool first, red-first, so the scanner cannot inherit a delete verb.

### 7.2 Output

```json
{ "schema_version": 1, "contract": 1, "head": "<sha>", "root_kind": "worktree|bare",
  "files_at_head": 589, "probes_attempted": 27, "probes_matched": 10,
  "facts": [ {"id","claim","value","confidence","citations"} ],
  "liveness": { "months": 12, "recent_months": 3,
                "directories": [ {"path","touches","recent_touches","share","recent_share",
                                  "files_at_head","status","generated"} ],
                "top_files":   [ {"path","touches"} ],
                "ghost_touches_dropped": 1104 },
  "unknowns": ["hist.release.cadence"], "truncated": false }
```

- **Fact id**: `<domain>.<topic>.<name>`, derived from content, never from enumeration order.
- **Confidence**: `inferred-high` (a config states it) · `inferred-medium` (dominant in the sample) ·
  `inferred-low` (weak or split) · `unknown` (cap hit or no signal → becomes an interview question).
- **Citation kinds**: `{kind:file,path,line?}` · `{kind:count,pattern,matched,sampled}` ·
  `{kind:commit,hash}` · `{kind:tag,name}`.
- **`status`**: `alive` (touched in the recent window) · `cooling` (touched in the long window only) ·
  `dormant` (present at HEAD, untouched) — the three-state split § 2.4 showed is needed.
- **`probes_attempted` vs `probes_matched`** exist so a stale catalogue is visible per run. Without
  them "not probed" and "probed and absent" are the same output, and BR-1's "absent evidence yields no
  fact" makes catalogue rot indistinguishable from a correct negative.

### 7.3 Behaviour

1. **Resolve the file list** — `ls-files -z`, falling back to `ls-tree -r -z HEAD`; `root_kind`
   records which. Both empty → refuse (§ 2.2).
2. **Probe configuration by glob** against that list (§ 2.1), covering Node, Python, Go, Rust, JVM and
   Ruby manifests, workspace markers, lockfiles, lint/format/type/test config, CI, containers,
   CODEOWNERS, dependency automation, hooks, and governance documents.
3. **Read manifest-embedded config** — `pyproject.toml` `[tool.*]` headers by line-anchored scan;
   `package.json` dependency names and `engines`/`workspaces` by JSON parse. YAML and TOML *values*
   stay out of reach at the 3.9 floor; any check over them is textual and labelled `"checked":
   "textual"`.
4. **Mine history** — commit-subject convention with its share and scopes, merge shape, tags. Measured
   classifications: flask free-form (0.00), cobra mixed (0.35), express mixed (0.77), Hercules
   conventional (0.88), vue conventional (0.93).
5. **Compute liveness** — two windows, HEAD intersection, full-tree dormancy, generated-tree tagging
   (§ 2.3–2.5).
6. **Measure grounded numbers** — module-size percentiles and TODO density over a bounded sample of
   code files (§ 2.6), so a size rule cites the repo instead of a default.
7. **Bound everything** — caps on commits examined, distinct paths tracked, files read, and wall
   clock. A breach sets `truncated` and moves the affected ids to `unknowns`; it never stalls and
   never silently truncates.

### 7.4 Tests (`tests/scripts/tools/coc_scan/`)

`conftest.py` builds a synthetic git repo in `tmp_path`: configs across two ecosystems, scripted
history with a known convention, one alive and one dormant module, a renamed-away path, a generated
tree, and a file whose name contains a newline.

| File | Defends |
|---|---|
| `test_contract.py` | Contract refusal; one JSON object on every path |
| `test_file_resolution.py` | `ls-tree` fallback for a bare repo; refusal when both are empty |
| `test_config_probes.py` | Glob variants match; manifest-embedded `[tool.*]` found; absent config invents no fact; `probes_attempted` exceeds `probes_matched` |
| `test_history.py` | Convention classification at known shares; merge shape; tags |
| `test_liveness.py` | Ghost paths dropped; dormant directory present with zero touches; generated tree tagged; alive/cooling/dormant boundaries |
| `test_hostile_input.py` | A newline in a filename fabricates no path; author identity never emitted; secret-bearing paths never read |
| `test_determinism.py` | Two runs at one HEAD are byte-identical |
| `test_bounds.py` | Cap breach sets `truncated` and yields `unknowns` rather than stalling |
| `test_mutation_guards.py` | Share arithmetic, id derivation, status thresholds driven directly |

Byte-exact golden output is the right assertion here and is consistent with the house rule against
pinning wording: for a tool whose promise *is* determinism, the exact bytes are the business fact.
This also carries the shipped-Python mutation expectation (≥85% kill on the fortnightly report), which
float-free integer counting makes attainable.

## 8. Phasing

Each phase is one Conventional Commit, red first, with `make build` and the `dist/` diff in the same
commit.

| Phase | Content | Risk retired |
|---|---|---|
| ✅ 1 | `coc_audit draft` + island + 7 recipes + step 7 + `toolReferences` guard | Envelope gating works end to end |
| 2 | Coverage-map format rules: per-group WHY, DO/DON'T pairs, annotation caps (§ 6.3). **No code.** | Closes C4/C5, the audit's only ❌ that needs no tooling |
| 3 | Per-tool git allowlist in `test_tool_hygiene.py` (§ 7.1) | Prerequisite; scanner cannot inherit `rm` |
| 4 | `coc_scan all` + island + recipes + skill step 3 | The evidence layer |
| 5 | `coc_audit lint` + skill wiring | Format conformance becomes mechanical |
| 6 | `coc_audit existing` + update-mode wiring; envelope persistence with `schema_version` | Update mode verifies instead of re-reading |

Phase 2 before any scanner work: it is the cheapest fix for a real gap, and if the necessity baseline
(§ 10) shows the current skill already drafts well, phase 2 may be most of the value.

## 9. Budgets, versioning, and update mode

**Token budget.** SKILL.md ≤3000, coverage-map ≤6600, both immovable without a direct instruction to
raise them. Phase 1 spent some headroom on § Rules envelope and step 7 and still passes. Phase 4 must
fund the scanner's contract by shrinking § Scan playbook **in the same commit** — otherwise the skill
carries two authorities for one job and pays for both. If it will not fit, the answer is trimming, and
the overage is surfaced with options. Measure, never assume.

**Envelope persistence.** The rule→citation envelope persists to `~/.hercules/state/{slug}-coc.json`
carrying `schema_version` from v1. `~/.hercules` is shared across all seven ecosystems, which update
independently, so: unknown fields survive a rewrite (an older install cannot destroy a newer one's
data), and an unreadable or older envelope degrades **audibly** to the § 6.2 advisory path — never
silently, since exact re-verification is the whole value being lost. The store is user-local and
uncommitted, so a teammate, a fresh clone, or CI necessarily falls back; the skill says so rather than
implying a guarantee it cannot keep.

**Update mode.** Validation and the § 6.3 format bind **new rules and new sections only**. Pre-existing
bullets — hand-written, or generated before the envelope existed — carry no ids, tags or citations by
construction; validating the merged document would refuse every legitimate update. They pass through
unvalidated and unreformatted, and gaps surface as report lines, never rejections. Additions-only
holds: nothing existing is cut, merged, reordered, or retro-fitted with annotations.

## 10. Open decisions

1. **Necessity baseline (unresolved, and the largest).** The audit established feasibility and
   conformance to owner-chosen criteria, never that the current skill produces bad output — it was
   never run. Generating a CoC on two or three real repositories, twice each, and recording rule-set
   overlap, directive count, and dangling citations would either justify phases 4–6 or shrink them to
   phase 2. Recommended before phase 4.
2. **Conflict resolution (owner's call, unchanged from BR-2).** Recent-dominant defaulting overturns
   the shipped invariant "two live patterns for one concern → a question, never majority rule".
   Recency weighting is majority rule with a window. The scan can compute the shares either way; what
   it does with them is a product decision, not a measurement.
3. **Churn as a proxy.** § 2.4 shows liveness is measurable; nothing shows churn-hot code is
   convention-worthy code — hot can mean deprecation, reformatting, or removal. Accepted as an
   assumption, flagged as untested.
4. **Not in this work:** every opencode command invokes tools cwd-relative (`python3 tools/….py`)
   while the other six targets emit an absolute plugin root, and those commands run with the user's
   project as cwd. That is a shipped defect needing its own branch.

## 11. What shipped differently from this specification

Recorded here rather than edited into the sections above, which stay a dated record of what was
planned. Each of these was decided while building, for a reason the plan could not have known.

- **Three tools, not two, grouped in a directory.** `tools/code_of_conduct/` holds `coc_scan.py`,
  `coc_audit.py` and `coc_lint.py`. § 6.1's `lint` and § 6.2's `existing` became one tool: both
  answer *what is wrong with this document*, and splitting them across two modes of the gate meant a
  reader had to run two things to find out. The gate keeps one job — may this draft be written at all.
- **Shape binds a draft, and only informs about a document that already exists.** Running the linter
  against this repository's own code-of-conduct reported 100+ untagged bullets: a list of edits that
  § 9's additions-only rule forbids. Shape findings on an existing file now sit in `shape_notes`,
  outside `findings`, and do not decide the exit code. A rotted citation is a finding either way.
- **The linter runs again after the write**, against the file on disk. § 6.1 checked the draft only,
  which is not evidence about the bytes that landed.
- **`coc_audit` stayed pure; `coc_lint` carries the git surface.** § 5's purity claim survives on the
  gate alone — the tool that reads a repository is the one that needed `ls-files`.
- **The ghost-path figures in § 2.3 were withdrawn and re-measured** against the shipped scanner; the
  exploratory spike had mis-parsed git's output. The section carries the corrected numbers.
- **BR-2 resolved as "always ask".** The scan reports a split convention under `conflicts` with each
  side's file share, recent share and an example file, and names no winner — no `recommended` field,
  `resolution` always `question`, pinned by test. Recency is a good argument and a bad decision
  procedure: code is edited while a convention is being adopted and equally while it is being torn
  out, and nothing in the scan distinguishes those. Defaulting is also the asymmetric mistake — adding
  a default later is one line, while removing one after code-of-conducts were generated from it
  leaves every such file carrying a rule nobody chose. The shipped invariant stands unchanged.
- **Rivalry is stated, not inferred.** Grouping tools by the middle of their fact id read
  `cfg.test.pytest` and `cfg.test.vitest` as a contradiction, when a repository holding Python and
  TypeScript needs both. Competing tools are named explicitly.
- **Idiom markers are scoped to the files the question is about.** Unscoped, any file that mentions a
  marker counts as using it — this scanner's own source names every pattern it looks for, and
  reported itself as the repository's one holdout.
- **Per-tool git allowlists** (§ 7.1) landed as planned, and the hygiene scan additionally learned to
  follow a tool's hardened git wrapper — routing every call through one place is the better shape, and
  a scan that only understood argv-at-the-call-site would have pushed tools away from it.
