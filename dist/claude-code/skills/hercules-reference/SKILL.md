---
name: hercules-reference
description: Hercules operational reference — artifact-root resolution, code-of-conduct resolution, machine-local state (`~/.hercules/`) layout, agent-scaling tiers, sub-agent consent, and the debate protocol. Use when running any Hercules Discover/Design/Build/Ship phase, resolving where to write artifacts or machine-local state, scaling advisors, or running an advisor debate.
---

# Hercules operational reference

The normative operating details every Hercules phase relies on. Cited across the commands and persona as `hercules-reference § <Section>`.

## Artifact root resolution

Every command writes session documents (requirements, design, specs, build summaries,
`INDEX.md`, `learnings.md`) under the **artifact root**, resolved the same way. A
`code-of-conduct.md` directive wins: a same-repo directory (e.g. `documents/`) is used silently;
a separate repository prompts once for its local path (validated, then cached as `docs_root` in
the project's registry entry — see § Machine-local state). Otherwise default to `docs/` in the
launch directory. Machine-local state is **never** written into the user's repo; it lives only
under `~/.hercules/` (the registry `config.json` plus per-project `state/{slug}.json`).
`~/.hercules` is install-and-state only and never holds project documents; commands show paths
relative to the resolved root as `docs/`.

## Code-of-conduct resolution

Every phase reads the project's code-of-conduct for its stack, conventions, and quality bar. Resolve it
by a matcher, never a fixed filename: it may be `code-of-conduct.md`, `CODE_OF_CONDUCT.md`, or any
capitalization — `-`/`_`/space between the words, extension `.md`, in the repo root, `.github/`, or
`docs/` — so find it case-insensitively (`find -iname 'code[-_ ]of[-_ ]conduct.md'`; the anchored form
`(?i)^code[-_ ]of[-_ ]conduct\.md$` matches any casing but not a lookalike like
`code-of-conduct-draft.md`). Read it from the repository the work targets, not the nearest path: a
service-scoped spec uses that service's repo (`repositories[service]`), otherwise the home code repo
(`directory`); when Claude is launched in a docs/requirements repo whose code lives elsewhere, the
governing CoC is the code repo's, never the launch/artifact repo's just because it is closest to the
working directory (a service CoC overrides the home CoC for that service's work). Then validate before
trusting it — confirm the match is a real code-of-conduct at the target repo's root/`.github/`/`docs/`,
not a lookalike or another repo's file; on more than one match don't silently pick (show them and
confirm); on exactly one, use it as the code-of-conduct with no extra prompt; and with none in the
target repo infer conventions from that repo's own code and tests, and say so.

## Machine-local state (`~/.hercules/`)

All per-project, machine-bound state lives under `~/.hercules/` — **never** in a file inside the
user's repo. It is split in two. The **registry** `~/.hercules/config.json` is config only: one entry
per project, keyed by a human-friendly slug (default the launch-directory basename, deduped on
collision), carrying `directory`, `docs_root`, a `state_file` pointer, and the `repositories` map.
Resolve the current project by matching the launch directory against each entry's `directory` (a full
path — collision-proof). The registry is a **regenerable index**: the state files are the source of
truth, so a missing or stale registry entry is rebuilt from `~/.hercules/state/*.json` on the next run
(a torn two-file write self-heals; never silently blank an entry). The **delivery state**
`~/.hercules/state/{slug}.json` is the source of truth for delivery, **keyed by session** (one feature
= one Discover gathering = one session, with its own `tier`).

All writes are atomic (temp + rename) and touch only the current project's registry entry / the active
session's object — never other entries, never the top-level `schema_version` (each file owns its own).

```json
// Example — illustrative values, not real state: ~/.hercules/config.json
{
  "schema_version": 1,
  "projects": {
    "user-auth-platform": {
      "directory": "/Users/alice/work/myrepo",
      "docs_root": "docs",
      "state_file": "user-auth-platform.json",
      "repositories": { "svc-auth": "/Users/alice/work/svc-auth" }
    }
  }
}
```

```json
// Example — illustrative values showing every field at once; real state omits fields that
// don't apply (e.g. frozen_override exists only while a grant is live, shipped_commit only
// after Ship): ~/.hercules/state/user-auth-platform.json
{
  "schema_version": 1,
  "active_session": "2026-06-22-user-auth",
  "sessions": {
    "2026-06-22-user-auth": {
      "tier": "high",
      "tier_rationale": "touches auth surface; floored at high",
      "current_phase": "build",
      "current_spec": "2026-06-22-user-auth-spec-02-login.md",
      "current_spec_round": 1,
      "frozen_test_files": ["tests/auth/test_login.py"],
      "frozen_override": {
        "files": ["tests/auth/test_login.py"],
        "spec": "2026-06-22-user-auth-spec-02-login.md",
        "round": 1,
        "reason": "user: 'expected status is 201, not 200 — fix the test'"
      },
      "delivered_specs": ["2026-06-22-user-auth-spec-01-schema.md"],
      "pending_specs": ["2026-06-22-user-auth-spec-03-refresh.md"],
      "build_progress": [
        {
          "spec": "2026-06-22-user-auth-spec-01-schema.md",
          "acceptance_criteria": ["token persists", "version conflict rejected"],
          "satisfies": ["§Token storage"],
          "decisions": "optimistic locking on token table",
          "interfaces": "TokenRepository.save(Token): Token",
          "tests_added": ["test_token_persists", "test_version_conflict_rejected"],
          "coverage": 94,
          "mutation": 91,
          "constraints_for_later_specs": "spec-03 must respect the version column"
        }
      ],
      "handed_off_by": "Dev A",
      "handoff_note": "spec-01 done. spec-02 blocked on svc-gateway contract.",
      "build_complete": true,
      "shipped_commit": "abc1234...",
      "shipped_pr": "https://github.com/owner/repo/pull/42",
      "last_updated": "2026-06-22T14:30:00Z"
    }
  }
}
```

Registry entry: `directory` — the project's local path (the launch / artifact-root host); the match key. `docs_root` — the resolved artifact root (default `"docs"`; a code-of-conduct.md directive may set a directory or a separate-repo local path). `state_file` — the per-project state filename under `~/.hercules/state/` (derived from the slug; stored so lookup never re-derives). `repositories` — additional service names → machine-local paths for cross-repo features; persists across features. `frozen_hook` — set to `"off"` on the user's instruction to disable the frozen-tests hook for this project (prompt-only TDD discipline); omit otherwise. `keep_specs` — `true` when the project's `code-of-conduct.md` directs keeping delivered specs (retire refreshes them instead of deleting); omit otherwise.

Session object (in the state file): `current_phase` — the phase backbone (`"discover"` → `"design"` → `"build"` → `"shipped"`); the hooks arm only on `"build"`, so a stale value silently disarms or over-arms the guard. `tier` + `tier_rationale` — scored once in Discover, read by Design and Build; never re-scored by Hercules (a manual user override is the only change). `current_spec` — the spec filename in progress. `cadence` — the approved delivery cadence (`"deliver-all"` / `"ship-each"`), written at Build's Plan approval so a resume honours it. `current_spec_round` — the 1–3 implementation-round counter, written `1` at the step-3 freeze, removed at retire, persisted so a resume can't reset it. `frozen_test_files` — the current spec's test files, `git diff`-guarded so a frozen test cannot be silently edited. `frozen_baseline` — `{path: sha256}` of those files at freeze; re-checked before retire so a tampered acceptance test can't be accepted. `frozen_override` — a user-granted exception the frozen-tests hook honours: files + spec + round + the user's quoted instruction; written only on the user's explicit grant, cleared once the corrected test compiles and asserts the corrected requirement (green against existing code is the expected pass) — and at latest by the pre-advance diff gate or retire; a stale spec or round never validates. Omit when no grant is live. `delivered_specs` / `pending_specs` — spec filenames delivered / remaining in order (omit when empty). `build_progress` — per-spec checkpoint (criteria, satisfies, decisions, interfaces, tests, coverage, mutation, cross-spec constraints) written at retire; the durable record the cross-check reads after specs are deleted. `handed_off_by` / `handoff_note` — written only at explicit handoff (Build close-out). `build_complete` — written `true` by Build close-out; read by Ship as its precondition; reset to `false` by Ship after a successful commit. `shipped_commit` / `shipped_pr` — written by Ship; omitted when not yet shipped / not applicable. `last_updated` — ISO 8601 stamp refreshed by state-writing steps (session-init, close-out, Ship's record).

## Agent scaling

Complexity is classified **once in Discover**, persisted to the session's `tier` in the state file, and **read forward** by Design and Build. **Tier = max(effort-signal, blast-radius-signal)** — never the average. A change touching auth, secrets, money, data migration, deletion, production config, or concurrency is floored at `high` regardless of diff size. Hercules **never re-scores** the tier — no automated escalation or de-escalation in any later phase. The **user may manually override** the tier at any point; that manual override is the only thing that changes it. (Advisor dissent surfaces as input to the user, not an automatic re-score.)

Sub-agent count per tier (main agent decides; user may override) — these counts are **advisors**; independent reviewers at the coverage/traceability gates are a separate category (§ Independent review):

| Tier | Sub-agents |
|---|---|
| trivial | 0 — main agent only |
| low | 1–2 |
| medium | 1–3 |
| high | 2–4 |
| critical | 3–6 |

Agent selection is the main agent's call, driven by the task at hand: the per-phase lists in the commands are a default starting point, not a fixed roster. Add, drop, or swap specialists to fit the feature and its context — e.g. a security-expert for auth, a senior-qa-engineer for solution design or a risky migration, or a source-checker when an article must be checked against its cited sources — choosing deliberately different, even opposing, perspectives (challenger, simplicity-advocate, and cynical-reviewer are strong general picks). Productive disagreement produces better specs than easy consensus.

### Sub-agent consent

The main agent never spawns advisors silently. It first asks the user's questions to pin down gaps and intent; when it has no more questions, it recommends advisors and waits. (This governs *advisors* — the generative debate. **Independent reviewers** at the coverage/traceability gates are a separate category, per § Independent review: mandatory at `low`+, recommend-and-ask at `trivial`, not part of this consent prompt.)
> Main agent has no more questions.
>
> As a recommendation, would you like to run a set of sub-agents to advocate on the current phase?
> - {agent} — {one-line reason}
> - {agent} — {one-line reason}
>
> Running advisors surfaces gaps, risks, and alternatives a single pass misses. See the Hercules README (*Why sub-agents*) for why this improves output quality.
>
> Proceed with sub-agents? You can:
> - **yes** — run the recommended set
> - **yes, but one fewer** — run the set minus the agent you name (e.g. "yes, drop the copywriter")
> - **yes, plus two with a specific agenda** — run the set and add advisors you brief (e.g. "yes, add a security expert focused on auth and a QA focused on the migration path")
> - **skip** — draft directly, no advisors
> - **adjust** — revise the list and re-ask

On **yes**: spawn per the tier counts above. On **yes, but one fewer**: spawn the set minus the named agent. On **yes, plus …**: spawn the set plus the extra advisors, each carrying the agenda the user gave. On **skip**: draft directly. On **adjust**: revise the list and re-ask.

## Debate protocol

Rule 7 in the Agent-Injected Core carries the minimal debate summary to all agents.
Once the user consents to advisors (§ Sub-agent consent), Discover and Design run those rounds scaled
to the session tier — running them is not separately optional.
Full orchestrator mechanics: [${CLAUDE_PLUGIN_ROOT}/protocols/debate-consensus-protocol.md](${CLAUDE_PLUGIN_ROOT}/protocols/debate-consensus-protocol.md).
For debates involving built-in Explore/Plan/Workflow agents, prepend the full
`${CLAUDE_PLUGIN_ROOT}/protocols/debate-consensus-protocol.md` to the per-call delegation prompt.

## Independent review

The two gates where a session would judge an artifact **it produced** — Design **requirement coverage**
and Build **traceability** — are decided by a freshly-spawned `hercules:cynical-reviewer` (read-only, not
a debate default — it never co-authored the draft), one reviewer per gate. It **reads the durable source
directly** — the full `*-business-requirements.md` (+ the spec's `## Affected code`/acceptance criteria, or
`build_progress` checkpoints) — **never a slice the producing agent pre-selected** (a curated slice is a
bias lever). At `trivial` the main agent recommends (skip / run one) and the user chooses; at `low`+ it
runs. Reviewers are distinct from advisors (§ Agent scaling's `trivial → 0` is advisors). The orchestrator
synthesises the findings (terminal — not itself reviewed) and **surfaces Blocker/High to the user at
Plan-approval as input, never an auto-veto**; a contested Blocker goes to the user. A fix is re-checked by
a **fresh** reviewer, bounded (three rounds → the user) — so self-review can't return and the gate can't
deadlock.
