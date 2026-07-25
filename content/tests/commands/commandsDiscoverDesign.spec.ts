import { describe, expect, it } from 'vitest';

import { BUILD, DESIGN, DISCOVER, readFile, section } from './support';

// Ported from tests/commands/test_commands_discover_design.py — Discover and Design phase
// contracts.

describe('discover and design phase contracts', () => {
  it('README does not promise Discover drafts can be resumed later', () => {
    const readme = readFile('README.md').toLowerCase();
    expect(readme).not.toContain('picked up where you left off');
  });

  it('Discover never commits machine-specific session files to the users repo', () => {
    const md = readFile(DISCOVER);
    expect(md).not.toContain('.gitignore');
    expect(md).not.toContain('docs/.context');
    expect(md).toContain('~/.hercules/');
  });

  it("saying 'approved' early in Discover does not save the file", () => {
    const md = readFile(DISCOVER);
    const lower = md.toLowerCase();
    expect(lower).not.toContain('and i will save the file');
    const iStep5 = lower.indexOf('## step 5');
    const iStep6 = lower.indexOf('## step 6');
    const step5Text = lower.slice(iStep5, iStep6);
    expect(step5Text).toContain('plan approval');
  });

  it('resuming Build still finds a session with some specs already delivered', () => {
    const md = readFile(BUILD);
    expect(md).not.toContain('none delivered yet');
    const lower = md.toLowerCase();
    const iStep1 = lower.indexOf('### step 1');
    const iStep2 = lower.indexOf('### step 2');
    const window = lower.slice(iStep1, iStep2);
    expect(window.includes('still pending') || window.includes('not yet delivered')).toBe(true);
  });

  it('Build asks where each service lives when the design covers several services', () => {
    const lower = readFile(BUILD).toLowerCase();
    expect(
      lower.includes('local path') || lower.includes('service path') || lower.includes('service-path'),
    ).toBe(true);
  });

  it('Discover figures out where project documents should be saved', () => {
    const md = readFile(DISCOVER);
    const lower = md.toLowerCase();
    expect(lower).toContain('artifact root');
    expect(lower).toContain('code-of-conduct.md');
    expect(md).toContain('docs_root');
  });

  it('Discover offers to generate a missing code-of-conduct as a quality boost', () => {
    const md = readFile(DISCOVER);
    const step0 = md.slice(md.indexOf('## Step 0'), md.indexOf('## Step 1'));
    expect(step0).toContain('code-of-conduct-generator');
    expect(step0.toLowerCase()).toContain('quality');
  });

  it('a finished sessions leftover files do not make it look still pending', () => {
    const build = readFile(BUILD);
    const step1 = build.slice(build.indexOf('### Step 1'), build.indexOf('### Step 2'));
    expect(step1.includes('pending_specs') || step1.includes('delivered_specs')).toBe(true);
  });

  it('Discover waits until the end to actually save the resolved document path', () => {
    const discover = readFile(DISCOVER);
    const step0 = discover.slice(discover.indexOf('## Step 0'), discover.indexOf('## Step 1'));
    expect(step0).toContain('Step 7');
  });

  it('finishing Discover does not erase other saved project settings', () => {
    const discover = readFile(DISCOVER);
    const step7 = discover.slice(discover.indexOf('## Step 7'));
    expect(step7).not.toContain('empty\n`repositories`');
    expect(step7).not.toContain('empty `repositories`');
    expect(step7).toContain('preserv');
  });

  it('Design explicitly forbids saving specs before the user approves', () => {
    const approval = section(readFile(DESIGN), '## Step 8 — Plan approval', '## Step 9', DESIGN);
    expect(approval).toContain('**Do not write the specs until the user approves.**');
  });

  it('a small idea gets all its discovery questions in one message', () => {
    const discover = readFile(DISCOVER);
    const step2 = section(discover, '## Step 2', '## Step 3', DISCOVER);
    expect(step2).toContain('one message');
  });
});
