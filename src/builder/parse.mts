/**
 * Frontmatter + document parsing (pure).
 *
 * `parseFrontmatter` / `renderFrontmatter` round-trip today's clean `key: value` frontmatter
 * byte-for-byte (proven by the keystone gate in the frontmatter round-trip suite).
 * `splitDocument` is the byte-preserving splitter Claude-target rendering relies on.
 */

import { pySplitlines, pyStrip } from './pyCompat.mjs';

const FENCE = '---';

export interface Frontmatter {
  metadata: Map<string, string>;
  body: string;
}

/**
 * Return `{metadata, body}` for a markdown document.
 *
 * A document with no `---` fence yields `({}, strip(text))`. Values are stripped, so this is *not*
 * byte-preserving — use {@link splitDocument} when exact bytes matter.
 *
 * `metadata` is a Map rather than an object: insertion order is the emitted key order, and a plain
 * object would reorder any key that looks like an array index (`"1"`, `"0"`) to the front.
 */
export function parseFrontmatter(text: string): Frontmatter {
  const stripped = pyStrip(text);
  if (!stripped.startsWith(FENCE)) return { metadata: new Map(), body: stripped };

  // Split on FENCE *lines*, not the bare substring: a frontmatter VALUE containing "---" (e.g.
  // `description: pros --- cons`) must not be mistaken for the closing fence, which would truncate
  // the value and silently drop every key after it.
  const lines = pySplitlines(stripped);
  let close = -1;
  for (let i = 1; i < lines.length; i += 1) {
    if (pyStrip(lines[i] as string) === FENCE) {
      close = i;
      break;
    }
  }
  if (close === -1) return { metadata: new Map(), body: stripped };

  const metadata = new Map<string, string>();
  for (const line of lines.slice(1, close)) {
    const at = line.indexOf(':');
    if (at === -1) continue;
    metadata.set(pyStrip(line.slice(0, at)), pyStrip(line.slice(at + 1)));
  }
  return { metadata, body: pyStrip(lines.slice(close + 1).join('\n')) };
}

/** Render an ordered `metadata` map to a `---`-fenced YAML block (no trailing newline). */
export function renderFrontmatter(metadata: ReadonlyMap<string, string>): string {
  const lines = [FENCE];
  for (const [key, value] of metadata) lines.push(`${key}: ${value}`);
  lines.push(FENCE);
  return lines.join('\n');
}

export interface SplitDocument {
  /** The raw frontmatter block including both fences, or null when there is none. */
  block: string | null;
  body: string;
}

/**
 * Split into `{block, body}` losslessly: `(block ?? '') + body === text`.
 *
 * A frontmatter block is present only when `text` opens with `---\n` and a later line is exactly
 * `---`. The returned block includes both fences and the single newline after the closing fence;
 * the body is returned verbatim (never stripped).
 */
export function splitDocument(text: string): SplitDocument {
  if (!text.startsWith(`${FENCE}\n`)) return { block: null, body: text };
  // `close` is the index of the '\n' immediately BEFORE the closing fence (search skips the opening
  // fence). So the fence itself starts one char later, and ends after its own width.
  const close = text.indexOf(`\n${FENCE}`, FENCE.length + 1);
  if (close === -1) return { block: null, body: text };
  const closingFenceStart = close + 1;
  let blockEnd = closingFenceStart + FENCE.length; // just past the closing "---"
  if (blockEnd < text.length && text[blockEnd] === '\n') blockEnd += 1; // include the trailing newline
  return { block: text.slice(0, blockEnd), body: text.slice(blockEnd) };
}
