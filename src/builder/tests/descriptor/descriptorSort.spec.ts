import { mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { minimal } from '../../../commons/support/descriptorFixtures';

// APFS (Apple File System) already returns readdirSync entries in name order, so only a mocked walk
// proves the `.sort()` calls in discover/distFiles/validateLayout do real work. `vi.mock` is
// module-scoped, so this needs its own file — as in builder/tests/pipeline/layoutSort.spec.ts.
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

const { discover, distFiles } = await import('../../descriptor.mjs');

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
    // The order-sensitive proof is that this does not throw: validateLayout's internal sort must
    // agree with the loaded-descriptor set whatever order readdir returns.
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
    // Narrower than the test above, which re-sorts on the test side: asserting the RAW key order
    // pins discover()'s own internal `readdirSync(root).sort()`, so removing it turns this red.
    const root = workspace();
    for (const name of ['zebra', 'mango', 'apple']) {
      writeFileSync(join(root, `${name}.json`), JSON.stringify(minimal({ name })), 'utf-8');
    }
    expect(Object.keys(discover(root))).toEqual(['apple', 'mango', 'zebra']);
  });

  it('validateLayout reports the alphabetically-FIRST invalid sibling, not whatever order readdir happened to return', () => {
    // Without validateLayout's internal sort, the mocked-reversed readdir would report
    // 'zzz-stray.md' first: that sort decides WHICH error a multiply-broken directory reports.
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
