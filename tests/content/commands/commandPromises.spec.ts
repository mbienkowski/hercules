import { describe, expect, it } from 'vitest';

import {
  BUILD, DESIGN, DISCOVER, PROJECT_RESET, RETIRE_STEP, SHIP, WORKFLOW, readFile, section,
} from './support';

/**
 * The main promise each command makes: step order, the decision gates that pause for a person, and the
 * prohibitions that would hurt someone if silently dropped — one describe per command, not a wording pin.
 */

describe('discover', () => {
  it('scores the project complexity and lets the user confirm or override it before continuing', () => {
    const lower = readFile(DISCOVER).toLowerCase();
    expect(lower, 'discover must classify complexity').toContain('complexity');
    expect(lower, 'discover must ask the user to confirm the classification').toContain('confirm or override');
  });

  it('never commits a machine-local session file, and points forward to Design once its plan is approved', () => {
    const md = readFile(DISCOVER);
    expect(md).not.toContain('docs/.context');
    expect(md).toContain('~/.hercules/');
    expect(md).toContain('/hercules:design');
  });
});

describe('design', () => {
  it('reads the tier Discover recorded instead of re-scoring it, and points forward to Build once approved', () => {
    const lower = readFile(DESIGN).toLowerCase();
    expect(lower.includes('tier') && lower.includes('state'), 'design must read the tier from state').toBe(true);
    expect(lower, 'design must not re-classify complexity').not.toContain('confirm or override');
    expect(readFile(DESIGN)).toContain('/hercules:build');
  });

  it('tests the plan against reality before it is ever shown as approvable', () => {
    // The promise, not the wording: nothing is offered for approval until the assumptions it rests
    // on have been checked. A plan approved and THEN found impossible is the failure this prevents.
    const lower = readFile(DESIGN).toLowerCase();
    const probe = lower.indexOf('## step 7');
    const approval = lower.indexOf('## step 9 — plan approval');
    expect(probe > 0 && probe < approval, 'assumptions are falsified before approval is asked').toBe(true);
    expect(lower).toContain('falsification, not proof');
    expect(lower).toContain('probe_run.py');
  });

  it('validates the plan is sound before asking for approval, and never writes specs before that approval', () => {
    const lower = readFile(DESIGN).toLowerCase();
    const i8 = lower.indexOf('## step 8');
    const i9 = lower.indexOf('## step 9 — plan approval');
    const i10 = lower.indexOf('## step 10');
    expect(i8 < i9 && i9 < i10, 'order must be validation gates (8) -> Plan approval (9) -> write specs (10)').toBe(true);
    const approval = section(readFile(DESIGN), '## Step 9 — Plan approval', '## Step 10', DESIGN);
    expect(approval).toContain('**Do not write the specs until the user approves.**');
  });
});

describe('build', () => {
  it('runs its TDD loop in a fixed order: scaffold, freeze failing tests, implement, quality gates, mutation gate, retire', () => {
    const build = readFile(BUILD);
    const lower = build.toLowerCase();
    expect(lower).toContain('mutation gate');
    expect(lower.indexOf('mutation gate')).toBeLessThan(lower.indexOf('retire the spec'));
    expect(build).toContain('frozen_test_files');
    const step3 = section(build, '3. **Write failing tests.**', '4. **Implement.**', BUILD);
    expect(step3, 'a corrected test still has to fail for the right reason first').toContain('fails for the right reason');
  });

  it('freezes tests after they are written, and only a one-time override can touch a frozen one', () => {
    const md = readFile(BUILD);
    const lower = md.toLowerCase();
    expect(md).toContain('frozen_test_files');
    expect(lower).toContain('announce the freeze');
    expect(md, 'the override must not linger past its intended use').toContain('frozen_override');
    const retire = section(lower, ...RETIRE_STEP, BUILD);
    // The override's clearing and `git rm` live in retire_spec.py; the promise here is refuse-on-drift.
    expect(retire, 'retire must run the fail-closed backstop first').toContain('frozen_tests.py check');
    expect(retire, 'retire must go through the tool that owns the ordering').toContain('retire_spec.py apply');
  });

  it('shows the delivery plan — including cadence — for approval before any code is written', () => {
    const md = readFile(BUILD);
    expect(md.toLowerCase(), 'build must OPEN in plan mode like every other phase').toContain('**plan mode — required');
    expect(md.indexOf('### Step 4 — Present the delivery plan')).toBeLessThan(md.indexOf('### Plan approval'));
    expect(md.slice(md.indexOf('### Plan approval'), md.indexOf('## Execution'))).toContain('cadence');
  });

  it('retires a spec only after traceability is confirmed, honours a project that keeps its specs, and points forward to Ship', () => {
    const lower = readFile(BUILD).toLowerCase();
    // The ordering promise: retire sits after traceability, and a drifted frozen test halts it first.
    expect(lower.lastIndexOf('retire_spec.py')).toBeGreaterThan(lower.indexOf('traceab'));
    const retire = section(lower, ...RETIRE_STEP, BUILD);
    expect(retire, 'a drifted frozen test halts the retire').toContain('halt');
    expect(retire).toContain('keep_specs');
    expect(readFile(BUILD)).toContain('/hercules:ship');
  });

  it('choosing "ship now" mid-build opens a full review, never a quiet commit', () => {
    const lower = readFile(BUILD).toLowerCase();
    const advanceStep = lower.slice(lower.indexOf('**advance.**'), lower.indexOf('**write the checkpoint.**'));
    expect(advanceStep).toContain('ship now');
    expect(advanceStep).not.toContain('git commit');
    expect(advanceStep).toContain('not retired');
  });
});

