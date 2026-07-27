import { mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { discoverSources } from '../../layout.mjs';

// A SEPARATE spec file, deliberately: `vi.mock('node:fs', ...)` is hoisted and module-scoped, so
// isolating it keeps layout.spec.ts on real filesystem behaviour, symlinks included. It must wrap the
// ACTUAL module — `vi.spyOn` on a `require('node:fs')` object mutates a separate CommonJS-interop
// object that discoverSources' own static import never observes.
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return {
    ...actual,
    readdirSync: vi.fn((...args: Parameters<typeof actual.readdirSync>) => {
      const result = (actual.readdirSync as (...a: unknown[]) => unknown)(...args);
      // Reverse only the withFileTypes Dirent[] form discoverSources actually requests.
      return Array.isArray(result) ? [...result].reverse() : result;
    }),
  };
});

const dirs: string[] = [];

function workspace(files: string[]): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-layout-sort-'));
  dirs.push(root);
  for (const rel of files) {
    mkdirSync(dirname(join(root, rel)), { recursive: true });
    writeFileSync(join(root, rel), 'x', 'utf-8');
  }
  return root;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('discoverSources applies its own sort, not an incidentally-sorted directory listing', () => {
  it('returns files in the correct order even when the filesystem reports them reversed', () => {
    // APFS's readdirSync returns entries in name order regardless of creation order (see layout.mts's
    // doc comment), so an unmocked walk cannot prove the explicit `.sort()` produces the order rather
    // than a lucky filesystem default. Reversing the listing removes the ambiguity: only a working
    // sort recovers the correct output from deliberately wrong input.
    const root = workspace(['a.md', 'b.md', 'c.md']);
    expect(readdirSync(root)).toEqual(['c.md', 'b.md', 'a.md']); // sanity: the mock is really active
    const result = discoverSources(root).map((p) => relative(root, p));
    expect(result).toEqual(['a.md', 'b.md', 'c.md']);
  });
});
