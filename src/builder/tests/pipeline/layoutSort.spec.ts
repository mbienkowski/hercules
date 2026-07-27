import { mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { discoverSources } from '../../layout.mjs';

// A SEPARATE spec file, deliberately: `vi.mock('node:fs', ...)` is hoisted and module-scoped, so it
// would replace node:fs for every test in whatever file it lives in. Isolating it here keeps
// layout.spec.ts free to use real filesystem behaviour (symlinks included) everywhere else.
//
// The mock must wrap the ACTUAL node:fs module, not fabricate one: a `vi.spyOn` on a plain
// `require('node:fs')` object does NOT work for this — it mutates a separate CJS-interop object,
// while `discoverSources`'s own `import { readdirSync } from 'node:fs'` closed over the REAL
// binding at load time and never observes the spied one. `vi.mock` intercepts the module graph
// itself, which both forms of import resolve through.
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
    // APFS's readdirSync already returns entries in name order regardless of creation order (see
    // layout.mts's doc comment), so a real, unmocked directory walk cannot prove the explicit
    // `.sort()` call is what produces the correct order rather than a lucky filesystem default —
    // removing that call is a real Stryker mutant that survives every real-filesystem test on this
    // platform. Forcing readdirSync to return entries reversed removes that ambiguity: only a
    // working sort can recover the correct output from deliberately wrong input.
    const root = workspace(['a.md', 'b.md', 'c.md']);
    expect(readdirSync(root)).toEqual(['c.md', 'b.md', 'a.md']); // sanity: the mock is really active
    const result = discoverSources(root).map((p) => relative(root, p));
    expect(result).toEqual(['a.md', 'b.md', 'c.md']);
  });
});
