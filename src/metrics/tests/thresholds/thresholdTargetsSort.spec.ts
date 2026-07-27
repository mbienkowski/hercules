import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';

import {
  afterEach, describe, expect, it, vi,
} from 'vitest';

// A SEPARATE spec file, deliberately — vi.mock('node:fs') is module-scoped and hoisted. Node's own
// globSync already returns matches in name order on this platform, so on a real FS (filesystem) the
// mutant dropping resolveTargets's `.sort()` (thresholdRunner.mts) survives; reversing globSync's
// result proves the sort is load-bearing without relying on incidental platform ordering.
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return {
    ...actual,
    globSync: vi.fn((...args: Parameters<typeof actual.globSync>) => {
      const result = (actual.globSync as (...a: unknown[]) => unknown)(...args);
      return Array.isArray(result) ? [...result].reverse() : result;
    }),
  };
});

const { resolveTargets } = await import('../../thresholdRunner.mjs');

const dirs: string[] = [];

function workspace(): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-threshold-targets-sort-'));
  dirs.push(root);
  return root;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('resolveTargets applies its own sort, not an incidentally-sorted glob listing', () => {
  it('returns glob matches in name order even when the underlying glob reports them reversed', () => {
    const root = workspace();
    for (const name of ['zeta', 'mid', 'alpha']) writeFileSync(join(root, `${name}.md`), 'x', 'utf-8');
    const names = resolveTargets(root, '*.md').map((t) => basename(t));
    expect(names).toEqual(['alpha.md', 'mid.md', 'zeta.md']);
  });
});
