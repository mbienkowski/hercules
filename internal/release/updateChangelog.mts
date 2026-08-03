/** Generate a CHANGELOG entry from git log and write it to CHANGELOG.md. */

import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';

/** Return all commit subjects reachable from HEAD but not from prevTag. */
function getCommitsSince(prevTag: string): string[] {
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

function formatEntry(newTag: string, commits: readonly string[]): string {
  const header = `## ${newTag} (${todayIso()})`;
  if (commits.length === 0) {
    return `${header}\n\n`;
  }
  const body = commits.map((c) => `* ${c}`).join('\n');
  return `${header}\n\n${body}\n\n`;
}

/** Write a release entry: overwrites on the first release, prepends after. */
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

/** Reads NEW_TAG/PREV_TAG/IS_FIRST from the environment for `bin/updateChangelog.mts`. */
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
    // Any non-'true' fallback is identical once compared with === 'true' — a true equivalent mutant.
    // Stryker disable next-line StringLiteral: any non-'true' fallback is identical against === 'true'
    (env['IS_FIRST'] ?? 'false').toLowerCase() === 'true',
  );
}
