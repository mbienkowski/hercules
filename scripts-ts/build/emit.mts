/**
 * Leaf filesystem primitives for the build — no target knowledge.
 *
 * Pure I/O: write a text file, or byte-copy a `src -> dest` map.
 */

import { copyFileSync, chmodSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

const VERSION_TOKEN = /\$\{version\}/g;

/**
 * The mode every emitted file carries.
 *
 * Python's `shutil.copyfile` copies CONTENT ONLY and leaves the destination at the process umask;
 * Node's `fs.copyFileSync` propagates the SOURCE's permission bits. Left alone, a source checked
 * out as 0755 would emit an executable file into `dist/` under Node and a 0644 one under Python.
 * Every file in the committed `dist/` tree is git mode 100644, so the divergence is invisible to a
 * byte comparison — `diff -r` and `cmp` compare content, not modes — and would surface only as a
 * spurious permission change in a later commit.
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
 * Read a source file as UTF-8, refusing invalid input the way Python does.
 *
 * `Path.read_text(encoding='utf-8')` RAISES on a malformed byte sequence; Node's
 * `readFileSync(p, 'utf-8')` silently substitutes U+FFFD. Without this check a corrupted source
 * would build cleanly under Node and refuse to build under Python — the two engines disagreeing
 * about whether the repository is even valid.
 */
export function readSource(path: string): string {
  const bytes = readFileSync(path);
  // `ignoreBOM: true` means "do not treat U+FEFF specially", i.e. KEEP it. TextDecoder's default
  // silently strips a leading byte-order mark while Python's read_text preserves it — which would
  // change the first byte of any BOM-carrying source in dist/, invisibly, in the very function
  // written to close the UTF-8 decoding divergence.
  const text = new TextDecoder('utf-8', { fatal: false, ignoreBOM: true }).decode(bytes);
  if (text.includes('�')) {
    // U+FFFD may legitimately appear in a source file; only flag it when it was MANUFACTURED by
    // decoding, which a strict re-decode detects precisely.
    try {
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
 * Deliberately NOT routed through `render` (whose token pass is fail-OPEN: an unknown or absent
 * token survives verbatim, which for a version field would silently ship the literal `${version}`
 * into a release manifest). This is a targeted substitution that throws unless the token count is
 * exactly one — the same fail-LOUD contract as `versionTargets.writeVersion`. A pure string replace
 * with no JSON re-serialisation, so key order, indentation and the trailing newline are preserved
 * exactly, keeping `dist/` byte-identical.
 */
export function copyVersioned(src: string, dest: string, version: string): void {
  const text = readSource(src);
  const matches = text.match(VERSION_TOKEN);
  const count = matches === null ? 0 : matches.length;
  if (count !== 1) {
    // Byte-identical to the Python original's message, snake_case name included, so the parity
    // harness can diff stderr directly. That obligation ends when the Python compiler is deleted.
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
