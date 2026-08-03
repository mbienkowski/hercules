import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * The repository root: the process working directory, never a module-relative path — under Stryker
 * that would resolve to the original checkout, scoring mutants against unmutated files.
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
 * stripped, so a value holding a URL survives — enough without a JSONC (JSON with comments) parser.
 */
export function readRepoJsonc<T>(...segments: string[]): T {
  const stripped = readRepoFile(...segments)
    .split('\n')
    .filter((line) => !line.trimStart().startsWith('//'))
    .join('\n');
  return JSON.parse(stripped) as T;
}
