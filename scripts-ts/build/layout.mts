/**
 * Source discovery for the build (thin filesystem boundary).
 *
 * Enumerates the `*.md` sources under `src/content` in a stable order for the serializers to
 * consume. `cli.buildTarget` maps each source to its per-target destination.
 */

import { readdirSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

/**
 * Compare two strings by Unicode CODE POINT, as Python does.
 *
 * JavaScript's `<` compares UTF-16 code units, which orders supplementary-plane characters before
 * U+E000–U+FFFF instead of after. Filenames here are ASCII today, so this changes nothing now — it
 * is here so that the day one is not, the ordering does not quietly shift.
 */
function compareCodePoints(a: string, b: string): number {
  const left = [...a];
  const right = [...b];
  for (let i = 0; i < Math.min(left.length, right.length); i += 1) {
    const x = (left[i] as string).codePointAt(0) as number;
    const y = (right[i] as string).codePointAt(0) as number;
    if (x !== y) return x - y;
  }
  return left.length - right.length;
}

/**
 * Order two paths the way Python's `sorted()` orders `pathlib.Path` objects.
 *
 * This is NOT a plain string comparison, and the difference is not academic. `pathlib` compares the
 * PARTS TUPLE, so `x/a/b` sorts before `x/a-c`; comparing the joined strings reverses that, because
 * `-` (U+002D) precedes `/` (U+002F). Today's `src/content/` tree happens to sort identically both
 * ways, so a plain sort would pass every current fixture and silently reorder the build the first
 * time someone adds a file whose name contains a hyphen next to a directory sharing its prefix.
 */
function comparePathParts(a: string, b: string): number {
  const left = a.split(sep);
  const right = b.split(sep);
  for (let i = 0; i < Math.min(left.length, right.length); i += 1) {
    const cmp = compareCodePoints(left[i] as string, right[i] as string);
    if (cmp !== 0) return cmp;
  }
  return left.length - right.length;
}

/**
 * Every `*.md` source under `contentRoot`, in a stable (sorted) order. Absolute paths.
 *
 * The walk is manual rather than `readdirSync({recursive: true})` so it can classify entries the
 * way Python's `rglob` does. Two behaviours matter and the recursive helper gets both wrong:
 *
 *   - a SYMLINK to a markdown file is a source. Its Dirent reports `isSymbolicLink()`, not
 *     `isFile()`, so an `isFile()` filter silently drops it while `rglob` includes it;
 *   - a symlinked DIRECTORY is not descended into, matching `rglob`, which does not follow them.
 *     A Dirent for one reports `isDirectory() === false`, so recursing only on `isDirectory()`
 *     reproduces that for free.
 *
 * Entries are deliberately not `stat`ed: a dangling symlink would throw, and `rglob` lists it.
 */
export function discoverSources(contentRoot: string): string[] {
  const found: string[] = [];

  const walk = (dir: string): void => {
    let entries;
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch (error) {
      // Python's `if not content_root.exists(): return []`. Only a missing directory is benign — a
      // permission error or a file where a directory was expected must still fail loudly.
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
