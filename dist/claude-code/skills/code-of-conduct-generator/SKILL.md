---
name: code-of-conduct-generator
description: Generate or update a project's code-of-conduct — the single source of project standards every Hercules agent reads. Use on first run in a repo, or when a standard is missing.
---

# Code-of-Conduct Generator

The code-of-conduct is the highest-leverage file — every agent reads it, so careful answers compound.
The generator drafts it **evidence-first**, then proves each rule before the user sees it. The detailed
scan tactics and output format live in the companion `coverage-map.md`; this file is the spine.

## Invariants

- The **target repository's** enforced standards only — never Hercules's process internals (phases,
  commands, state, spec-first flow, contributor rules).
- Only what is enforced **today**; recommended-but-unmet is offered in chat, never written to the file.
- Never average two conflicting values.

## Preconditions

- Must run inside a git repository — else **stop**: tell the user to re-open Hercules in the target
  repository and re-invoke.
- Resolve the **target** repo per `hercules-reference § Code-of-conduct resolution`, not the launch
  directory. If Claude was opened away from the code, or several roots are candidates, list them
  (`ls`, `git rev-parse --show-toplevel`) and ask which repo the CoC is for.
- Run every scan, `find` and git command against that root (`git -C <root>`), never bare `.`.

## Method

1. **Plan mode & mode** — call `EnterPlanMode` first, before any scanning; give a chat summary of the
   flow and offer **Quick** (small/low-stakes default: scan → a few questions → draft → gate → review →
   commit) or **Thorough** (adds the coverage-map gap pass and an advisor critical-review pass). Name the detected
   root so the user can correct it.
2. **Find existing CoC** — `find <root> -maxdepth 2 -iname 'code[-_ ]of[-_ ]conduct.md'` across
   root/`.github/`/`docs/`, any capitalization. **Whatever it finds is the path Step 8 writes** —
   the repo's own spelling, its own directory, in place. Never a second file beside it.
   - One match → **update mode**, writing back to that exact path. A repo spelling it
     `CODE_OF_CONDUCT.md` keeps that name; emitting the default alongside would leave two
     standards files, and on a case-insensitive filesystem it silently clobbers the wrong one.
   - More than one → **never silently pick**; list every match and confirm which one is the target.
     This is the only naming question worth asking, because the repo itself is ambiguous.
   - None → default `code-of-conduct.md` in the root. The default applies **only** here.
   - Record the resolved path once and carry it verbatim through Steps 7, 8 and 9.
   - But a lone `.github/` behavioural Contributor Covenant is not an engineering standard: treat
     it as none and create a separate file.
3. **Scan** — `python3 ${CLAUDE_PLUGIN_ROOT}/tools/code_of_conduct/coc_scan.py all --root <root> --contract 2`.
   - It reports what the repo declares, what its history shows, which directories are alive, cooling,
     dormant or generated, a ranked file list to read from, and the `arch.*` facts: file families
     (extension points), the import graph, chokepoints, entrypoints, config consumers —
     `arch.import_coverage` names the languages where that reading is yours instead.
   - Non-zero exit: relay its message and stop — never hand-scan around a refusal.
   - Then the **§ Scan playbook** for what it cannot decide: read the ranked sample and the `arch.*`
     facts, and record each pattern, idiom or architectural mechanism you confirm as an
     **observation** `{id, path}` naming the file that shows it — the third evidence stream, beside
     facts and answers. Reconcile config against code; turn every `unknown` into a Step-4 question.
4. **Questions** — one batch, one message, no trickle.
   - **Never fewer than 5**, up to 8+ for a large or polyglot repo; Quick asks this many too.
   - **Every `conflicts` entry becomes one question**, quoting both sides' `file_share` and
     `recent_share` and naming an `example` file each. Never pick for the user: recent work says
     where a team is going and equally where it is retreating from, and the scan cannot tell those
     apart. The shares are the argument; the answer is theirs.
   - Ask *intent*, resolve split patterns, force an explicit accept/decline on each recommended gate.
   - Recommend in chat: branch (not line) coverage, a mutation gate where a mutation tool exists,
     architecture tests via the framework's standard tool, a linter + formatter.
   - Accepted-with-tooling becomes a rule; the rest stay chat advice.
5. **Draft** — rules only from the three evidence streams (facts, answers, observations), per
   **§ Output format**.
   - Orientation first (what the repo is, the edit→verify loop, what the tiers mean), then themed
     sections — Architecture naming the real mechanisms, how the repo is extended, Testing, Quality
     Gates, Security & Data, Delivery — every reason in one closing Why section.
   - Every heading (`##`, or `###` where a section has concerns worth naming) opens with a 1–3
     sentence summary, then one `MUST:`/`SHOULD:`/`AVOID:`/`NEVER_DO:` header per posture owning a
     numbered run. Plain text — no markup.
   - Each directive is **multi-line**: first sentence is the rule and reads alone, then the lines
     that explain it, then `Check:`. Add a fenced code block wherever the real fragment teaches
     faster — the engine's config, a recipe entry, the destinations one source lands at.
   - **Never past eight directives under one heading**; split at the first clear boundary, often
     well before. Give each concern a `###` and its own summary, and carry it in the envelope's
     `subsection`.
   - Orientation, summaries, code blocks and the Why section cost no directive.
6. **Gap pass & critical review** (Thorough) — run `coverage-map.md` once as a stack-gated gap detector.
   - Each load-bearing omission is a chat recommendation: accept → rule, decline → absent.
   - Offer highest-value first, never past the directive budget.
   - Then one `challenger` reviews the draft per `hercules-reference § Sub-agent consent`, carrying the
     A2A § Agent-Injected Core plus the observations; a trio is opt-in, or automatic for a contested
     repo per `hercules-reference § Debate protocol`. Advisors return findings only, never write.
   - Quick runs a light platitude/no-evidence self-scan instead.
