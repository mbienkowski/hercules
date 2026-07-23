/**
 * The single canonical list of version-bearing files.
 *
 * Consumed by BOTH the version writer and CI's `validate` job (reader) plus the release tag check,
 * so writer and reader can never drift (CoC "pin both ends / one canonical list"). Adding a
 * manifest is one entry here, no new code.
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { pyRepr, pyReprMapping } from './pyCompat.mjs';

export type VersionFormat = 'toml' | 'json';

/**
 * Only files that MUST carry a literal version belong here: `pyproject.toml` (setuptools reads it
 * at build) and `package.json` (npm and OpenCode read it as-is). The plugin manifests are
 * deliberately absent: they are build OUTPUTS whose sources carry a `${version}` token, injected at
 * build time by `emit.copyVersioned`, so a human never sees a literal version to forget to bump.
 */
export const VERSION_TARGETS: ReadonlyArray<readonly [string, VersionFormat]> = [
  ['pyproject.toml', 'toml'],
  ['package.json', 'json'],
];

/**
 * Write and read patterns per format.
 *
 * The `m` flag is a REGEX FLAG here, not an inline `(?m)` prefix as in the Python original. This is
 * not cosmetic: JavaScript has no inline-flag syntax, so `new RegExp('(?m)^(version…)')` throws
 * `Invalid regular expression: Invalid group` at construction. A literal transcription of the
 * Python pattern would therefore fail at MODULE LOAD, inside the exact code path CI's `validate`
 * job and the release pipeline run.
 */
const PATTERNS: Record<VersionFormat, { write: RegExp; read: RegExp }> = {
  toml: {
    write: /^(version\s*=\s*")[^"]+(")/m,
    read: /^version\s*=\s*"([^"]+)"/gm,
  },
  json: {
    write: /("version"\s*:\s*")[^"]+(")/,
    read: /"version"\s*:\s*"([^"]+)"/g,
  },
};

export class VersionError extends Error {
  override readonly name = 'VersionError';
}

/**
 * The one version match in `text`, or a loud failure.
 *
 * Guards against BOTH a missing version line and a SECOND one: a single-replacement substitution or
 * a first-match search silently accepts a duplicate, so a future nested field such as
 * `"engines": {"version": …}` could be mis-read or mis-written with no signal. Every occurrence is
 * counted and exactly one is required.
 */
// Messages below are byte-identical to the Python original's, snake_case names included, so the
// parity harness can diff stderr directly. That obligation ends when the Python compiler is deleted.
function soleVersionMatch(text: string, format: VersionFormat, rel: string): RegExpMatchArray {
  const matches = [...text.matchAll(PATTERNS[format].read)];
  if (matches.length !== 1) {
    throw new VersionError(
      `version_targets: expected exactly one version in ${rel}, found ${matches.length}`,
    );
  }
  return matches[0] as RegExpMatchArray;
}

/** Write `version` into every canonical file, in place, preserving formatting. */
export function writeVersion(version: string, root = '.'): void {
  for (const [rel, format] of VERSION_TARGETS) {
    const path = join(root, rel);
    const text = readFileSync(path, 'utf-8');
    soleVersionMatch(text, format, rel); // fail loud on zero or duplicate version fields
    // A function replacer, never a `$1…$2` string: a version containing `$&` would otherwise be
    // re-interpreted as a capture reference.
    const next = text.replace(PATTERNS[format].write, (_whole, prefix: string, suffix: string) =>
      `${prefix}${version}${suffix}`,
    );
    writeFileSync(path, next, 'utf-8');
  }
}

/** `{relativePath: version}` read from every canonical file. */
export function readVersions(root = '.'): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [rel, format] of VERSION_TARGETS) {
    const text = readFileSync(join(root, rel), 'utf-8');
    out[rel] = soleVersionMatch(text, format, rel)[1] as string;
  }
  return out;
}

/**
 * The single source of truth for the build's version: `pyproject.toml`.
 *
 * Build-consumed manifests (`dist/<eco>/…/plugin.json`) are INJECTED from this at build time, never
 * restating it, so a human reading a descriptor's versioned manifest sees a `${version}` token
 * rather than a literal they would have to remember to bump.
 */
export function readCanonicalVersion(root = '.'): string {
  return readVersions(root)['pyproject.toml'] as string;
}

/** Throw if the canonical files disagree, or (when given) differ from `expected`. */
export function checkInSync(root = '.', expected?: string): void {
  const versions = readVersions(root);
  const distinct = new Set(Object.values(versions));
  if (distinct.size !== 1) {
    throw new VersionError(`version drift across files: ${pyReprMapping(versions)}`);
  }
  const actual = [...distinct][0] as string;
  if (expected !== undefined && actual !== expected) {
    throw new VersionError(
      `version ${pyRepr(actual)} != expected ${pyRepr(expected)} (files: ${pyReprMapping(versions)})`,
    );
  }
}
