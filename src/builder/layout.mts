/**
 * Source discovery for the build (a thin filesystem boundary): enumerates the `*.md` sources under
 * `content` in a stable order. `cli.buildTarget` maps each source to its per-target destination.
 */

import { readdirSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

/**
 * Compare two strings by Unicode CODE POINT.
 *
 * JavaScript's `<` compares UTF-16 code units, which orders supplementary-plane characters before
 * U+E000–U+FFFF instead of after. Filenames here are ASCII today, so this changes nothing yet; it is
 * here so the ordering does not quietly shift the day one is not. Exported so its branches can be
 * unit-tested with synthetic strings — APFS returns directory entries in name order regardless, so a
 * real-directory test on macOS passes even with the comparator disabled entirely.
 */
export function compareCodePoints(a: string, b: string): number {
  const left = [...a];
  const right = [...b];
  for (let pos = 0; pos < Math.min(left.length, right.length); pos += 1) {
    const leftCp = (left[pos] as string).codePointAt(0) as number;
    const rightCp = (right[pos] as string).codePointAt(0) as number;
    if (leftCp !== rightCp) return leftCp - rightCp;
  }
  return left.length - right.length;
}

/**
 * Order two paths by their PARTS, never as joined strings.
 *
 * `x/a/b` must sort before `x/a-c`; comparing the joined strings reverses that, because `-` (U+002D)
 * precedes `/` (U+002F). Today's `content/` tree sorts identically either way, so a plain sort would
 * pass every current fixture and silently reorder the build the first time a hyphenated filename
 * lands next to a directory sharing its prefix.
 */
export function comparePathParts(a: string, b: string): number {
  const left = a.split(sep);
  const right = b.split(sep);
  for (let pos = 0; pos < Math.min(left.length, right.length); pos += 1) {
    const cmp = compareCodePoints(left[pos] as string, right[pos] as string);
    if (cmp !== 0) return cmp;
  }
  return left.length - right.length;
}

/**
 * Every `*.md` source under `contentRoot`, in a stable (sorted) order. Absolute paths.
 *
 * The walk is manual rather than `readdirSync({recursive: true})` so entries classify correctly:
 *
 *   - a SYMLINK to a markdown file IS a source — its Dirent reports `isSymbolicLink()`, not
 *     `isFile()`, so an `isFile()` filter would silently drop it;
 *   - a symlinked DIRECTORY is NOT descended into — its Dirent reports `isDirectory() === false`,
 *     so recursing only on `isDirectory()` gets that for free.
 *
 * Entries are deliberately not `stat`ed: a dangling symlink would throw, and it belongs in the list.
 */
export function discoverSources(contentRoot: string): string[] {
  const found: string[] = [];

  const walk = (dir: string): void => {
    let entries;
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch (error) {
      // Only a missing content root is benign — a permission error, or a file where a directory was
      // expected, must still fail loudly.
      if ((error as NodeJS.ErrnoException).code === 'ENOENT' && dir === contentRoot) return;
      throw error;
    }
    for (const entry of entries) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith('.md')) found.push(full);
    }
  };

  walk(contentRoot);

  return found.sort((a, b) =>
    comparePathParts(relative(contentRoot, a), relative(contentRoot, b)),
  );
}