7. **Gate & present** — the gate is a program, not a promise.
   - Build the envelope: each rule as `{id, section, tag, text, check, citations}` plus the `facts`,
     `answers` and `observations` it may cite — `fact:<id>`, `answer:<id>`, `code:<observation-id>`
     (**§ Rules envelope**).
   - Pipe it to `python3 ${CLAUDE_PLUGIN_ROOT}/tools/code_of_conduct/coc_gate.py draft --contract 2`.
   - **Exit 0 ships.** Any other exit: fix or drop what its `findings` name and re-run — never argue
     past it, never hand-wave a rule it refused.
   - It judges tag, check, citations, unique id, observation paths, and the directive count. The rest
     stays yours: each rule reads exactly one way and conflicts with no other.
   - Lay the rules out as markdown, then `python3 ${CLAUDE_PLUGIN_ROOT}/tools/code_of_conduct/coc_lint.py
     --contract 2` with `{"contract":2,"markdown":"…","paths":[each observation's path],
     "families":[each `arch.families` path]}` on stdin — it checks the shape, holds every
     observation path against HEAD, refuses a `Check:` that names nothing runnable, refuses an
     unverifiable universal claim, and names any family the document never mentions. It reports
     what to fix, it never fixes it. Apply its findings and re-run until clean.
   - Present with a short summary (top standards, added, conflicts, dropped, and the band when past
     `intended`), surfacing only the ~5 genuine decisions — never a long list to curate.
   - Feedback applies **surgically** with a diff; regenerate wholesale only if the user reopens the
     scope, and re-gate only what changed.
8. **Approve & write** — on approval: `ExitPlanMode` (`auto`) → write atomically (temp + rename).
   Write to **the path Step 2 resolved**, overwriting it in place — no rename, no second file, no
   question about where it goes. The temp file lands in the same directory so the rename is atomic
   on one filesystem.
   The generator **never creates or edits any file besides that one** — offer the reference line
   for `CLAUDE.md` in chat, naming the resolved path; adding it is the user's edit.
   Then **re-run the linter against the file on disk**
   (`… coc_lint.py --contract 2 --file <coc> --root <root>`): the draft that passed is not proof about
   the bytes that landed. Fix and re-run until clean.
9. **Review & commit** — show the file and ask the user to review it. On their go-ahead, **stage then
   commit** exactly the code-of-conduct file — `git add -- <path>` then `git commit -m … -- <path>` —
   so an untracked new file commits cleanly and the user's other staged work is never reset or swept
   in; use the mined commit convention or a plain imperative subject.
   Attribution lives in the commit message, never in the file. Offer a push; never push automatically.
   No go-ahead → reply: "Left uncommitted: {path}. Say 'commit' when ready, or edit first."

## Update mode

- **The existing file is the output file.** Update mode edits it where it lives, under the name the
  repository already uses. Never emit a differently-named copy and never migrate the old one.
- **Read it mechanically first:** `python3 ${CLAUDE_PLUGIN_ROOT}/tools/code_of_conduct/coc_lint.py
  --contract 2 --file <coc> --root <root>`. Its `findings` are rotted references — wrong whoever
  wrote them. Its `shape_notes` are **not a task list**: restyling an existing rule is the edit
  additions-only forbids, and an existing document may be in any format at all.
- A `dangling` entry is a **question for the user, never an edit** — the rule may be right and the
  path merely moved.
- Where the state file holds a previous run's envelope, re-verify those citations exactly instead.
  An unreadable or older envelope **says so in chat** and falls back to the report.
- **Additions only:** never rename, reorder, delete or restructure existing sections or rules on the
  generator's own initiative. Exceptions: a critical-review-proposed drop after an explicit yes, and
  any edit the user directs.
- **Append inside a run; never renumber.** A new directive joins the END of its tier's numbered run,
  so no existing line changes. Inserting one mid-run would renumber every directive after it — a
  mechanical edit to rules nobody asked to touch, and the loss of every number a review or an issue
  ever cited. Where the ordering genuinely matters, say so and let the user decide.
- **The group cap binds new rules, not old ones.** If appending would push a heading past eight,
  propose a `###` split as a question — never perform one, because splitting moves existing rules.
- Existing rules are never retro-fitted with tags, summaries, checks or reasons, and **never
  submitted to the gate** — they predate it, so validating them would refuse every legitimate
  update. New rules and new sections meet the full bar.
- Gap analysis surfaces missing items, conflicts (the CoC says X, the code does Y — a question, never
  auto-resolved) and missing sections.
- Present an additions-only diff plus any drop questions; append new sections at the end.

## Output budget

Every agent reads this whole file on top of its own instructions.

- Aim for **30–40** directives; **50** for a large or polyglot repo; **70 is the hard ceiling**.
- One numbered directive = one directive. Orientation, summaries, code blocks and the Why section
  don't count.
- Past 40 the delegate total crosses the ~150-directive adherence line: 50–70 trades adherence for
  coverage — **say so when reporting the count**.
- Near the band, merge near-duplicates and cut what the code makes obvious. New-file flow only: in
  update mode nothing existing is cut or merged, so surface the overage as a question instead.
- A mutation gate ships only where a mutation tool exists; otherwise it is chat advice, never a rule.

## Corner cases

- Monorepo/polyglot: per-module subsections in the one root file.
- Multi-repo or opened elsewhere: one CoC per repo, never merged.
- Thin/empty repo: lean on Q&A and ship a small labelled seed.
