/**
 * Leaf filesystem primitives for the build — no target knowledge.
 * Pure I/O (input/output): write a text file, or byte-copy a `src -> dest` map.
 */

import { copyFileSync, chmodSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

const VERSION_TOKEN = /\$\{version\}/g;

/**
 * The mode every emitted file carries, forced explicitly.
 *
 * `fs.copyFileSync` propagates the SOURCE's permission bits, so a source checked out 0755 would emit
 * an executable file. Every file in the committed `dist/` tree is git mode 100644, and a byte
 * comparison cannot see the difference — it would surface only as a spurious permission change later.
 */
const FILE_MODE = 0o644;

/** Raised when a versioned copy does not carry exactly one `${version}` token. */
export class EmitError extends Error {
  override readonly name = 'EmitError';
}

function writeFileWithParents(dest: string, text: string): void {
  mkdirSync(dirname(dest), { recursive: true });
  writeFileSync(dest, text, 'utf-8');
  chmodSync(dest, FILE_MODE);
}

/** Write `text` to `dest` (UTF-8), creating parent directories. */
export function write(dest: string, text: string): void {
  writeFileWithParents(dest, text);
}

/**
 * Read a source file as UTF-8, refusing a malformed byte sequence.
 *
 * `readFileSync(p, 'utf-8')` silently substitutes U+FFFD instead of failing, so without this check a
 * corrupted source would be baked into `dist/` rather than failing the build.
 */
export function readSource(path: string): string {
  const bytes = readFileSync(path);
  // `ignoreBOM: true` means "do not treat U+FEFF specially", i.e. KEEP it. TextDecoder's default
  // strips a leading byte-order mark, invisibly changing the first byte of a BOM-carrying source.
  const text = new TextDecoder('utf-8', { fatal: false, ignoreBOM: true }).decode(bytes);
  if (text.includes('�')) {
    // U+FFFD may legitimately appear in a source file; only flag it when DECODING manufactured it,
    // which a strict re-decode detects precisely. `ignoreBOM` only affects the decoded text — which
    // is discarded here — so it cannot change whether `.decode()` throws: a TRUE equivalent mutant
    // per CODE_OF_CONDUCT.md's Testing section's pragma exception.
    try {
      // Stryker disable next-line BooleanLiteral: ignoreBOM never affects whether a fatal decode throws — see comment above
      new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
    } catch {
      throw new EmitError(`${path}: not valid UTF-8`);
    }
  }
  return text;
}

/**
 * Copy `src` to `dest`, substituting the single `${version}` token with `version`.
 *
 * Deliberately NOT routed through `render`, whose token pass is fail-OPEN — an absent token survives
 * verbatim, shipping the literal `${version}` into a release manifest. This throws unless the token
 * count is exactly one, and is a pure string replace, so key order, indentation and the trailing
 * newline stay byte-identical.
 */
export function copyVersioned(src: string, dest: string, version: string): void {
  const text = readSource(src);
  const matches = text.match(VERSION_TOKEN);
  const count = matches === null ? 0 : matches.length;
  if (count !== 1) {
    throw new EmitError(
      `emit.copy_versioned: expected exactly one \${version} token in ${src}, found ${count}`,
    );
  }
  writeFileWithParents(dest, text.replace(VERSION_TOKEN, () => version));
}

/** Byte-copy each `srcDir/<src>` to `outRoot/<dest>`; return the written destination relatives. */
export function copyMap(
  srcDir: string,
  outRoot: string,
  mapping: ReadonlyMap<string, string>,
): string[] {
  const written: string[] = [];
  for (const [srcRel, destRel] of mapping) {
    const dest = join(outRoot, destRel);
    mkdirSync(dirname(dest), { recursive: true });
    copyFileSync(join(srcDir, srcRel), dest);
    chmodSync(dest, FILE_MODE);
    written.push(destRel);
  }
  return written;
}
