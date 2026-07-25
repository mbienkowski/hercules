import { describe, expect, it } from 'vitest';

import { readRepoFile } from '../../../commons/support/repo';

// Ported from tests/docs/test_docs.py — the README "Plugin permissions" prose-pin cluster, split
// out of docs.spec.ts to keep both files under the CoC's 500-line-per-file cap.

describe('README "Plugin permissions" section', () => {
  it('truthfully discloses that the plugin runs code automatically', () => {
    const content = readRepoFile('README.md');
    const low = content.toLowerCase();
    expect(low, 'README must not claim the plugin has no executable code').not.toContain(
      'no executable code of its own',
    );
    expect(low, "README 'Plugin permissions' must disclose the enforcement hooks").toContain('hook');
    expect(low, 'README must name the PreToolUse hook surface').toContain('pretooluse');
    // The three safety properties a reader relies on before trusting a shipped hook.
    expect(
      low.includes('read-only') || low.includes('only **read**') || low.includes('only read'),
      'README must state the hooks are read-only over ~/.hercules',
    ).toBe(true);
    expect(
      low.includes('fail **open**') || low.includes('fail open'),
      'README must state the hooks fail open (never block when no active build)',
    ).toBe(true);
    expect(
      low.includes('no network') || low.includes('make no network') || low.includes('network — none'),
      'README must state the hooks make no network calls',
    ).toBe(true);
  });

  it('tells users the default model is opus and how to change it', () => {
    const readme = readRepoFile('README.md');
    const match = readme.match(/## Plugin permissions\n([\s\S]*?)(?=\n## |$)/);
    expect(match, "README must have a '## Plugin permissions' section").toBeTruthy();
    const perms = (match as RegExpMatchArray)[1] as string;
    expect(/defaults to `?opus`?/i.test(perms), 'Models bullet must state the persona defaults to opus').toBe(true);
    expect(perms, 'Models bullet must document the /model override').toContain('/model');
  });
});
