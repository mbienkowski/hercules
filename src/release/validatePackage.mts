/**
 * Validate the plugin package (`make validate`): every `<eco>-plugin/marketplace.json` at the repo
 * root — `.claude-plugin/`, `.cursor-plugin/`, … — must list hercules, and the canonical version
 * files must agree. Runs without any CLI; the live install check is the `smoke` job.
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
 * Throw if any of `manifests` omits the hercules plugin. Split out from `main()` so a test can drive
 * the failure path against a fabricated manifest — ESM (ECMAScript modules) import bindings aren't
 * reassignable, so `marketplaces`/`checkInSync`/`readVersions` cannot be stubbed in place.
 */
export function validateManifests(manifests: readonly string[]): void {
  for (const path of manifests) {
    const mk = JSON.parse(readFileSync(path, 'utf-8')) as MarketplaceManifest;
    // The only consumer of `?? []` is the `.some(p => p.name === 'hercules')` below, and no fallback
    // array's contents could satisfy that predicate — a TRUE equivalent mutant under
    // CODE_OF_CONDUCT.md's Testing pragma exception for behaviourally equivalent static literals.
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
