/**
 * Shared helpers for the docs/plugin specs, ported from tests/conftest.py's `ALL_COMMANDS` and
 * `section()`. Kept local to this directory rather than added to src/commons/support/ — nothing
 * outside docsAndPlugin/ needs them.
 */

const DISCOVER = 'dist/claude-code/commands/discover.md';
const DESIGN = 'dist/claude-code/commands/design.md';
const BUILD = 'dist/claude-code/commands/build.md';
const WORKFLOW = 'dist/claude-code/commands/workflow.md';
const SHIP = 'dist/claude-code/commands/ship.md';

export const ALL_COMMANDS: readonly string[] = [DISCOVER, DESIGN, BUILD, WORKFLOW, SHIP];

/**
 * Slice `text` from `start` up to `stop` (or the end), failing LOUDLY.
 *
 * The prose-pin idiom `text.slice(text.indexOf(a), text.indexOf(b))` dies with a silent `-1`
 * turning into an empty or inverted slice; this helper turns a missing or renamed anchor into an
 * actionable thrown error naming the marker and the file. `stop` is searched AFTER `start`, so a
 * window can never silently invert or bind to an earlier occurrence.
 */
export function section(text: string, start: string, stop?: string, label = ''): string {
  const i = text.indexOf(start);
  if (i === -1) {
    throw new Error(`section start marker not found${label ? ` in ${label}` : ''}: ${JSON.stringify(start)}`);
  }
  if (stop === undefined) return text.slice(i);
  const j = text.indexOf(stop, i + start.length);
  if (j === -1) {
    throw new Error(`section stop marker not found after start${label ? ` in ${label}` : ''}: ${JSON.stringify(stop)}`);
  }
  return text.slice(i, j);
}

/** The shape of dist/claude-code/.claude-plugin/plugin.json this directory's specs read. */
export interface PluginManifest {
  name?: string;
  description?: string;
  version: string;
  author?: unknown;
  license?: string;
}
