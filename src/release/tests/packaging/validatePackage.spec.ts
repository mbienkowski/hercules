import { globSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

// vi.mock('node:fs') is module-scoped and hoisted (see builder/tests/descriptor/descriptorSort.spec.ts for
// the fuller rationale) — it wraps (not replaces) globSync so every test still hits the real
// repo's manifests, just with the RESULT ORDER reversed. That proves marketplaces()'s own `.sort()`
// call is load-bearing rather than riding an incidentally-sorted glob result (real readdir order is
// filesystem-dependent, same concern descriptorSort.spec.ts documents for readdirSync), while
// leaving `main() validates the real repo` correct regardless — it never depends on manifest order.
// One test below further overrides this mock with `.mockReturnValueOnce([])` to reach main()'s
// zero-manifest branch without needing an actual manifest-free checkout.
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return {
    ...actual,
    globSync: vi.fn((...args: Parameters<typeof actual.globSync>) => {
      const result = actual.globSync(...args);
      // Sorted-then-reversed, not just `.reverse()`: the real filesystem's raw (pre-sort) glob
      // order is NOT guaranteed alphabetical OR reverse-alphabetical (it happens to already be
      // reverse-alphabetical on this checkout, which would make a plain `.reverse()` here
      // coincidentally UNDO that and produce an already-sorted result — defeating the whole point).
      // Sort-then-reverse is deterministically the opposite of sorted order for >= 2 distinct
      // entries, regardless of what the real glob's natural order happens to be.
      return Array.isArray(result) ? [...result].sort().reverse() : result;
    }),
  };
});

import { readVersions } from '../../../builder/versionTargets.mjs';
import { main, marketplaces, validateManifests } from '../../validatePackage.mjs';

// Ported from tests/build/test_validate_package.py. The Python original's failure-path test
// monkeypatched module attributes (vp._marketplaces, vp.check_in_sync, vp.read_versions) to isolate
// the "must list hercules" check from the rest of main()'s work; the TS port instead calls
// validateManifests() directly — an addition over the Python original, purely for this test's
// benefit, since ESM import bindings cannot be reassigned from outside the module.

const dirs: string[] = [];

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('marketplaces()', () => {
  it('finds every ecosystem manifest', () => {
    const found = marketplaces();
    expect(found).toContain('.claude-plugin/marketplace.json');
    expect(found).toContain('.cursor-plugin/marketplace.json'); // the one that used to ship unvalidated
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
