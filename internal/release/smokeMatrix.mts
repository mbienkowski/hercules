/**
 * Assemble the ecosystem smoke matrix (`make smoke-matrix`), writing `matrix=<json>` to
 * `$GITHUB_OUTPUT`. The ecosystem list comes from the recipe directory, so it cannot drift from
 * what ships.
 */

import { appendFileSync } from 'node:fs';

import { listRecipeNames } from '../builder/recipe-loader.mjs';
import { smokeTargets, type SmokeTarget } from './smoke-targets.mjs';

export class SmokeMatrixError extends Error {
  override readonly name = 'SmokeMatrixError';
}

interface SmokeLeg {
  readonly target: string;
  readonly cli: string;
  readonly test: string;
  readonly install_method: string;
  readonly npm_package: string;
  readonly npm_version: string;
  readonly install_url: string;
  readonly install_flags: string;
}

/**
 * The `{"include": [...]}` smoke matrix; fails CLOSED on a missing entry, a phantom one, or zero
 * legs — a skipped leg reads as success to GitHub, and an ungated build must not reach release.
 */
export function buildMatrix(
  registered: readonly string[] = listRecipeNames(),
  descriptors: Readonly<Record<string, SmokeTarget>> = smokeTargets(),
): { readonly include: readonly SmokeLeg[] } {
  const missing = registered.filter((name) => !(name in descriptors)).sort();
  if (missing.length > 0) {
    throw new SmokeMatrixError(
      'distributions with no entry in internal/release/smoke-targets.json (untestable, the gate '
        + `would skip them): ${JSON.stringify(missing)}`,
    );
  }
  const registeredSet = new Set(registered);
  const orphan = Object.keys(descriptors)
    .filter((name) => !registeredSet.has(name))
    .sort();
  if (orphan.length > 0) {
    throw new SmokeMatrixError(
      `smoke entries naming no distribution (phantom smoke legs): ${JSON.stringify(orphan)}`,
    );
  }

  const legs: SmokeLeg[] = [];
  for (const name of registered) {
    const gateConfig = descriptors[name] as SmokeTarget;
    // A typed union: each install method reads its own keys, none cast out of `unknown`.
    const install = gateConfig.install;
    legs.push({
      target: name,
      cli: gateConfig.cli,
      test: gateConfig.test,
      install_method: install?.method ?? 'none',
      npm_package: install?.method === 'package' ? install.name : '',
      npm_version: install?.method === 'package' ? install.version : '',
      install_url: install?.method === 'script' ? install.url : '',
      install_flags: install?.method === 'script' ? install.flags ?? '' : '',
    });
  }
  if (legs.length === 0) {
    throw new SmokeMatrixError('smoke matrix resolved to zero legs — the smoke gate would vanish');
  }
  return { include: legs };
}

export function main(): void {
  const matrix = buildMatrix();
  const line = 'matrix=' + JSON.stringify(matrix);
  // Echoed to the job log so a missing leg is debuggable from the Build output alone.
  const legs = matrix.include.map((leg) => leg.target);
  process.stdout.write(`smoke matrix (${legs.length} legs): ${legs.join(', ')}\n`);
  process.stdout.write(line + '\n');
  const out = process.env['GITHUB_OUTPUT'];
  if (out) {
    appendFileSync(out, line + '\n', 'utf-8');
  }
}
