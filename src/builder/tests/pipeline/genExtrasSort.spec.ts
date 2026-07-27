import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

// A SEPARATE spec file, deliberately: `vi.mock('node:fs')` is module-scoped and hoisted, so it must
// live alone. An unmocked walk cannot prove roleEntries' `.sort(compareCodePoints)` does real work
// rather than riding a lucky filesystem default, since APFS already returns entries in name order.
// Full rationale: builder/tests/descriptor/descriptorSort.spec.ts.
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return {
    ...actual,
    readdirSync: vi.fn((...args: Parameters<typeof actual.readdirSync>) => {
      const result = (actual.readdirSync as (...a: unknown[]) => unknown)(...args);
      return Array.isArray(result) ? [...result].reverse() : result;
    }),
  };
});

const { discover } = await import('../../descriptor.mjs');
const { roleEntries } = await import('../../genExtras.mjs');
const { ECOSYSTEMS } = await import('../../../commons/support/descriptorFixtures');
const { repoRoot } = await import('../../../commons/support/repo');

describe('roleEntries applies its own sort, not an incidentally-sorted directory listing', () => {
  it('returns entries in stem order even when the filesystem reports them reversed', () => {
    const descriptors = discover(ECOSYSTEMS);
    const opencode = descriptors['opencode'];
    if (opencode === undefined) throw new Error('opencode descriptor missing');
    const srcContent = join(repoRoot, 'src', 'content');
    const entries = roleEntries(opencode, srcContent, new Map(Object.entries(opencode.vars)), 'agent');
    const stems = entries.map((e) => e.stem);
    expect(stems.length).toBeGreaterThan(1); // sanity: the sort has more than one element to prove
    expect(stems).toEqual([...stems].sort());
  });
});