describe('ship', () => {
  it('shows a complete plan before committing anything, and never claims AI authorship or bypasses git safety', () => {
    const md = readFile(SHIP);
    const lower = md.toLowerCase();
    expect(lower).toContain('plan mode');
    expect(md).toContain('build_complete');
    expect(lower).toContain('commit message');
    expect(lower).toContain('approved');
    expect(md).not.toContain('--no-verify');
    expect(md).not.toContain('--force');
    expect(lower).not.toContain('co-authored');
    expect(lower).not.toContain('generated with');
  });

  it('only stages files the user explicitly approved, refuses outside a repo or on a detached checkout, and never edits the CoC unprompted', () => {
    const step1 = section(readFile(SHIP), '**1. Stage.**', '**2. Commit.**', SHIP);
    expect(step1).toContain('`git add <file>` per approved file');
    expect(step1).toContain('never `git add -A` or `git add .`');
    const precondition = section(readFile(SHIP), '## Precondition check', '## Plan proposal', SHIP);
    expect(precondition.toLowerCase()).toContain('detached');
    expect(precondition).toContain('not a git repository');
    expect(precondition).toContain('ask once');
    expect(precondition).toContain('never edit the CoC unprompted');
  });
});

describe('workflow', () => {
  it('walks the four phases in a fixed order, gating every transition on the user', () => {
    const md = readFile(WORKFLOW);
    const heads = ([[1, 'Discover'], [2, 'Design'], [3, 'Build'], [4, 'Ship']] as const)
      .map(([n, name]) => md.indexOf(`## Phase ${n} — ${name}`));
    expect(heads, 'the four phase sections must appear in order').toEqual([...heads].sort((a, b) => a - b));
    const lower = md.toLowerCase();
    expect(lower.indexOf('move to design') < lower.indexOf('move to build')
      && lower.indexOf('move to build') < lower.indexOf('move to ship'),
    'the transition gates must appear in phase order').toBe(true);
  });
});

describe('project-reset — the one command that deletes', () => {
  it('warns the action cannot be undone before the choice, and again at confirmation', () => {
    const text = readFile(PROJECT_RESET);
    expect(text.indexOf('cannot be undone')).toBeLessThan(text.indexOf('Choose what you want to delete'));
    const warnings = [...text.matchAll(/cannot be undone/g)].map((m) => m.index as number);
    expect(warnings.length).toBeGreaterThanOrEqual(2);
    expect([...text.matchAll(/DANGER ZONE/g)].length).toBeGreaterThanOrEqual(2);
    expect([...text.matchAll(/There is no backup, no undo, no restore\./g)].length).toBe(2);
  });

  it('offers each of the four clearable things as its own choice, any combination valid', () => {
    const choices = section(readFile(PROJECT_RESET), 'Choose what you want to delete', 'Reply with numbers');
    for (const item of ['1) Documents', '2) Settings', "3) One feature's record", "4) Every feature's record"]) {
      expect(choices, `missing choice: ${item}`).toContain(item);
    }
    expect(readFile(PROJECT_RESET)).toContain('Any combination is valid');
  });

  it('states a contract version on every call, and treats a non-zero exit as a full stop with no fallback route', () => {
    const text = readFile(PROJECT_RESET);
    const invocations = text.split('\n').filter((line) => line.includes('project_reset.py'));
    expect(invocations.length).toBeGreaterThanOrEqual(2);
    for (const line of invocations) expect(line, `unversioned call: ${line}`).toContain('--contract 1');
    expect(text).toContain('A non-zero exit is a full stop');
    expect(text).toContain('never fall back to deleting by another route');
  });

  it('relays the program\'s own refusal rather than guessing at state, and is not the same as abandoning a session', () => {
    const text = readFile(PROJECT_RESET);
    expect(text).toContain('abandon this session');
    expect(text).toContain('the only one of the two that deletes files');
    expect(text).toContain('word for word');
    expect(text).toContain('Do not read `~/.hercules` yourself');
  });
});
