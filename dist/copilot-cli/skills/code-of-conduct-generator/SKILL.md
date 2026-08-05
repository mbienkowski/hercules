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
  directory. If Copilot was opened away from the code, or several roots are candidates, list them
  (`ls`, `git rev-parse --show-toplevel`) and ask which repo the CoC is for.
- Run every scan, `find` and git command against that root (`git -C <root>`), never bare `.`.

## Method

1. **Plan mode & mode** — enter plan mode first, before any scanning; give a chat summary of the
   flow and offer **Quick** (small/low-stakes default: scan → a few questions → draft → gate → review →
   commit) or **Thorough** (adds the coverage-map gap pass and an advisor critical-review pass). Name the detected
   root so the user can correct it.
2. **Find existing CoC** — `find <root> -maxdepth 2 -iname 'code[-_ ]of[-_ ]conduct.md'` across
   root/`.github/`/`docs/`, any capitalization.
   - One match → **update mode**. But a lone `.github/` behavioural Contributor Covenant is not an
     engineering standard: treat it as none and create a separate file.
   - More than one → **never silently pick**; list every match and confirm the target.
   - None → default `code-of-conduct.md` in the root.
3. **Scan** — `python3 ${PLUGIN_ROOT}/tools/code_of_conduct/coc_scan.py all --root <root> --contract 2`.
   - It reports what the repo declares, what its history shows, which directories are alive, cooling,
     dormant or generated, a ranked file list to read from, and the `arch.*` facts: file families
     (extension points), the import graph, chokepoints, entrypoints, config consumers.
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
   - Orientation first (what the repo is, the edit→verify loop), then themed sections — Architecture
     naming the real mechanisms, how the repo is extended, Testing, Quality Gates, Security & Data,
     Delivery — each a 1–3 sentence summary then its rules; every reason in one closing Why section.
   - Every rule: one line, opening `MUST:`/`SHOULD:`/`AVOID:`/`NEVER_DO:`, its check named inline.
     Plain text — no markup.
   - A worked example (≤12 indented lines) per `arch.families` extension point: the exact files one
     more addition touches, its owning test named.
   - Orientation, summaries, examples and the Why section cost no directive; the caps keep that true.
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
   - Pipe it to `python3 ${PLUGIN_ROOT}/tools/code_of_conduct/coc_audit.py draft --contract 2`.
   - **Exit 0 ships.** Any other exit: fix or drop what its `findings` name and re-run — never argue
     past it, never hand-wave a rule it refused.
   - It judges tag, check, citations, unique id, observation paths, and the directive count. The rest
     stays yours: each rule reads exactly one way and conflicts with no other.
   - Lay the rules out as markdown, then `python3 ${PLUGIN_ROOT}/tools/code_of_conduct/coc_lint.py
     --contract 2` with `{"contract":2,"markdown":"…","paths":[each observation's path]}` on stdin —
     it checks the shape and holds every observation path against HEAD; it reports what to fix, it
     never fixes it. Apply its findings and re-run until clean.
   - Present with a short summary (top standards, added, conflicts, dropped, and the band when past
     `intended`), surfacing only the ~5 genuine decisions — never a long list to curate.
   - Feedback applies **surgically** with a diff; regenerate wholesale only if the user reopens the
     scope, and re-gate only what changed.
8. **Approve & write** — on approval: leave plan mode → write atomically (temp + rename).
   The generator **never creates or edits any file besides the code-of-conduct itself** — offer the
   `@./code-of-conduct.md` reference line for `AGENTS.md` in chat; adding it is the
   user's edit. Then **re-run the linter against the file on disk**
   (`… coc_lint.py --contract 2 --file <coc> --root <root>`): the draft that passed is not proof about
   the bytes that landed. Fix and re-run until clean.
9. **Review & commit** — show the file and ask the user to review it. On their go-ahead, **stage then
   commit** exactly the code-of-conduct file — `git add -- <path>` then `git commit -m … -- <path>` —
   so an untracked new file commits cleanly and the user's other staged work is never reset or swept
   in; use the mined commit convention or a plain imperative subject.
   Attribution lives in the commit message, never in the file. Offer a push; never push automatically.
   No go-ahead → reply: "Left uncommitted: {path}. Say 'commit' when ready, or edit first."

## Update mode

- **Read it mechanically first:** `python3 ${PLUGIN_ROOT}/tools/code_of_conduct/coc_lint.py
  --contract 2 --file <coc> --root <root>`. Its `findings` are rotted references — wrong whoever
  wrote them. Its `shape_notes` are **not a task list**: reformatting an existing bullet is the edit
  additions-only forbids.
- A `dangling` entry is a **question for the user, never an edit** — the rule may be right and the
  path merely moved.
- Where the state file holds a previous run's envelope (`schema_version` 1), re-verify those citations
  exactly instead. An unreadable or older envelope **says so in chat** and falls back to the report.
- **Additions only:** never rename, reorder, delete or restructure existing sections or bullets on the
  generator's own initiative. Exceptions: a critical-review-proposed drop after an explicit yes, and
  any edit the user directs.
- Existing bullets are never retro-fitted with tags, summaries or reasons, and **never submitted to
  the gate** — they predate it, so validating them would refuse every legitimate update. New rules and
  new sections meet the full bar.
- Gap analysis surfaces missing items, conflicts (the CoC says X, the code does Y — a question, never
  auto-resolved) and missing sections.
- Present an additions-only diff plus any drop questions; insert bullets in place, append new sections
  at the end.

## Output budget

Every agent reads this whole file on top of its own instructions.

- Aim for **30–40** directives; **50** for a large or polyglot repo; **70 is the hard ceiling**.
- One tagged bullet = one directive. Orientation, summaries, worked examples and the Why section
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
