import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * The repository root.
 *
 * This is the process working directory, inherited from whatever invoked the run. Vitest's `root`
 * option scopes spec DISCOVERY only — it never chdirs the process — so the guarantee here comes
 * from the entry points, not from Vitest:
 *
 *   - the Makefile's `test-ts` / `mutation-ts` targets and the npm `test` / `mutation` scripts all
 *     run from the repo root;
 *   - Stryker's runner child calls `process.chdir()` into its sandbox copy of the tree, so specs
 *     resolve against the copy rather than the original — which is what makes them valid there.
 *
 * Invoking `vitest` from a subdirectory therefore fails loudly with ENOENT on the first repo read,
 * rather than silently reading the wrong tree.
 *
 * A module-relative path is deliberately not used: it would need `import.meta` (unavailable in the
 * CommonJS type-check project) or `__dirname` (unavailable at ESM runtime).
 */
export const repoRoot = process.cwd();

export function readRepoFile(...segments: string[]): string {
  return readFileSync(join(repoRoot, ...segments), 'utf-8');
}

export function readRepoJson<T>(...segments: string[]): T {
  return JSON.parse(readRepoFile(...segments)) as T;
}
