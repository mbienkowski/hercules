/**
 * Body token + switch rendering (pure, byte-preserving).
 *
 * Substitutes only a known **allowlist** of Hercules tokens; any other `${…}` (notably
 * `${CLAUDE_PLUGIN_ROOT}`, used in prose and hooks) passes through verbatim. Never normalises
 * whitespace — only marker spans change — so a Claude render reproduces the source bytes exactly.
 */

import { pyRepr } from './pyCompat.mjs';

const TOKEN = /\$\{([A-Za-z0-9_.]+)\}/g;
const DIRECTIVE = /^\$\{target:([^}]*)\}$/;
const TARGET_NAME = /^[a-z][a-z0-9-]*$/;

/** Raised on a malformed or unclosed `${target:…}` switch. */
export class RenderError extends Error {
  override readonly name = 'RenderError';
}

function resolveSwitches(text: string, target: string): string {
  // Plain '\n' split, matching the Python original: this operates on an already-parsed body and
  // must not re-interpret exotic line boundaries the way frontmatter parsing does.
  const lines = text.split('\n');
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const opening = DIRECTIVE.exec(lines[i] as string);
    if (opening === null) {
      out.push(lines[i] as string);
      i += 1;
      continue;
    }

    const name = opening[1] as string;
    if (name === 'end') throw new RenderError('`${target:end}` without an opening branch');
    if (!TARGET_NAME.test(name)) {
      throw new RenderError(`malformed switch directive: ${pyRepr(lines[i] as string)}`);
    }

    const branches = new Map<string, string[]>([[name, []]]);
    let current = name;
    i += 1;
    let closed = false;

    while (i < lines.length) {
      const inner = DIRECTIVE.exec(lines[i] as string);
      if (inner !== null) {
        const innerName = inner[1] as string;
        if (innerName === 'end') {
          closed = true;
          i += 1;
          break;
        }
        if (!TARGET_NAME.test(innerName)) {
          throw new RenderError(`malformed switch directive: ${pyRepr(lines[i] as string)}`);
        }
        current = innerName;
        branches.set(innerName, []);
        i += 1;
        continue;
      }
      (branches.get(current) as string[]).push(lines[i] as string);
      i += 1;
    }

    if (!closed) throw new RenderError('unclosed `${target:…}` switch');

    // Match the full target key, then its short alias (claude-code -> claude), then default.
    let chosen: string[] = [];
    for (const key of [target, target.split('-')[0] as string, 'default']) {
      const branch = branches.get(key);
      if (branch !== undefined) {
        chosen = branch;
        break;
      }
    }
    out.push(chosen.join('\n'));
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
