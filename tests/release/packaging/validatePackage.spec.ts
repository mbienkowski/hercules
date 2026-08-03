import { globSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

// vi.mock('node:fs') is module-scoped and hoisted, so it lives alone. It wraps globSync with the
// RESULT ORDER reversed, forcing `main()`'s zero-manifest branch without an empty filesystem.
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return {
    ...actual,
    globSync: vi.fn((...args: Parameters<typeof actual.globSync>) => {
      const result = actual.globSync(...args);
      return Array.isArray(result) ? [...result].sort().reverse() : result;
    }),
  };
});

import { main, marketplaces, validateManifests } from '../../../internal/release/validatePackage.mjs';
import { tempWorkspace } from '../../support/tempWorkspace';

const workspace = tempWorkspace();

afterEach(workspace.cleanup);

// The happy path against the real manifests plus one fail-closed case (zero manifests found) — the
// manifest-shape details are review-obvious in the source.
describe('main()', () => {
  it('validates the real repo', () => {
    expect(() => main()).not.toThrow();
  });

  it('fails closed when zero <ecosystem>-plugin/marketplace.json manifests are found', () => {
    vi.mocked(globSync).mockReturnValueOnce([]);
    expect(() => main()).toThrow('no <ecosystem>-plugin/marketplace.json found — expected at least .claude-plugin/');
  });
});

describe('validateManifests()', () => {
  it('fails if any marketplace omits hercules', () => {
    const dir = workspace.make('hercules-validate-package-');
    const bad = join(dir, 'marketplace.json');
    writeFileSync(bad, JSON.stringify({ plugins: [{ name: 'not-hercules' }] }), 'utf-8');
    expect(() => validateManifests([bad])).toThrow(/must list the hercules plugin/);
  });
});

describe('marketplaces()', () => {
  it('finds every ecosystem manifest', () => {
    const found = marketplaces();
    expect(found).toContain('.claude-plugin/marketplace.json');
    expect(found).toContain('.cursor-plugin/marketplace.json');
  });
});
