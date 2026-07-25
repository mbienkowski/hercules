import {
  mkdirSync, mkdtempSync, rmSync, writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
  afterEach, describe, expect, it, vi,
} from 'vitest';

// A SEPARATE spec file, deliberately — vi.mock('node:fs') is module-scoped and hoisted (see
// builder/tests/descriptorSort.spec.ts for the full rationale, and
// metrics/tests/thresholdTargetsSort.spec.ts for why an unmocked directory can't prove this:
// Node's own fs.globSync already returns matches in name order on this platform, so the mutant that
// drops resolveChains's `.sort()` on its `variable.glob` matches (loadingChains.mts) survives every
// test built on a real, unmocked filesystem). Reversing globSync's real result is enough to prove
// the sort is load-bearing without relying on any particular OS/filesystem's incidental ordering.
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

const { resolveChains } = await import('../loadingChains.mjs');

const dirs: string[] = [];

function workspace(): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-loading-chains-sort-'));
  dirs.push(root);
  return root;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('resolveChains applies its own sort to variable-glob matches, not an incidentally-sorted glob listing', () => {
  it('names chains in matched-filename order even when the underlying glob reports them reversed', () => {
    const root = workspace();
    mkdirSync(join(root, 'agents'));
    for (const name of ['zeta', 'mid', 'alpha']) {
      writeFileSync(join(root, 'agents', `${name}.md`), '- x\n', 'utf-8');
    }
    const chains = resolveChains(root, [{
      name: 't', fixed: [], variable: { glob: 'agents/*.md', label: 'agent' },
    }]);
    expect(chains.map((c) => c.name)).toEqual(['t: agents/alpha.md', 't: agents/mid.md', 't: agents/zeta.md']);
  });
});
