import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { main, marketplaces, validateManifests } from '../../scripts-ts/ci/validatePackage.mjs';

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
});

describe('main()', () => {
  it('validates the real repo', () => {
    expect(() => main()).not.toThrow();
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
});
