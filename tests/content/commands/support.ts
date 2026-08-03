import { readRepoFile } from '../../support/repo';

/**
 * Shared support for the command-contract spec files under tests/content/commands/ — the command
 * paths and read/slice helpers in one module, so a rename updates one place.
 */

export const DISCOVER = 'dist/claude-code/commands/discover.md';
export const DESIGN = 'dist/claude-code/commands/design.md';
export const BUILD = 'dist/claude-code/commands/build.md';
export const WORKFLOW = 'dist/claude-code/commands/workflow.md';
export const SHIP = 'dist/claude-code/commands/ship.md';
export const PROJECT_RESET = 'dist/claude-code/commands/project-reset.md';

/** Read a file relative to the repo root. */
export function readFile(relPath: string): string {
  return readRepoFile(...relPath.split('/'));
}

/**
 * Slice `text` from `start` up to `stop` (or the end), failing LOUDLY: the bare
 * `text.slice(indexOf(a), indexOf(b))` idiom returns `""` on a missing or renamed anchor.
 */
export function section(text: string, start: string, stop?: string, label = ''): string {
  const where = label ? ` in ${label}` : '';
  const i = text.indexOf(start);
  if (i === -1) throw new Error(`section start marker not found${where}: ${JSON.stringify(start)}`);
  if (stop === undefined) return text.slice(i);
  const j = text.indexOf(stop, i + start.length);
  if (j === -1) throw new Error(`section stop marker not found after start${where}: ${JSON.stringify(stop)}`);
  return text.slice(i, j);
}

// Section window reused by several build.md tests (start <-> stop, lowercased).
export const RETIRE_STEP: readonly [string, string] = ['10. **retire the spec.**', 'for a spec scoped'];
