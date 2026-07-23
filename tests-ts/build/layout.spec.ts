import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative, sep } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

import { discoverSources } from '../../scripts-ts/build/layout.mjs';

const dirs: string[] = [];

function workspace(files: string[]): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-layout-'));
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

const relativeTo = (root: string, paths: string[]): string[] => paths.map((p) => relative(root, p));

describe('finding the markdown sources to compile', () => {
  it('finds them at every depth', () => {
    const root = workspace(['a.md', 'x/b.md', 'x/y/c.md']);
    expect(relativeTo(root, discoverSources(root)).sort()).toEqual(['a.md', 'x/b.md', 'x/y/c.md']);
  });

  it('ignores files that are not markdown', () => {
    const root = workspace(['a.md', 'notes.txt', 'x/data.json']);
    expect(relativeTo(root, discoverSources(root))).toEqual(['a.md']);
  });

  it('returns nothing when the content directory does not exist', () => {
    // A missing root is benign — a target may ship no content of a given kind.
    expect(discoverSources(join(tmpdir(), 'hercules-layout-absent-xyz'))).toEqual([]);
  });

  it('returns nothing for an empty directory', () => {
    expect(discoverSources(workspace([]))).toEqual([]);
  });
});

describe('the order sources are compiled in', () => {
  it('is stable rather than filesystem order', () => {
    // Filesystem order is not guaranteed, and it differs between APFS locally and ext4 on the CI
    // runner — exactly where an unsorted walk diverges silently.
    const root = workspace(['c.md', 'a.md', 'b.md']);
    expect(relativeTo(root, discoverSources(root))).toEqual(['a.md', 'b.md', 'c.md']);
  });

  it('orders a directory ahead of a sibling file whose name shares its prefix', () => {
    // The subtle one. Python sorts Path objects by their PARTS TUPLE, so `x/a/b.md` precedes
    // `x/a-c.md`; sorting the joined strings reverses that, because '-' precedes '/'. Today's
    // src/content/ tree happens to sort identically either way, so a plain string sort would pass
    // every other fixture here and silently reorder the build the first time someone added a
    // hyphenated file beside a directory sharing its prefix.
    const root = workspace(['x/a-c.md', 'x/a/b.md']);
    expect(relativeTo(root, discoverSources(root))).toEqual([join('x', 'a', 'b.md'), join('x', 'a-c.md')]);
  });

  it('orders a nested file ahead of a sibling whose name extends the directory name', () => {
    // Verified against CPython: comparing the parts tuples puts 'a' before 'a.md', so x/a/b.md
    // sorts BEFORE x/a.md. Reading it as "shorter path first" gets this backwards.
    const root = workspace(['x/a.md', 'x/a/b.md']);
    expect(relativeTo(root, discoverSources(root))).toEqual([join('x', 'a', 'b.md'), join('x', 'a.md')]);
  });
});

describe('comparing paths segment by segment', () => {
  it('orders by the first segment that differs, not by overall length', () => {
    const root = workspace(['b/a.md', 'a/z.md']);
    expect(relativeTo(root, discoverSources(root))).toEqual([join('a', 'z.md'), join('b', 'a.md')]);
  });

  it('orders a shorter path before a longer one that starts with it', () => {
    const root = workspace(['x/y/a.md', 'x/y/a/b.md']);
    expect(relativeTo(root, discoverSources(root))).toEqual([
      join('x', 'y', 'a', 'b.md'),
      join('x', 'y', 'a.md'),
    ]);
  });

  it('orders siblings within the same directory', () => {
    const root = workspace(['x/b.md', 'x/a.md', 'x/c.md']);
    expect(relativeTo(root, discoverSources(root))).toEqual([
      join('x', 'a.md'),
      join('x', 'b.md'),
      join('x', 'c.md'),
    ]);
  });

  it('reports a real filesystem failure instead of pretending there are no sources', () => {
    // Only a MISSING root is benign. Swallowing every error would turn a permissions problem or a
    // file-where-a-directory-was-expected into a silently empty build.
    const root = workspace(['a.md']);
    expect(() => discoverSources(join(root, 'a.md'))).toThrow();
  });
});

describe('following symbolic links the way Python does', () => {
  it('treats a symlink to a markdown file as a source', () => {
    // Node's Dirent reports isSymbolicLink(), not isFile(), so an isFile() filter would silently
    // drop it while Python's rglob includes it — a source vanishing from the build with no error.
    const root = workspace(['real/target.md', 'root/plain.md']);
    symlinkSync(join(root, 'real/target.md'), join(root, 'root/linked.md'));
    const names = discoverSources(join(root, 'root')).map((p) => p.split(sep).pop());
    expect(names.sort()).toEqual(['linked.md', 'plain.md']);
  });

  it('lists a dangling symlink rather than failing on it', () => {
    // Python's rglob lists it without stat-ing it. Stat-ing here would throw on a broken link and
    // fail the whole build over a stray file.
    const root = workspace(['root/plain.md']);
    symlinkSync(join(root, 'root/nowhere.md'), join(root, 'root/dangling.md'));
    const names = discoverSources(join(root, 'root')).map((p) => p.split(sep).pop());
    expect(names.sort()).toEqual(['dangling.md', 'plain.md']);
  });

  it('does not descend into a symlinked directory', () => {
    // rglob does not follow directory symlinks. Following one would compile the same source twice
    // under two paths, or loop forever on a cycle.
    const root = workspace(['real/deep.md', 'root/plain.md']);
    symlinkSync(join(root, 'real'), join(root, 'root/linkeddir'));
    const names = discoverSources(join(root, 'root')).map((p) => p.split(sep).pop());
    expect(names).toEqual(['plain.md']);
  });
});
