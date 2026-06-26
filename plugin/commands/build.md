# /hercules:build

Delivery wizard — step 3 of the Hercules workflow. Locate the spec files, execute each spec in order, verify and trace each before retiring it, validate coverage with evidence, mark progress only after approval. Never mark a spec done without approval and never close out with undelivered specs.

## Step 0 — Session context

Resolve the **artifact root** (`docs_root`, default `docs/`; see `CLAUDE.md § Artifact root resolution`), then read the project's entry in `~/.hercules/hercules-config.json` (see `CLAUDE.md § Machine-local state`). If `current_phase` is `"build"` and `current_spec` is set, show any `handed_off_by` / `handoff_note` first, then offer:
> "I see you were building `{active_session}` on **{current_spec}**. Resume from there? Say **'resume'** or **'start fresh'**."

On 'start fresh': clear `current_spec`, `delivered_specs`, and `pending_specs` in the project's entry and proceed normally.
On 'resume': after Step 1, skip directly to the spec matching `current_spec`.

On resume, reconcile against the filesystem: a spec listed in `delivered_specs` whose file still exists was interrupted before its delete — `git rm` it now. `pending_specs` drives remaining work, self-healing an interrupted run.

If the project has no entry or `current_phase` ≠ `"build"`: proceed silently.

## Step 1 — Session discovery

Find sessions ready for delivery — two formats:
- *medium+:* has `*-business-requirements.md` and at least one `*-spec-NN-*.md`, none delivered yet
- *trivial/low:* has `*-session.md` with an empty `## Delivery` section

Present a numbered list with format indicators. Ask which to deliver (number, path, or Enter for most recent).

For a `*-session.md` session, read that single file in Step 3 instead of the separate artifacts. If no sessions are found, tell the user to run `/hercules:design` first.

## Step 2 — Service paths

Read the selected specs for named services (each spec names its service in `## Scope`). If none are named, work in the current directory — no prompt needed. Otherwise, for each named service not yet in the project's `repositories` map (in `~/.hercules/hercules-config.json`), ask:
> "What is the local path to `{service}` on your machine?"

Validate the path exists. On success echo: `"Found {service} at {path} — detected: {manifest}."` Write confirmed paths to the project's `repositories` map (atomically; never into the repo). When all paths are resolved, show a summary table. (Write/Edit tools accept absolute paths; Bash uses `cd {service-path} && {command}`.)

Check for `code-of-conduct.md` at each service path (and the home repo for single-service). If absent:
> "No `code-of-conduct.md` found for `{service}`. Agents will infer conventions from existing tests. To generate one, say **'generate conduct for {service}'** at any point."

## Step 3 — Read the specs

Read `*-business-requirements.md` and the spec files from the confirmed session.
List all `*-spec-NN-*.md` files in delivery order (ascending NN). Summarise each spec's scope and what "done" means.

If the project's entry has `pending_specs` from a prior session, use that order; otherwise derive it from shell-sort of spec filenames.

## Step 4 — Classify complexity & confirm

> "I'm classifying this as **complexity:X** because [one sentence rationale]."  
> "Do you agree, or would you like to override?"

Wait for the user to confirm or override before proceeding.

## Step 5 — Execution

For each spec file in delivery order, run this cycle:

1. **Failing tests first.** Invoke `write-test-scenarios` for the spec's scope and linked design section. Tests must fail before writing implementation. Frontend scope: suggest Gherkin e2e scenarios (Cypress / Playwright); keep scenario files in source control.
2. **Scope lock.** Once tests are red, the acceptance criteria and test assertions are frozen for this spec. A test that needs editing to pass signals a gap in the design: stop, re-enter `/hercules:design` to close the gap, then return here.
3. **Implement.** Write the minimum code to turn the failing tests green. Stay within the spec boundary; respect `code-of-conduct.md`. Do not expand scope.
4. **Verify.** Run the full suite: all new tests pass, no regressions. Require branch ≥ 90%; mutation kill rate by tier — trivial 90%, low 88%, medium 85%, high 82%, critical 80% (tool from code-of-conduct.md; mutmut / Stryker / PITest as fallback). Fix survivors before continuing.
5. **Traceability.** Each `satisfies:` requirement §section maps to ≥1 **named passing test** — the spec's own acceptance criteria passing is not sufficient; the business requirement must have a test asserting it. Each acceptance criterion maps to a test. Any uncovered requirement → stop, re-enter `/hercules:design` to close the gap.
6. **Retire the spec.** As the **last** action for this spec, `git rm docs/{session}/{spec-filename}` — its intent now lives in code and tests. Update the project's entry in `~/.hercules/hercules-config.json` atomically (temp + rename): set `current_spec`, append the filename to `delivered_specs`, drop it from `pending_specs`. For multi-service delivery, prefix spec references with `"{service}/"`.

For specs scoped to a service under `## {service}` in the design: announce `"Now working in {service} at {local-path}."` and use that path for all file operations and Bash test runs. Read `{service-path}/code-of-conduct.md` if present (overrides home repo CoC for this service's specs). Construct the absolute path as `{service-path}/{path-from-repo-root}` for every Read, Write, and Edit call; never use a bare relative path. After implementing, run `git -C {service-path} status` to confirm the expected files appear modified before verifying.

Pause after each spec:
> Spec [NN] complete — tests green, traced, retired. Proceed to spec [NN+1]? (yes / continue all)

## Step 6 — Tier-scaled review (after all specs)

- *medium:* spawn `hercules:cynical-reviewer` with the diff and the spec files; apply every Blocker/High before close-out.
- *high/critical:* additionally spawn the relevant domain-expert agent (infer from the feature domain), then invoke the `learnings` skill.

## Step 7 — Validation gate (required before close-out)

Two checks, both must pass:

- **Delivery evidence.** For every spec that was in the delivery list, cite evidence: `✓ [spec slug] → evidence` or `✗ [spec slug] → NOT DELIVERED`.
- **Requirements traceability & drift.** Every requirement in `*-business-requirements.md` is covered by a delivered spec — each maps to ≥1 named passing test, verified per spec in Step 5. Then the reverse: any shipped behaviour with no originating requirement is scope drift — surface it and require a disposition (amend `*-business-requirements.md`, or annotate as deliberate/trivial). Drift on a high-risk surface (auth, secrets, money, migration, deletion, prod-config, concurrency) **blocks** until requirement-backed.

If any spec is undelivered or any requirement is uncovered, do not close out — ask the user to resolve or defer with a reason.

## Step 8 — Close-out

After approval and a passing validation gate, there is no artifact to write — the code and tests
are what ships, and git history is the record of what was delivered.

Update `docs/INDEX.md`: set this session's `Status` to `delivered`. Write atomically (temp + rename).

Ask: "Is anyone taking over from here? Say 'handoff to {name}: {note}' to record it, or skip." If provided, write `handed_off_by` and `handoff_note` to the project's entry in `~/.hercules/hercules-config.json`.

Show a one-line summary of what was delivered.
