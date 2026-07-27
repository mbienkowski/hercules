import { describe, expect, it } from 'vitest';

import { BUILD, DESIGN, DISCOVER, SHIP, WORKFLOW, readFile, section } from './support';

// Ship phase, workflow orchestration, and cross-phase continuity.

describe('ship phase and workflow orchestration', () => {
  it('each delivery step points forward to the next', () => {
    const chain: Array<[string, string]> = [
      [DISCOVER, '/hercules:design'],
      [DESIGN, '/hercules:build'],
      [BUILD, '/hercules:ship'],
    ];
    for (const [file, nextStep] of chain) {
      expect(readFile(file)).toContain(nextStep);
    }
  });

  it('the workflow command walks the user through every phase in order', () => {
    const md = readFile(WORKFLOW);
    const heads = ([[1, 'Discover'], [2, 'Design'], [3, 'Build'], [4, 'Ship']] as const).map(
      ([n, name]) => md.indexOf(`## Phase ${n} — ${name}`),
    );
    expect(heads).toEqual([...heads].sort((a, b) => a - b));
    const lower = md.toLowerCase();
    expect(lower).toContain('move to');
    expect(lower).toContain('plan mode');
    expect(lower).toContain('not yet');
    expect(lower).toContain('move to ship');
  });

  it('choosing ship now mid-build opens a full review, not a quiet commit', () => {
    const lower = readFile(BUILD).toLowerCase();
    const iAdvance = lower.indexOf('**advance.**');
    const iNext = lower.indexOf('**write the checkpoint.**');
    const advanceStep = lower.slice(iAdvance, iNext);
    expect(advanceStep).toContain('ship now');
    expect(advanceStep).toContain('spec-scoped');
    expect(advanceStep).toContain('/hercules:ship');
    expect(advanceStep).not.toContain('git add');
    expect(advanceStep).not.toContain('git commit');
    expect(advanceStep).toContain('not retired');
    expect(advanceStep).not.toContain('build_complete');
  });

  it('shipping one piece at a time is documented consistently everywhere', () => {
    for (const path of [BUILD, SHIP, 'docs/workflow/workflow-diagram-detailed.html']) {
      expect(readFile(path).toLowerCase()).toContain('spec-scoped');
    }
  });

  it('Ship shows the user a complete plan before committing anything', () => {
    const md = readFile(SHIP);
    const lower = md.toLowerCase();
    expect(md).toContain('/hercules:ship');
    expect(lower).toContain('plan mode');
    expect(md).toContain('build_complete');
    expect(lower).toContain('index.md');
    expect(lower).toContain('commit message');
    expect(lower).toContain('approved');
    expect(lower.includes('conventional') || md.includes('feat(') || md.includes('fix(')).toBe(true);
    expect(lower).toContain('push');
    expect(md).not.toContain('--no-verify');
    expect(md).not.toContain('--force');
    expect(md).not.toContain('--force-with-lease');
    expect(lower).not.toContain('co-authored');
    expect(lower).not.toContain('generated with');
    expect(md).toContain('shipped_commit');
  });

  it("Ship's default commit includes the real shared index file", () => {
    const md = readFile(SHIP);
    expect(md).not.toContain('docs/{session}/INDEX.md');
    expect(md).not.toMatch(/docs\/\d{4}-\d{2}-\d{2}-[\w-]+\/INDEX\.md/);
    expect(md).toContain('docs/INDEX.md');
  });

  it('shipping never creates a new documentation file of its own', () => {
    const md = readFile(SHIP);
    expect(md.toLowerCase()).not.toContain('-ship.md');
    const writingToDocs = md.split('\n').some(
      (line) =>
        line.includes('docs/') &&
        (line.toLowerCase().includes('write') || line.toLowerCase().includes('create')) &&
        !line.toLowerCase().includes('index.md'),
    );
    expect(writingToDocs).toBe(false);
  });

  it('pull request creation only happens when GitHub access is confirmed', () => {
    const md = readFile(SHIP);
    const lower = md.toLowerCase();
    expect(lower).toContain('gh pr');
    expect(lower).toContain('auth');
    expect(md).toContain('shipped_pr');
    expect(lower).not.toContain('co-authored');
    expect(lower).not.toContain('generated with');
    expect(lower.includes('existing') || lower.includes('already')).toBe(true);
  });

  it('re-running Ship after success reports it was already shipped', () => {
    const ship = readFile(SHIP);
    expect(ship.indexOf('`current_phase` is `"shipped"`')).toBeLessThan(
      ship.indexOf('Local build is not complete'),
    );
  });

  it('Ship recovers gracefully if interrupted right after committing', () => {
    const ship = readFile(SHIP);
    const proposal = section(ship, '## Plan proposal', '\n## ', SHIP);
    const clean = section(proposal, 'working tree is clean', '\n\n', SHIP);
    expect(clean).toContain('build_complete');
    expect(clean.toLowerCase()).toContain('step');
  });

  it('a silent pre-check for an existing pull request is never recorded as a real ship', () => {
    const ship = readFile(SHIP);
    const precondition = ship.slice(0, ship.indexOf('## Plan proposal'));
    expect(precondition).not.toContain('record as `shipped_pr`');
    expect(precondition).toContain('_existing_pr');
  });

  it('finishing Build flips the switch that lets shipping begin', () => {
    const closeout = section(readFile(BUILD), '## Close-out', undefined, BUILD);
    expect(closeout).toContain('`build_complete: true`');
    expect(closeout).toContain('`current_spec: null`');
  });

  it('Ship only commits the files the user explicitly approved', () => {
    const step1 = section(readFile(SHIP), '**1. Stage.**', '**2. Commit.**', SHIP);
    expect(step1).toContain('`git add <file>` per approved file');
    expect(step1).toContain('never `git add -A` or `git add .`');
  });

  it('Ship refuses to run outside a repository or on a disconnected checkout', () => {
    const precondition = section(readFile(SHIP), '## Precondition check', '## Plan proposal', SHIP);
    expect(precondition.toLowerCase()).toContain('detached');
    expect(precondition).toContain('not a git repository');
  });

  it("Ship's proposed commit message follows the teams formatting rules", () => {
    const msg = section(readFile(SHIP), '**Commit message.**', '**Push target.**', SHIP);
    expect(msg).toContain('strip the date prefix');
    expect(msg).toContain('72');
    expect(msg).toContain('BREAKING CHANGE');
  });

  it('Ship surfaces prior session uncommitted changes before plan mode', () => {
    const precondition = section(readFile(SHIP), '## Precondition check', '## Plan proposal', SHIP);
    expect(precondition).toContain('git status --porcelain');
    expect(precondition).toContain('in-session');
    expect(precondition).toContain('external');
    expect(precondition).toContain('ask before plan mode');
  });

  it('Ship asks once on code-of-conduct conflict, never silently edits', () => {
    const precondition = section(readFile(SHIP), '## Precondition check', '## Plan proposal', SHIP);
    expect(precondition).toContain('ask once');
    expect(precondition).toContain('never edit the CoC unprompted');
    const persona = readFile('dist/claude-code/CLAUDE.md');
    expect(persona).toContain('asked about once');
  });
});
