/**
 * The single canonical list of version-bearing files, read by both the writer and CI's `validate`
 * job — adding a manifest is one entry here, no new code.
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Render a value inside a build-error message: plain JSON (`"x"`, `["a","b"]`, `true`, `null`).
 *
 * Diagnostics only — these strings never reach `dist/`. `JSON.stringify` returns `undefined` for a
 * value it cannot encode (a function, a symbol), so `String` keeps this total. It used to be a
 * module of its own under `internal/builder/`, imported across the domain boundary by this one file
 * and needing its own mutation exclusion because there is nothing in it to mutate.
 */
function show(value: unknown): string {
  return JSON.stringify(value) ?? String(value);
}


type VersionFormat = 'toml' | 'json';

/**
 * Only files that MUST carry a literal version: `pyproject.toml` and `package.json`. Plugin
 * manifests are build OUTPUTS whose sources write `{{ version }}`, so nobody hand-bumps those.
 */
export const VERSION_TARGETS: ReadonlyArray<readonly [string, VersionFormat]> = [
  ['pyproject.toml', 'toml'],
  ['package.json', 'json'],
];

/**
 * Write and read patterns per format. Multiline is a REGEX FLAG (`m`), not an inline `(?m)` prefix —
 * JavaScript has no inline-flag syntax, so that would throw at MODULE LOAD.
 */

// `write` captures the text around the value as named groups `prefix`/`suffix`, so the replacer
// swaps only the value; `read` needs just the value, in one group.
const PATTERNS: Record<VersionFormat, { write: RegExp; read: RegExp }> = {
  toml: {
    write: /^(?<prefix>version\s*=\s*")[^"]+(?<suffix>")/m,
    read: /^version\s*=\s*"([^"]+)"/gm,
  },
  json: {
    write: /(?<prefix>"version"\s*:\s*")[^"]+(?<suffix>")/,
    read: /"version"\s*:\s*"([^"]+)"/g,
  },
};

class VersionError extends Error {
  override readonly name = 'VersionError';
}

/** The one version match in `text`, or a loud failure — zero or a second match both refuse. */
function soleVersionMatch(text: string, format: VersionFormat, relativePath: string): RegExpMatchArray {
  const matches = [...text.matchAll(PATTERNS[format].read)];
  if (matches.length !== 1) {
    throw new VersionError(
      `version_targets: expected exactly one version in ${relativePath}, found ${matches.length}`,
    );
  }
  return matches[0] as RegExpMatchArray;
}

// `root='.'` and `root=''` are indistinguishable through `path.join`, a true equivalent mutant.
// Stryker disable next-line StringLiteral: '.' and '' resolve identically through join(root, relativePath)
/** Write `version` into every canonical file, in place, preserving formatting. */
export function writeVersion(version: string, root = '.'): void {
  for (const [relativePath, format] of VERSION_TARGETS) {
    const path = join(root, relativePath);
    const text = readFileSync(path, 'utf-8');
    soleVersionMatch(text, format, relativePath); // fail loud on zero or duplicate version fields
    // A function replacer, never a `$1…$2` string: a version containing `$&` would otherwise be
    // re-interpreted as a capture reference.
    const next = text.replace(PATTERNS[format].write, (_whole, prefix: string, suffix: string) =>
      `${prefix}${version}${suffix}`,
    );
    writeFileSync(path, next, 'utf-8');
  }
}

// Same equivalent mutant as writeVersion()'s `root` default.
// Stryker disable next-line StringLiteral: same equivalence as writeVersion()'s root default
/** `{relativePath: version}` read from every canonical file. */
export function readVersions(root = '.'): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [relativePath, format] of VERSION_TARGETS) {
    const text = readFileSync(join(root, relativePath), 'utf-8');
    out[relativePath] = soleVersionMatch(text, format, relativePath)[1] as string;
  }
  return out;
}

/** The single source of truth for the build's version: `package.json`. */

// Same equivalent mutant as writeVersion()'s `root` default.
// Stryker disable next-line StringLiteral: same equivalence as writeVersion()'s root default
export function readCanonicalVersion(root = '.'): string {
  return readVersions(root)['package.json'] as string;
}

// Same equivalent mutant as writeVersion()'s `root` default.
// Stryker disable next-line StringLiteral: same equivalence as writeVersion()'s root default
/** Throw if the canonical files disagree, or (when given) differ from `expected`. */
export function checkInSync(root = '.', expected?: string): void {
  const versions = readVersions(root);
  const distinct = new Set(Object.values(versions));
  if (distinct.size !== 1) {
    throw new VersionError(`version drift across files: ${show(versions)}`);
  }
  const actual = [...distinct][0] as string;
  if (expected !== undefined && actual !== expected) {
    throw new VersionError(
      `version ${show(actual)} != expected ${show(expected)} (files: ${show(versions)})`,
    );
  }
}
