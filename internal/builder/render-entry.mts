/**
 * One shipped file: each declared source rendered whole, in order, joined by a single newline.
 *
 * Frontmatter is not special here — it is text, so what a tool's metadata should say is written in
 * the source itself. Nothing trims, pads or normalises; a failure names the entry and the variable.
 */

import { readFileSync } from 'node:fs';

import type { Liquid } from 'liquidjs';

/** Raised when one entry's sources cannot be rendered. Carries the whole locating context. */
export class RenderEntryError extends Error {
  override readonly name = 'RenderEntryError';
}

/**
 * Read a source as UTF-8, refusing malformed bytes rather than shipping U+FFFD in their place.
 *
 * `ignoreBOM: true` KEEPS a byte-order mark; the default would strip it and silently change the
 * file's first byte.
 */
function readSource(path: string): string {
  try {
    return new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(readFileSync(path));
  } catch {
    throw new RenderEntryError(`${path}: not valid UTF-8`);
  }
}

/** Where a render failed, in the words a reader of the configuration would use. */
export interface EntryContext {
  /** The configuration file the entry came from, e.g. `src/targets/cursor.json`. */
  readonly config: string;
  /** The entry's key — the path under `dist/<name>/` this file ships at. */
  readonly dest: string;
  /** The names in scope, so the message can say what WAS available. */
  readonly declared: readonly string[];
}

/** The variable name a strict-mode failure is about, or null if it is a different kind of error. */
function undefinedVariable(message: string): string | null {
  const match = /undefined variable:\s*([^,\n]+)/.exec(message);
  return match === null ? null : (match[1] as string).trim();
}

function explain(error: unknown, ctx: EntryContext, source: string): string {
  const message = error instanceof Error ? error.message : String(error);
  const missing = undefinedVariable(message);
  const where = `${ctx.config} → '${ctx.dest}' ← ${source}`;
  if (missing === null) return `${where}: ${message}`;
  return (
    `${where}: You mentioned a variable that is not set in context for this ecosystem: ` +
    `'${missing}'. Declared here: ${ctx.declared.length === 0 ? '(none)' : ctx.declared.join(', ')}. ` +
    'Either add it to this configuration (every configuration that renders this source needs it, ' +
    'even when the value is false) or stop mentioning it.'
  );
}

/**
 * Render `sources` against `scope` and return the bytes to write.
 *
 * `repoRoot` is joined onto each source path by the caller's own resolver, passed in as `resolve`,
 * so this module performs no path arithmetic of its own and stays testable against a temp tree.
 */
export async function renderEntry(
  engine: Liquid,
  sources: readonly string[],
  scope: Readonly<Record<string, string | boolean>>,
  resolve: (source: string) => string,
  ctx: EntryContext,
): Promise<string> {
  const pieces: string[] = [];
  for (const source of sources) {
    const path = resolve(source);
    let text: string;
    try {
      text = readSource(path);
    } catch (error) {
      throw new RenderEntryError(
        `${ctx.config} → '${ctx.dest}': source '${source}' cannot be read — ` +
          `${error instanceof Error ? error.message : String(error)}`,
      );
    }
    try {
      pieces.push(await engine.parseAndRender(text, scope));
    } catch (error) {
      throw new RenderEntryError(explain(error, ctx, source));
    }
  }
  return pieces.join('\n');
}
