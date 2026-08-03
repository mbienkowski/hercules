/** Validate the plugin package (`make validate`): every marketplace manifest lists hercules. */

import { globSync, readFileSync } from 'node:fs';

import { checkInSync, readVersions } from './version-files.mjs';

interface MarketplaceManifest {
  readonly plugins?: ReadonlyArray<{ readonly name?: string }>;
}

/** Every ecosystem's marketplace manifest at the repo root (`.claude-plugin/`, `.cursor-plugin/`, …). */
export function marketplaces(): string[] {
  return globSync('.*-plugin/marketplace.json').sort();
}

/** Throw if any of `manifests` omits the hercules plugin. */
export function validateManifests(manifests: readonly string[]): void {
  for (const path of manifests) {
    const mk = JSON.parse(readFileSync(path, 'utf-8')) as MarketplaceManifest;
    // No fallback array could satisfy .some below — a true equivalent mutant.
    // Stryker disable next-line ArrayDeclaration: no fallback array can satisfy .some(p => p.name === 'hercules')
    const listsHercules = (mk.plugins ?? []).some((p) => p.name === 'hercules');
    if (!listsHercules) {
      throw new Error(`${path} must list the hercules plugin`);
    }
  }
}

export function main(): void {
  const manifests = marketplaces();
  if (manifests.length === 0) {
    throw new Error('no <ecosystem>-plugin/marketplace.json found — expected at least .claude-plugin/');
  }
  validateManifests(manifests);
  checkInSync();
  const versions = new Set(Object.values(readVersions()));
  process.stdout.write(
    `plugin package valid (${manifests.length} marketplace manifest(s): ${manifests.join(', ')}); ` +
      `version ${[...versions][0]}\n`,
  );
}
