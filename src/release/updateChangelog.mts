/**
 * Generate a CHANGELOG entry from git log and write it to CHANGELOG.md.
 *
 * Used by the release workflow. Reads NEW_TAG, PREV_TAG, and IS_FIRST from the environment;
 * PREV_TAG is empty on the first release (no previous tags).
 */

import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';

/** Return all commit subjects reachable from HEAD but not from prevTag. */
export function getCommitsSince(prevTag: string): string[] {
  const revRange = prevTag ? `${prevTag}..HEAD` : 'HEAD';
  const out = execFileSync(
    'git',
    ['log', revRange, '--pretty=format:%s', '--no-merges'],
    { encoding: 'utf-8' },
  );
  return out
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith('chore(release):'));
}

function todayIso(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function formatEntry(newTag: string, commits: readonly string[]): string {
  const header = `## ${newTag} (${todayIso()})`;
  if (commits.length === 0) {
    return `${header}\n\n`;
  }
  const body = commits.map((c) => `* ${c}`).join('\n');
  return `${header}\n\n${body}\n\n`;
}

/**
 * Write a new release entry to the changelog at `path`.
 *
 * First release: overwrites the file (clears stale entries). Subsequent releases: prepends the
 * entry, keeping history below. Pass `commits` to skip the git-log call (useful in tests).
 */
export function updateChangelog(
  newTag: string,
  prevTag: string,
  isFirst: boolean,
  path = 'CHANGELOG.md',
  commits?: readonly string[],
): void {
  const resolvedCommits = commits ?? getCommitsSince(prevTag);
  const entry = formatEntry(newTag, resolvedCommits);
  if (isFirst) {
    writeFileSync(path, entry, 'utf-8');
  } else {
    const existing = existsSync(path) ? readFileSync(path, 'utf-8') : '';
    writeFileSync(path, entry + existing, 'utf-8');
  }
}

/**
 * Environment handling, split out from the entry point (`bin/updateChangelog.mts`) so it is fully
 * unit-testable. `updateChangelogFn` is injectable so a test can verify the env-var parsing without
 * touching real git or filesystem state; `updateChangelog` itself is covered by its own spec.
 */
export function main(
  env: NodeJS.ProcessEnv,
  updateChangelogFn: typeof updateChangelog = updateChangelog,
): void {
  const newTag = env['NEW_TAG'];
  if (newTag === undefined) {
    throw new Error("updateChangelog: environment variable 'NEW_TAG' is required");
  }
  updateChangelogFn(
    newTag,
    env['PREV_TAG'] ?? '',
    // The only consumer of `?? 'false'` is the `=== 'true'` on this same line, so every non-'true'
    // filler behaves identically for every possible environment — a TRUE equivalent mutant under
    // CODE_OF_CONDUCT.md's Testing pragma exception for behaviourally equivalent static strings.
    // Stryker disable next-line StringLiteral: any non-'true' fallback here is behaviorally identical once compared with === 'true' — see comment above
    (env['IS_FIRST'] ?? 'false').toLowerCase() === 'true',
  );
}
