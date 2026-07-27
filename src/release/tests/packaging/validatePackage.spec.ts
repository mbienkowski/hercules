import { globSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

// vi.mock('node:fs') is module-scoped and hoisted (builder/tests/descriptor/descriptorSort.spec.ts has the
// fuller rationale). It wraps (not replaces) globSync so every test still hits the real repo's
// manifests, just with the RESULT ORDER reversed — proving marketplaces()'s own `.sort()` is
// load-bearing rather than riding an incidentally-sorted, filesystem-dependent glob result.
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return {
    ...actual,
    globSync: vi.fn((...args: Parameters<typeof actual.globSync>) => {
      const result = actual.globSync(...args);
      // Sorted-then-reversed, not a plain `.reverse()`: the raw glob order is guaranteed neither
      // alphabetical nor reverse-alphabetical, so a plain reverse could coincidentally produce a
      // sorted result. Sort-then-reverse is deterministically the opposite of sorted order.
      return Array.isArray(result) ? [...result].sort().reverse() : result;
    }),
  };
});

import { readVersions } from '../../../builder/versionTargets.mjs';
import { main, marketplaces, validateManifests } from '../../validatePackage.mjs';

// The failure-path tests call validateManifests() directly, isolating the "must list hercules" check
// from the rest of main()'s work — ESM import bindings cannot be reassigned from outside the module,
// so `marketplaces`/`checkInSync`/`readVersions` cannot be stubbed in place.

const dirs: string[] = [];

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('marketplaces()', () => {
  it('finds every ecosystem manifest', () => {
    const found = marketplaces();
    expect(found).toContain('.claude-plugin/marketplace.json');
    expect(found).toContain('.cursor-plugin/marketplace.json');
  });

  it('lists manifests in sorted order, not whatever order the (deliberately reverse-sorted, mocked) glob returned', () => {
    const found = marketplaces();
    expect(found).toEqual([...found].sort());
  });
});

describe('main()', () => {
  it('validates the real repo', () => {
    expect(() => main()).not.toThrow();
  });

  it('prints the exact manifest count, manifest list, and resolved version', () => {
    const originalWrite = process.stdout.write.bind(process.stdout);
    let out = '';
    process.stdout.write = ((chunk: string) => {
      out += chunk;
      return true;
    }) as typeof process.stdout.write;
    try {
      main();
    } finally {
      process.stdout.write = originalWrite;
    }
    const manifests = marketplaces();
    const version = [...new Set(Object.values(readVersions()))][0];
    expect(out).toBe(
      `plugin package valid (${manifests.length} marketplace manifest(s): ${manifests.join(', ')}); version ${version}\n`,
    );
  });

  it('fails closed when zero <eco>-plugin/marketplace.json manifests are found', () => {
    vi.mocked(globSync).mockReturnValueOnce([]);
    expect(() => main()).toThrow('no <eco>-plugin/marketplace.json found — expected at least .claude-plugin/');
  });
});

describe('validateManifests()', () => {
  it('fails if any marketplace omits hercules', () => {
    // A NON-Claude marketplace that omits hercules must fail the gate — proving the check covers
    // every ecosystem, not only .claude-plugin/.
    const dir = mkdtempSync(join(tmpdir(), 'hercules-validate-package-'));
    dirs.push(dir);
    const bad = join(dir, 'marketplace.json');
    writeFileSync(bad, JSON.stringify({ plugins: [{ name: 'not-hercules' }] }), 'utf-8');
    expect(() => validateManifests([bad])).toThrow(/must list the hercules plugin/);
  });

  it('fails on a manifest with no plugins array at all, not just an empty or wrong one', () => {
    // `mk.plugins ?? []` must default a MISSING key to an empty array so `.some()` still has
    // something to call rather than throwing on `undefined.some(...)`.
    const dir = mkdtempSync(join(tmpdir(), 'hercules-validate-package-'));
    dirs.push(dir);
    const bad = join(dir, 'marketplace.json');
    writeFileSync(bad, JSON.stringify({ name: 'no-plugins-key' }), 'utf-8');
    expect(() => validateManifests([bad])).toThrow(/must list the hercules plugin/);
  });

  it('passes when hercules is listed among other plugins, not only when it is the sole entry', () => {
    // Proves the check uses `.some(...)`, not `.every(...)`: for a single-plugin array the two are
    // indistinguishable, so this needs at least one OTHER plugin alongside hercules.
    const dir = mkdtempSync(join(tmpdir(), 'hercules-validate-package-'));
    dirs.push(dir);
    const ok = join(dir, 'marketplace.json');
    writeFileSync(ok, JSON.stringify({ plugins: [{ name: 'some-other-plugin' }, { name: 'hercules' }] }), 'utf-8');
    expect(() => validateManifests([ok])).not.toThrow();
  });
});
