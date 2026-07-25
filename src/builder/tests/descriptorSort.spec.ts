import { mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { minimal } from '../../commons/support/descriptorFixtures';

// A SEPARATE spec file, deliberately — see builder/tests/layoutSort.spec.ts for the full
// rationale. In short: APFS's readdirSync already returns entries in name order regardless of
// creation order, so a real, unmocked directory walk cannot prove the explicit `.sort()` calls in
// discover/distFiles/validateLayout are doing real work rather than riding a lucky filesystem
// default. `vi.mock('node:fs')` is module-scoped and hoisted, so it must live in its own file to
// avoid affecting every other descriptor test.
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

const { discover, distFiles } = await import('../descriptor.mjs');

const dirs: string[] = [];

function workspace(): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-descriptor-sort-'));
  dirs.push(root);
  return root;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('discover and distFiles apply their own sort, not an incidentally-sorted listing', () => {
  it('registers descriptors in name order even when the filesystem reports them reversed', () => {
    const root = workspace();
    for (const name of ['alpha', 'beta', 'gamma']) {
      writeFileSync(join(root, `${name}.json`), JSON.stringify(minimal({ name })), 'utf-8');
    }
    expect(readdirSync(root)).toEqual(['gamma.json', 'beta.json', 'alpha.json']); // sanity: mocked
    // The order-sensitive proof is that this does not throw: validateLayout's own internal sort
    // must agree with the loaded-descriptor set regardless of readdir order, and Object.keys on the
    // resulting record preserves the INSERTION order this loop used (readdir-reversed), which a
    // caller that wants a stable list should read through names()/sort(), not this raw order.
    expect(() => discover(root)).not.toThrow();
    expect(Object.keys(discover(root)).sort()).toEqual(['alpha', 'beta', 'gamma']);
  });

  it('lists an ecosystem’s dist siblings in destination-name order even when the filesystem reports them reversed', () => {
    const root = workspace();
    mkdirSync(root, { recursive: true });
    writeFileSync(join(root, 'eco.json'), JSON.stringify(minimal({ name: 'eco' })), 'utf-8');
    writeFileSync(join(root, 'eco.dist.c.md'), 'c', 'utf-8');
    writeFileSync(join(root, 'eco.dist.a.md'), 'a', 'utf-8');
    writeFileSync(join(root, 'eco.dist.b.md'), 'b', 'utf-8');
    const files = distFiles('eco', root);
    expect(Object.keys(files)).toEqual(['a.md', 'b.md', 'c.md']);
  });

  it("discover()'s OWN returned record is keyed in sorted order, not merely sortable", () => {
    // The test above deliberately checks `Object.keys(...).sort()` (re-sorting on the test side) —
    // documented there as intentionally not pinning discover()'s raw order, since names() is the
    // sanctioned way for a CALLER to get a stable list. This is a narrower, separate claim: it pins
    // discover()'s OWN internal `readdirSync(root).sort()` (descriptor.mts line ~653) as a real,
    // load-bearing determinism property (matching the Python original's `sorted(root.glob(...))`),
    // not an incidental one — without re-sorting on the test side, so removing that internal .sort()
    // actually turns this red.
    const root = workspace();
    for (const name of ['zebra', 'mango', 'apple']) {
      writeFileSync(join(root, `${name}.json`), JSON.stringify(minimal({ name })), 'utf-8');
    }
    expect(Object.keys(discover(root))).toEqual(['apple', 'mango', 'zebra']);
  });

  it('validateLayout reports the alphabetically-FIRST invalid sibling, not whatever order readdir happened to return', () => {
    // With two stray files present, the mocked-reversed readdir would visit 'zzz-stray.md' before
    // 'aaa-stray.md' if validateLayout's own internal sort (descriptor.mts line ~603) were dropped —
    // proving that sort determines WHICH error a multiply-broken directory reports, the same
    // "validation order is a real contract" property this suite already pins for parseDescriptor's
    // section ordering.
    const root = workspace();
    writeFileSync(join(root, 'eco.json'), JSON.stringify(minimal({ name: 'eco' })), 'utf-8');
    writeFileSync(join(root, 'zzz-stray.md'), 'z', 'utf-8');
    writeFileSync(join(root, 'aaa-stray.md'), 'a', 'utf-8');
    let message = '<did not throw>';
    try {
      discover(root);
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toContain('aaa-stray.md');
    expect(message).not.toContain('zzz-stray.md');
  });
});
