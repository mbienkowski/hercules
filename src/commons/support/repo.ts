import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * The repository root: the process working directory. Vitest's `root` option scopes spec discovery
 * only and never chdirs, so the guarantee comes from the entry points — the Makefile targets and npm
 * scripts run from the repo root, and Stryker's runner chdirs into its sandbox copy so specs resolve
 * against the mutated tree. Running `vitest` from a subdirectory therefore fails loudly with ENOENT
 * on the first repo read. A module-relative path is deliberately NOT used: it would resolve to the
 * original checkout under Stryker, scoring mutants against unmutated files.
 */
export const repoRoot = process.cwd();

export function readRepoFile(...segments: string[]): string {
  return readFileSync(join(repoRoot, ...segments), 'utf-8');
}

export function readRepoJson<T>(...segments: string[]): T {
  return JSON.parse(readRepoFile(...segments)) as T;
}

/**
 * Read a JSON file carrying `//` comments, as the tsconfig family does. Only whole comment LINES are
 * stripped, never a trailing `//`, so a value holding a URL survives intact — enough for the tsconfig
 * files without pulling in a JSONC (JSON with comments) parser for two assertions.
 */
export function readRepoJsonc<T>(...segments: string[]): T {
  const stripped = readRepoFile(...segments)
    .split('\n')
    .filter((line) => !line.trimStart().startsWith('//'))
    .join('\n');
  return JSON.parse(stripped) as T;
}
