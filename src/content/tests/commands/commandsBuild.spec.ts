import { describe, expect, it } from 'vitest';

import { BUILD, RETIRE_STEP, readFile, readPersona, section } from './support';

// Build-phase TDD (test-driven development) loop: freeze, retire, cross-check, cadence, gates.

describe('build-phase TDD loop', () => {
  it('spec files are deleted only after traceability is confirmed', () => {
    const lower = readFile(BUILD).toLowerCase();
    expect(lower.lastIndexOf('git rm')).toBeGreaterThan(lower.indexOf('traceab'));
  });

  it('build records its phase as soon as the plan is approved', () => {
    const md = readFile(BUILD);
    expect(md).toContain('current_phase: "build"');
    const lower = md.toLowerCase();
    expect(lower.indexOf('### plan approval')).toBeLessThan(lower.indexOf('current_phase: "build"'));
  });

  it('build gives one consistent rule for running commands in multi-service projects', () => {
    const md = readFile(BUILD);
    expect(md).not.toContain('cd {service-path}');
    expect(md).toContain('never a bare relative path');
  });

  it('build points agents to a spec section that actually exists', () => {
    const md = readFile(BUILD);
    expect(md).not.toContain('in the design)');
    expect(md).not.toContain('linked design section');
    const i = md.indexOf('For a spec scoped to a service');
    expect(md.slice(i, i + 200)).toContain('## Scope');
  });

  it('the delivery plan is shown to the user before they approve it', () => {
    const md = readFile(BUILD);
    expect(md.toLowerCase()).toContain('satisfies');
    expect(md.indexOf('### Step 4 — Present the delivery plan')).toBeLessThan(md.indexOf('### Plan approval'));
  });

  it('the user can adjust batching and delivery cadence before approving', () => {
    const lower = readFile(BUILD).toLowerCase();
    expect(lower.includes('re-batch') || lower.includes('batch')).toBe(true);
    expect(lower).toContain('cadence');
    expect(lower).toContain('deliver all');
    expect(lower).toContain('ship each');
  });

  it('tests are frozen after being written and the freeze is clearly announced', () => {
    const md = readFile(BUILD);
    const lower = md.toLowerCase();
    expect(md).toContain('frozen_test_files');
    expect(lower).toContain('git diff');
    expect(lower).toContain('frozen');
    expect(lower).toContain('announce the freeze');
    expect(lower).toContain('bullets');
    expect(md).toContain('frozen_override');
    expect(lower.includes('the same turn') || lower.includes('this turn')).toBe(true);
    expect(md).toContain('frozen_hook: "off"');
  });

  it('the user decides what happens after three failed implementation attempts', () => {
    const md = readFile(BUILD);
    const lower = md.toLowerCase();
    expect(md).toContain('current_spec_round');
    expect(lower.includes('3 rounds') || lower.includes('round 3') || lower.includes('three rounds')).toBe(true);
    expect(lower).toContain('user');
    expect(lower.includes('decide') || lower.includes('decision')).toBe(true);
  });

  it('a checkpoint is saved after each piece of work is completed', () => {
    expect(readFile(BUILD)).toContain('build_progress');
  });

  it('test quality is checked while the work is still in progress, not after', () => {
    const lower = readFile(BUILD).toLowerCase();
    expect(lower).toContain('mutation gate');
    expect(lower.indexOf('mutation gate')).toBeLessThan(lower.indexOf('retire the spec'));
    expect(lower.indexOf('retire the spec')).toBeLessThan(lower.indexOf('## cross-check validation'));
  });

  it('final review runs after all work is done and before wrap-up', () => {
    const lower = readFile(BUILD).toLowerCase();
    expect(lower).toContain('cross-check');
    expect(lower.indexOf('cross-check')).toBeLessThan(lower.indexOf('## close-out'));
    expect(lower).toContain('match what we set out to build');
    expect(lower).toContain('build_progress');
  });

  it('finishing a piece of work unlocks its previously frozen tests', () => {
    const retire = section(readFile(BUILD).toLowerCase(), ...RETIRE_STEP, BUILD);
    expect(retire).toContain('frozen_test_files');
  });

  it('a project that opts to keep its spec files gets them updated instead of deleted', () => {
    const md = readFile(BUILD);
    const lower = md.toLowerCase();
    const retire = section(lower, ...RETIRE_STEP, BUILD);
    expect(retire).toContain('git rm');
    expect(retire).toContain('keep_specs');
    expect(retire).toContain('match what shipped');
    expect(lower.slice(lower.indexOf('### step 2'), lower.indexOf('### step 3'))).toContain('keep_specs');
  });

  it('final review relies on saved checkpoints even when spec files were kept, not deleted', () => {
    const md = readFile(BUILD);
    const sec = md.slice(md.indexOf('## Cross-check validation'), md.indexOf('## Capture learnings'));
    expect(sec).toContain('build_progress');
    expect(sec).not.toContain('deleted files');
  });

  it('build leaves planning mode before saving the approved plan', () => {
    const build = readFile(BUILD);
    const para = build.slice(build.indexOf('### Plan approval'), build.indexOf('## Execution'));
    expect(para.indexOf('ExitPlanMode')).toBeLessThan(para.indexOf('current_phase'));
  });

  it('the delivery cadence the user approved is saved for later steps to follow', () => {
    const build = readFile(BUILD);
    const para = build.slice(build.indexOf('### Plan approval'), build.indexOf('## Execution'));
    expect(para).toContain('cadence');
    const prose = readPersona().slice(readPersona().indexOf('Session object (in the state file):'));
    expect(prose).toContain('`cadence`');
  });

  it('completing work does not fail when its spec file was never saved to git', () => {
    const build = readFile(BUILD);
    const retire = build.slice(build.indexOf('10. **Retire the spec.**'), build.indexOf('For a spec scoped'));
    expect(retire.includes('if tracked') || retire.includes('never committed') || retire.includes('untracked')).toBe(true);
    const reconcile = build.slice(build.indexOf('On resume, reconcile'), build.indexOf('### Step 1'));
    expect(reconcile.includes('if tracked') || reconcile.includes('untracked') || reconcile.includes('plain delete')).toBe(true);
  });

  it('the attempt counter starts at one the moment tests are frozen', () => {
    const build = readFile(BUILD);
    const step3 = build.slice(build.indexOf('3. **Write failing tests.**'), build.indexOf('4. **Implement.**'));
    expect(step3).toContain('current_spec_round');
  });

  it('a corrected test is allowed to pass immediately instead of needing to fail first', () => {
    const build = readFile(BUILD);
    const step5 = build.slice(build.indexOf('5. **Quality gates.**'), build.indexOf('6. **Mutation gate.**'));
    expect(step5).not.toContain('re-pass the step-3 gate');
    expect(step5.toLowerCase()).toContain('green');
    expect(readPersona()).not.toContain('re-passes the write-tests gate');
  });

  it('a one-time permission to edit frozen tests does not linger past its intended use', () => {
    const build = readFile(BUILD);
    const retire = build.slice(build.indexOf('10. **Retire the spec.**'), build.indexOf('For a spec scoped'));
    expect(retire).toContain('frozen_override');
  });

  it('the test freeze is described as a safety net, not a guaranteed enforcement', () => {
    const build = readFile(BUILD);
    expect(build).not.toContain('Enforced, not promised');
    expect(build).toContain('git diff');
  });

  it('the saved checkpoint includes every field the final review needs', () => {
    const step9 = section(readFile(BUILD), '9. **Write the checkpoint.**', '10. **Retire the spec.**', BUILD);
    for (const token of ['satisfies:', 'named tests', 'coverage', 'mutation', 'constraints']) {
      expect(step9).toContain(token);
    }
  });

  it('finishing a piece of work resets the attempt counter for the next one', () => {
    const retire = section(readFile(BUILD), '10. **Retire the spec.**', 'For a spec scoped', BUILD);
    expect(retire).toContain('remove `current_spec_round`');
    expect(retire).toContain('clear `frozen_test_files`, `frozen_baseline`, and `frozen_override`');
  });

  it('a new tests failure must be a real failure, not a broken test file', () => {
    const build = readFile(BUILD);
    const step2 = section(build, '2. **Scaffold.**', '3. **Write failing tests.**', BUILD);
    expect(step2).toContain('compile');
    const step3 = section(build, '3. **Write failing tests.**', '4. **Implement.**', BUILD);
    expect(step3).toContain('fails for the right reason');
    expect(step3).toContain('forced failure');
    expect(step3).toContain('`current_spec_round: 1`');
  });

  it('build close-out batches every state mutation into one atomic write', () => {
    const closeout = section(readFile(BUILD), '## Close-out', undefined, BUILD);
    const lower = closeout.toLowerCase();
    expect(lower.includes('all') || closeout.includes('**all**')).toBe(true);
    expect(lower.includes('one') || closeout.includes('**one**')).toBe(true);
    expect(closeout).toContain('temp + rename');
  });

  it('build allows merging traceability and cross-check for single-spec deliveries', () => {
    const crosscheck = section(readFile(BUILD), '## Cross-check validation', '## Capture learnings', BUILD);
    expect(crosscheck).toContain('single-spec');
    expect(crosscheck).toContain('merge');
    expect(crosscheck).toContain('both mandates');
  });

  it('build classifies change type and skips scaffold for annotation-only', () => {
    const build = readFile(BUILD);
    const step1 = section(build, '1. **Read the spec.**', '2. **Scaffold.**', BUILD);
    expect(step1).toContain('annotation-only');
    expect(step1.includes('skip to Step 3') || step1.toLowerCase().includes('skip to Step 3')).toBe(true);
    expect(step1).toContain('refactor');
  });

  it('build Step 3 makes write-test-scenarios mandatory', () => {
    const step3 = section(readFile(BUILD), '3. **Write failing tests.**', '4. **Implement.**', BUILD);
    expect(step3.toLowerCase()).toContain('mandatory');
  });

  it('build Step 4 checks guard reachability before freezing', () => {
    const step4 = section(readFile(BUILD), '4. **Implement.**', '5. **Quality gates.**', BUILD);
    expect(step4.toLowerCase()).toContain('before freezing');
    expect(step4.toLowerCase()).toContain('unreachable');
  });

  it('build Step 4 runs test-compile on constructor changes', () => {
    const step4 = section(readFile(BUILD), '4. **Implement.**', '5. **Quality gates.**', BUILD);
    expect(step4.toLowerCase()).toContain('test-compile');
    expect(step4.toLowerCase().includes('constructor') || step4.toLowerCase().includes('signature')).toBe(true);
  });

  it('build Step 5 verifies coverage per touched file, not aggregate', () => {
    const step5 = section(readFile(BUILD), '5. **Quality gates.**', '6. **Mutation gate.**', BUILD);
    expect(step5.toLowerCase()).toContain('per touched file');
    expect(step5.toLowerCase()).toContain('affected code');
  });
});
