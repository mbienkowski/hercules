import { join } from 'node:path';

import { filesUnder } from '../support/buildTree';
import { readRepoFile, repoRoot } from '../support/repo';

/**
 * Shared support for the command-contract spec files under tests-ts/commands/.
 *
 * Ported from tests/conftest.py (repo root — the `read_file`/`section()` helpers and the
 * ALL_COMMANDS delivery-command paths) and tests/commands/conftest.py (the command-package-local
 * regex constants). Kept as one module — mirroring how the Python originals split the same
 * responsibility across two conftest.py files — so a rename updates one place, not many specs.
 */

// Delivery command file paths — shared so a rename updates one place, not two test modules
// (mirrors tests/conftest.py's ALL_COMMANDS fixture).
export const DISCOVER = 'dist/claude-code/commands/discover.md';
export const DESIGN = 'dist/claude-code/commands/design.md';
export const BUILD = 'dist/claude-code/commands/build.md';
export const WORKFLOW = 'dist/claude-code/commands/workflow.md';
export const SHIP = 'dist/claude-code/commands/ship.md';
export const ALL_COMMANDS = [DISCOVER, DESIGN, BUILD, WORKFLOW, SHIP];

const CLAUDE_MD = 'dist/claude-code/CLAUDE.md';
const REFERENCE_SKILL = 'dist/claude-code/skills/hercules-reference/SKILL.md';

/** Read a file relative to the repo root (mirrors pytest's `read_file` fixture). */
export function readFile(relPath: string): string {
  return readRepoFile(...relPath.split('/'));
}

/**
 * CLAUDE.md concatenated with the auto-loaded hercules-reference skill — the recurring
 * `read_file(CLAUDE.md) + "\n" + read_file(reference SKILL.md)` pin target repeated across the
 * Python originals, factored into one call.
 */
export function readPersona(): string {
  return `${readFile(CLAUDE_MD)}\n${readFile(REFERENCE_SKILL)}`;
}

/**
 * Slice `text` from `start` up to `stop` (or the end), failing LOUDLY.
 *
 * Ported from tests/conftest.py's `section()`. The bare prose-pin idiom
 * `text.slice(text.indexOf(a), text.indexOf(b))` silently returns `""` (or an inverted slice) on a
 * missing or renamed anchor; this turns that into an actionable error naming the marker and,
 * optionally, the file/label it was read from.
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
// "3am" (two letters, no boundary) is never flagged. `m` mirrors Python's re.MULTILINE for `^`.
export const LETTER_STEP_RE = /\bStep \d+[a-z]\b|^#+\s*\d+[a-z]\b|^\s*\*\*\d+[a-z]\b/gm;

/**
 * Every `.md` file recursed under dist/claude-code, as repo-root-relative POSIX paths — mirrors
 * `(repo_root / "dist" / "claude-code").rglob("*.md")` from the Python original.
 */
export function pluginMarkdownFiles(): string[] {
  const root = 'dist/claude-code';
  return Object.keys(filesUnder(join(repoRoot, root)))
    .filter((f) => f.endsWith('.md'))
    .map((f) => `${root}/${f}`);
}
