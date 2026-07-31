import { join } from 'node:path';

import { filesUnder } from '../../../commons/support/buildTree';
import { readRepoFile, repoRoot } from '../../../commons/support/repo';

/**
 * Shared support for the command-contract spec files under content/tests/commands/ — the command
 * paths, pin regexes, and read/slice helpers in one module, so a rename updates one place.
 */

// Delivery command file paths — shared so a rename updates one place, not every test module.
export const DISCOVER = 'dist/claude-code/commands/discover.md';
export const DESIGN = 'dist/claude-code/commands/design.md';
export const BUILD = 'dist/claude-code/commands/build.md';
export const WORKFLOW = 'dist/claude-code/commands/workflow.md';
export const SHIP = 'dist/claude-code/commands/ship.md';
export const PROJECT_RESET = 'dist/claude-code/commands/project-reset.md';
export const ALL_COMMANDS = [DISCOVER, DESIGN, BUILD, WORKFLOW, SHIP, PROJECT_RESET];

const CLAUDE_MD = 'dist/claude-code/CLAUDE.md';
const REFERENCE_SKILL = 'dist/claude-code/skills/hercules-reference/SKILL.md';

/** Read a file relative to the repo root. */
export function readFile(relPath: string): string {
  return readRepoFile(...relPath.split('/'));
}

/**
 * CLAUDE.md concatenated with the auto-loaded hercules-reference skill — together they form the
 * instruction surface an agent actually sees, and so the single pin target for persona prose.
 */
export function readPersona(): string {
  return `${readFile(CLAUDE_MD)}\n${readFile(REFERENCE_SKILL)}`;
}

/**
 * Slice `text` from `start` up to `stop` (or the end), failing LOUDLY.
 *
 * The bare prose-pin idiom `text.slice(text.indexOf(a), text.indexOf(b))` silently returns `""` (or
 * an inverted slice) on a missing or renamed anchor; this raises an error naming the marker instead.
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

export const BAD_DATE_RE = /YYYY-DD-MM/;
export const ISO_DATE_RE = /YYYY-MM-DD/;
// Letter-suffixed step labels (Step 4a, ## 1b, **4a --). Single letter + boundary so prose like
// "3am" (two letters, no boundary) is never flagged. The `m` flag anchors `^` per line.
export const LETTER_STEP_RE = /\bStep \d+[a-z]\b|^#+\s*\d+[a-z]\b|^\s*\*\*\d+[a-z]\b/gm;

/** Every `.md` file recursed under dist/claude-code, as repo-root-relative POSIX paths. */
export function pluginMarkdownFiles(): string[] {
  const root = 'dist/claude-code';
  return Object.keys(filesUnder(join(repoRoot, root)))
    .filter((f) => f.endsWith('.md'))
    .map((f) => `${root}/${f}`);
}
