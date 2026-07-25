/**
 * Validate the plugin package: every marketplace lists hercules + single-source version (`make validate`).
 *
 * Runs without any CLI — the live install smoke is the `smoke` job. Fails the build if any ecosystem's
 * marketplace manifest omits the plugin or the canonical version files disagree. Every
 * `<eco>-plugin/marketplace.json` is checked (`.claude-plugin/`, `.cursor-plugin/`, …) so a newly
 * added distribution's marketplace can't ship unvalidated.
 */

import { globSync, readFileSync } from 'node:fs';

import { checkInSync, readVersions } from '../builder/versionTargets.mjs';

interface MarketplaceManifest {
  readonly plugins?: ReadonlyArray<{ readonly name?: string }>;
}

/** Every ecosystem's marketplace manifest at the repo root (`.claude-plugin/`, `.cursor-plugin/`, …). */
export function marketplaces(): string[] {
  return globSync('.*-plugin/marketplace.json').sort();
}

/**
 * Throw if any of `manifests` omits the hercules plugin.
 *
 * Split out from `main()` (an addition over the Python original, purely for test benefit) so a test
 * can exercise the failure path directly against a fabricated manifest, rather than monkeypatching
 * `marketplaces`/`checkInSync`/`readVersions` — ESM import bindings aren't reassignable the way
 * Python's module attributes are.
 */
export function validateManifests(manifests: readonly string[]): void {
  for (const path of manifests) {
    const mk = JSON.parse(readFileSync(path, 'utf-8')) as MarketplaceManifest;
    // `?? []`'s only consumer is `.some(p => p.name === 'hercules')` immediately below: an absent
    // `plugins` key can therefore only ever produce `false` (no test manifest lacking `plugins` can
    // ever legitimately list hercules), identically whether the fallback is `[]` or any other
    // filler array — there is no element `.some()`'s predicate could match that would make a
    // fallback's specific CONTENTS observable. A TRUE equivalent mutant per CODE_OF_CONDUCT.md's
    // Testing section's pragma exception (a static literal default, not a branch/comparison).
    // Stryker disable next-line ArrayDeclaration: no fallback array's contents can ever satisfy .some(p => p.name === 'hercules') — see comment above
    const listsHercules = (mk.plugins ?? []).some((p) => p.name === 'hercules');
    if (!listsHercules) {
      throw new Error(`${path} must list the hercules plugin`);
    }
  }
}

export function main(): void {
  const manifests = marketplaces();
  if (manifests.length === 0) {
    throw new Error('no <eco>-plugin/marketplace.json found — expected at least .claude-plugin/');
  }
  validateManifests(manifests);
  checkInSync();
  const versions = new Set(Object.values(readVersions()));
  process.stdout.write(
    `plugin package valid (${manifests.length} marketplace manifest(s): ${manifests.join(', ')}); ` +
      `version ${[...versions][0]}\n`,
  );
}
