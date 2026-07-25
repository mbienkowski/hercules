import { describe, expect, it } from 'vitest';

import { BUILD, SHIP, readFile, readPersona, section } from './support';

// Ported from tests/commands/test_commands_build_lifecycle.py — Build session lifecycle: resume,
// reconcile, start-fresh, handoff, discovery.

describe('build session lifecycle', () => {
  it('build offers to resume a project from saved state', () => {
    const lower = readFile(BUILD).toLowerCase();
    expect(lower).toContain('resume');
    expect(lower).toContain('~/.hercules/');
    expect(lower).toContain('state');
    expect(lower).not.toContain('docs/.context');
  });

  it('build records which spec is active and which are done', () => {
    const md = readFile(BUILD);
    expect(md).toContain('current_spec');
    expect(md).toContain('delivered_specs');
  });

  it("close-out asks whether to leave a handoff note", () => {
    const md = readFile(BUILD);
    const closeout = md.slice(md.indexOf('## Close-out'));
    expect(closeout.toLowerCase()).toContain('anyone taking over');
  });

  it('project registry is documented as rebuildable, not authoritative', () => {
    const persona = readPersona().toLowerCase();
    expect(persona).toContain('regenerable index');
    expect(persona.includes('rebuilt from') || persona.includes('source of truth')).toBe(true);
  });

  it("starting fresh removes a stale frozen file override", () => {
    const md = readFile(BUILD);
    const fresh = md.slice(md.indexOf("On 'start fresh':"), md.indexOf('On resume, reconcile'));
    expect(fresh).toContain('frozen_override');
  });

  it('resuming drops frozen file records for files that no longer exist', () => {
    const md = readFile(BUILD);
    const reconcile = md.slice(md.indexOf('On resume, reconcile'), md.indexOf('### Step 1'));
    expect(reconcile).toContain('frozen_test_files');
  });

  it('resuming does not delete spec files the project chose to keep', () => {
    const md = readFile(BUILD);
    const reconcile = md.slice(md.indexOf('On resume, reconcile'), md.indexOf('### Step 1'));
    expect(reconcile).toContain('git rm');
    expect(reconcile).toContain('keep_specs');
  });

  it('a handoff note written at close-out is visible to the next session', () => {
    const ship = readFile(SHIP);
    expect(ship.includes('handoff_note') || ship.includes('handed_off_by')).toBe(true);
  });

  it('resuming a session still requires plan approval first', () => {
    const build = readFile(BUILD);
    const resume = build.slice(build.indexOf("On 'start fresh':"), build.indexOf('On resume, reconcile'));
    expect(resume).toContain('Plan approval');
  });

  it('starting fresh clears old progress checkpoints', () => {
    const build = readFile(BUILD);
    const fresh = build.slice(build.indexOf("On 'start fresh':"), build.indexOf('On resume, reconcile'));
    expect(fresh).toContain('build_progress');
  });

  it('starting fresh keeps the delivery record for specs the project kept', () => {
    const build = readFile(BUILD);
    const fresh = section(build, "On 'start fresh':", 'On resume, reconcile', BUILD);
    expect(fresh).toContain('keep_specs');
    expect(fresh).toContain('checkpoint');
  });

  it('resuming after an interrupted finish completes it instead of redoing it', () => {
    const build = readFile(BUILD);
    const reconcile = build.slice(build.indexOf('On resume, reconcile'), build.indexOf('### Step 1'));
    expect(reconcile).toContain('build_progress');
    expect(reconcile).toContain('step 10');
  });

  it('a handoff note is shown even when no spec is currently in progress', () => {
    const build = readFile(BUILD);
    const step0 = build.slice(build.indexOf('### Step 0'), build.indexOf('### Step 1'));
    const handoffAt = step0.indexOf('handed_off_by');
    const gateAt = step0.indexOf('`current_spec` is set');
    expect(handoffAt).toBeLessThan(gateAt);
  });

  it('resuming rebuilds the project registry if it was lost', () => {
    const reconcile = section(readFile(BUILD), 'On resume, reconcile', '### Step 1', BUILD);
    expect(reconcile).toContain('rebuild');
    expect(reconcile).toContain('registry');
  });

  it('starting fresh clears every field needed for a true restart', () => {
    const fresh = section(readFile(BUILD), "On 'start fresh':", 'On resume, reconcile', BUILD);
    for (const field of ['`current_spec`', '`current_spec_round`', '`frozen_test_files`',
      '`frozen_override`', '`pending_specs`', '`build_progress`']) {
      expect(fresh).toContain(field);
    }
  });
});
