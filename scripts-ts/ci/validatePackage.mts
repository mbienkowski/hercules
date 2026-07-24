/**
 * Validate the plugin package: every marketplace lists hercules + single-source version (`make validate`).
 *
 * Runs without any CLI — the live install smoke is the `smoke` job. Fails the build if any ecosystem's
 * marketplace manifest omits the plugin or the canonical version files disagree. Every
 * `<eco>-plugin/marketplace.json` is checked (`.claude-plugin/`, `.cursor-plugin/`, …) so a newly
 * added distribution's marketplace can't ship unvalidated.
 */

import { globSync, readFileSync } from 'node:fs';

import { checkInSync, readVersions } from '../build/versionTargets.mjs';

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

// Only run when invoked directly (`node validatePackage.mjs`), not when imported by a test —
// matching Python's `if __name__ == "__main__":` guard.
if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}
