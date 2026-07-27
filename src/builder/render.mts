/**
 * Body token + switch rendering (pure, byte-preserving).
 *
 * Substitutes only a known **allowlist** of Hercules tokens; any other `${…}` (notably
 * `${CLAUDE_PLUGIN_ROOT}`, used in prose and hooks) passes through verbatim. Never normalises
 * whitespace — only marker spans change — so a Claude render reproduces the source bytes exactly.
 */

import { show } from './show.mjs';

const TOKEN = /\$\{([A-Za-z0-9_.]+)\}/g;
const DIRECTIVE = /^\$\{target:([^}]*)\}$/;
const TARGET_NAME = /^[a-z][a-z0-9-]*$/;

/** Raised on a malformed or unclosed `${target:…}` switch. */
export class RenderError extends Error {
  override readonly name = 'RenderError';
}

/**
 * Collect one switch's branch bodies, starting at `start` (the line AFTER the opening
 * `${target:openingName}`). Each `${target:name}` line opens a new branch; `${target:end}` closes
 * the switch. Returns the per-target line arrays plus the index of the first line past the `end`.
 * Throws on a malformed inner directive or a switch that never closes.
 */
function collectBranches(
  lines: readonly string[],
  openingName: string,
  start: number,
): { branches: Map<string, string[]>; nextIndex: number } {
  const branches = new Map<string, string[]>([[openingName, []]]);
  let current = openingName;
  let lineIndex = start;

  while (lineIndex < lines.length) {
    const directive = DIRECTIVE.exec(lines[lineIndex] as string);
    if (directive === null) {
      (branches.get(current) as string[]).push(lines[lineIndex] as string); // a body line of the current branch
      lineIndex += 1;
      continue;
    }
    const name = directive[1] as string;
    if (name === 'end') return { branches, nextIndex: lineIndex + 1 }; // closing fence — switch complete
    if (!TARGET_NAME.test(name)) {
      throw new RenderError(`malformed switch directive: ${show(lines[lineIndex] as string)}`);
    }
    current = name; // a new branch opens; subsequent body lines belong to it
    branches.set(name, []);
    lineIndex += 1;
  }
  throw new RenderError('unclosed `${target:…}` switch');
}

/** Pick the branch for `target`: exact key, then its short alias (claude-code -> claude), then default. */
function chooseBranch(branches: Map<string, string[]>, target: string): string[] {
  for (const key of [target, target.split('-')[0] as string, 'default']) {
    const branch = branches.get(key);
    if (branch !== undefined) return branch;
  }
  return [];
}

function resolveSwitches(text: string, target: string): string {
  // Plain '\n' split: this operates on an already-parsed body and must not re-interpret exotic line
  // boundaries the way frontmatter parsing does.
  const lines = text.split('\n');
  const out: string[] = [];
  let lineIndex = 0;

  while (lineIndex < lines.length) {
    const opening = DIRECTIVE.exec(lines[lineIndex] as string);
    if (opening === null) {
      out.push(lines[lineIndex] as string); // an ordinary line — copy it through unchanged
      lineIndex += 1;
      continue;
    }
    const name = opening[1] as string;
    if (name === 'end') throw new RenderError('`${target:end}` without an opening branch');
    if (!TARGET_NAME.test(name)) {
      throw new RenderError(`malformed switch directive: ${show(lines[lineIndex] as string)}`);
    }
    const { branches, nextIndex } = collectBranches(lines, name, lineIndex + 1);
    out.push(chooseBranch(branches, target).join('\n'));
    lineIndex = nextIndex;
  }

  return out.join('\n');
}

/**
 * Resolve `${target:…}` switches then `${var}` allowlist tokens for `target`.
 *
 * An unknown `${name}` (absent from `tokens`) passes through verbatim. Throws {@link RenderError}
 * only on a malformed or unclosed switch.
 */
export function renderBody(
  text: string,
  target: string,
  tokens: ReadonlyMap<string, string>,
): string {
  const resolved = resolveSwitches(text, target);
  // The replacer is a FUNCTION, not a string: a replacement value containing `$&` or `$1` would
  // otherwise be re-interpreted as a capture reference and corrupt the output.
  return resolved.replace(TOKEN, (whole, name: string) => tokens.get(name) ?? whole);
}
