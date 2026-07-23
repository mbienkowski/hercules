---
description: Ship phase — review the commit plan, then stage, commit, and push the delivered work
disable-model-invocation: true
---



Stage, commit, and optionally push the delivered work. Plugin-file citations (`hercules-reference §…`, `protocols/…`) live in this plugin's directory.

**Plan mode — required.** Enter plan mode; present a complete Ship plan; at the **Plan approval** gate — *you approve the phase after reviewing the plan* — the gate accepts the canonical Plan-approval trigger words (`persona.md § Delivery workflow`); any other utterance is feedback. When the user approves, leave plan mode, then execute all steps automatically — no further questions.

---

## Precondition check (before plan mode)

Read the project's registry entry in `~/.hercules/config.json` and the active session in `~/.hercules/state/{slug}.json` (see `hercules-reference § Machine-local state`).

If `current_phase` is `"shipped"` and `shipped_commit` is set: report the SHA (and, when the eligibility check below passes and `shipped_pr` is unset, offer step 5's PR) — then stop.

If `build_complete` is not `true`: refuse — "Local build is not complete. Finish `/hercules:build` first." — and stop (a spec-scoped invocation is the one exemption — see below).
Surface any `handed_off_by` / `handoff_note` — the successor sees the note here.

Verify the working directory is a git repository (`git status` returning "not a git repository" → stop: "Not a git repository — run `git init` or open Grok in your repo, then re-run."). Detect a detached HEAD (`git symbolic-ref --quiet HEAD` failing → stop: "Detached HEAD — check out a branch (`git checkout -b {name}`), then re-run."). Prior-session changes & CoC conflicts (`persona.md` § 9): classify `git status --porcelain` entries in-session vs external; external → list and ask before plan mode. CoC rule blocking an explicit request → ask once; never edit the CoC unprompted.

Check PR eligibility silently (never blocks): origin URL contains `github.com`; `gh --version` succeeds; `gh auth status` exits 0; `gh pr list --head {current-branch} --state open --json url` returns empty (eligible) or an existing PR URL (capture as `_existing_pr`). Any failure → omit PR from plan.

### Spec-scoped ship (from Build's cadence)

When Build's *ship-each* cadence invokes Ship mid-build ("ship now"), skip only the `build_complete` refusal — the session-wide gate (G6, `${GROK_PLUGIN_ROOT}/protocols/workflow-protocol.md#registry`) stays for the close-out ship. Scope to the current spec: staged set is the files this spec produced (surface anything else as "Not included — stage if you want"), commit message derives from the spec's scope, PR omitted — `shipped_pr` belongs to the close-out ship. The plan flow is unchanged. A spec-scoped ship never writes `current_phase: "shipped"`, `build_complete`, or `shipped_commit`; on a failed commit or push, control returns to Build's Advance prompt and the spec is not retired. The close-out ship later commits the remaining residue (retired specs, `INDEX.md`) — its message should say so.

---

## Plan proposal (inside plan mode)

Run `git status --short` and `git diff --stat HEAD`. If the working tree is clean, check for an interrupted ship first: `build_complete: true` with a HEAD commit matching this session's scope means step 2 landed but Record never ran — confirm with the user, then finish at Execution step 3 (push, if wanted) and step 4. Otherwise: "Working tree clean — nothing to ship. Already committed? Done. Expected changes? Check repo/branch, or run `/hercules:build` first." — and exit.

**Staged set.** Default: all modified and new tracked files from the session, plus `docs/INDEX.md` if modified. For multi-repo sessions, collect across all repos in the `repositories` map. Surface other modified files as "Not included — stage if you want".

**Commit message.** Read `*-business-requirements.md`. Build a Conventional Commits message:
- **type** — `feat` for new capability; `fix` for correcting behaviour. Show one-sentence rationale.
- **scope** — strip the date prefix from the session slug (`2026-06-28-user-auth` → `user-auth`).
- **description** — imperative reformulation of `## Goal`, lowercased, no period, ≤ 72 chars total.
- Never add AI attribution trailers to the message.
- For breaking changes (removed public API, migration files, altered public signatures): propose a `BREAKING CHANGE:` footer.

**Push target.** Read the project's code-of-conduct (resolve it per `hercules-reference § Code-of-conduct resolution`) and infer push preference from its prose (branch protection, CI conventions, PR requirements). Propose `push to origin/{current-branch}`, or omit if no remote is configured. The user can change this in the plan.

**Plan format:**
```
## Ship plan — {session-slug}

### Files to stage
  + src/auth/jwt.py                              (new)
  + docs/INDEX.md                                (modified)

  Not included (stage if you want): • README.md

### Commit
  feat(user-auth): add JWT refresh token rotation
  (Inferred from: Goal section + 2 new files in src/auth/)

### After commit
  Push to origin/feature-user-auth
  Open PR → main (when eligible; omit when not)
    Title:  feat(user-auth): add JWT refresh token rotation
    Body:   §Goal + §Success criteria from business-requirements.md
            No AI attribution or tool-credit trailers.

Say **"approved"** or click **Accept** to execute all steps, or tell me what to change.
```

Regenerate the complete plan on each amendment — never patch sections.

---

## Execution (after approval — automatic, no further prompts)

**1. Stage.** `git add <file>` per approved file — never `git add -A` or `git add .`. Multi-repo: stage in ascending spec delivery order.

**2. Commit.** `git commit -m "{approved message}"`. Run without hook-bypass or signature-suppression flags — hooks and signing execute as configured. Capture the resulting SHA. On failure: surface the exact error verbatim, do not write to state, stop. The user resolves the issue and re-runs `/hercules:ship` (spec-scoped: control returns to Build's Advance prompt instead).

**3. Push.** Execute the approved push action without force flags. On failure: report the raw git error, leave commits intact, stop (spec-scoped: return to Build's Advance prompt). Multi-repo: push in delivery order; stop on first failure and report which repos are inconsistent.

**4. Record.** Session-wide ship only — spec-scoped skips this. Write **all** end-of-ship state mutations in **one** atomic temp + rename to `~/.hercules/state/{slug}.json` — `current_phase: "shipped"`, `build_complete: false`, `shipped_commit`, `last_updated`, and `shipped_pr` if step 5 ran. Show `"Shipped {session-slug} at {short-SHA}."`

**5. Create PR.** Only when the plan includes a PR step and Step 3 succeeded. Recheck first: `gh pr list --head {branch} --state open` — if already open, record URL as `shipped_pr` and show it. Otherwise: read `*-business-requirements.md`, extract `## Goal` and `## Success criteria`, compose body (no AI attribution or tool-credit trailers), then `gh pr create --title "{commit subject}" --body "{body}" --base "{base branch}"`. Record `shipped_pr: "{URL}"` atomically and show `"Opened PR: {URL}"`. On failure: surface the raw `gh` error; leave `shipped_commit` intact; the user opens the PR manually.
