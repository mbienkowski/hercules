/**
 * Comparing a fresh render against the committed `dist/` — what every marketplace installs from.
 *
 * Compares BYTES, never size or mtime, and MODE, so a permission change with identical bytes is
 * still caught.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

/** How a committed file and a freshly rendered one disagree. */
export interface Difference {
  /** The path, relative to the two roots being compared. */
  readonly relativePath: string;
  /** `content` — the bytes differ or the file exists on only one side; `mode` — bytes agree, permissions do not. */
  readonly kind: 'content' | 'mode';
}

/** Every file under `root`, as `/`-joined relative paths. Missing root reads as empty. */
export function listFilesUnder(root: string): Set<string> {
  const out = new Set<string>();
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === '__pycache__') continue;
        walk(full);
      } else if (entry.isFile() && !entry.name.endsWith('.pyc')) {
        out.add(relative(root, full).split(sep).join('/'));
      }
    }
  };
  try {
    walk(root);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return out;
    throw error;
  }
  return out;
}

/** The permission bits of `path`, as the three-digit octal string a recipe would write. */
export function readPermissionBits(path: string): string {
  // eslint-disable-next-line no-bitwise -- permission bits are exactly what is being read
  return (statSync(path).mode & 0o777).toString(8).padStart(3, '0');
}

/** Every way `a` and `b` disagree, by content first and then by mode. */
export function findDifferences(a: string, b: string): Difference[] {
  const aFiles = listFilesUnder(a);
  const bFiles = listFilesUnder(b);
  const out = new Map<string, Difference>();
  for (const relativePath of aFiles) if (!bFiles.has(relativePath)) out.set(relativePath, { relativePath, kind: 'content' });
  for (const relativePath of bFiles) if (!aFiles.has(relativePath)) out.set(relativePath, { relativePath, kind: 'content' });
  for (const relativePath of aFiles) {
    if (!bFiles.has(relativePath)) continue;
    if (!readFileSync(join(a, relativePath)).equals(readFileSync(join(b, relativePath)))) {
      out.set(relativePath, { relativePath, kind: 'content' });
      continue;
    }
    if (readPermissionBits(join(a, relativePath)) !== readPermissionBits(join(b, relativePath))) out.set(relativePath, { relativePath, kind: 'mode' });
  }
  return [...out.values()].sort((x, y) => (x.relativePath < y.relativePath ? -1 : x.relativePath > y.relativePath ? 1 : 0));
}

/** Say, per differing path, which fix applies — `make build` never prunes a stray file. */
export function describeDifferences(
  committed: string,
  rendered: string,
  differences: readonly Difference[],
): string[] {
  const inRendered = listFilesUnder(rendered);
  const inCommitted = listFilesUnder(committed);
  return differences.map(({ relativePath, kind }) => {
    if (!inRendered.has(relativePath)) return `${relativePath} — STRAY: present in dist/ but declared by no target; delete it`;
    if (!inCommitted.has(relativePath)) return `${relativePath} — MISSING from dist/; \`make build\` writes it`;
    if (kind === 'mode') {
      const committedMode = readPermissionBits(join(committed, relativePath));
      const renderedMode = readPermissionBits(join(rendered, relativePath));
      return `${relativePath} — MODE ${committedMode} in dist/, ${renderedMode} rendered; `
        + "the entry's `permissions` and the committed file disagree";
    }
    return `${relativePath} — STALE content; \`make build\` refreshes it`;
  });
}
