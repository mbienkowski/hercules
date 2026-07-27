/**
 * Assemble the ecosystem smoke matrix (invoked by `make smoke-matrix`), writing `matrix=<json>` to
 * `$GITHUB_OUTPUT` when set and printing it otherwise. The ecosystem list comes from
 * `descriptor.names()` — the same source the build dispatches on — so the matrix cannot drift from
 * what ships; each descriptor's schema-required `smoke` section becomes one parallel leg, and a leg
 * whose live check needs an absent secret skips rather than fails.
 */

import { appendFileSync } from 'node:fs';

import type { EcosystemDescriptor } from '../builder/descriptor.mjs';
import { discover, names as registeredTargetNames } from '../builder/descriptor.mjs';

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
 * Return the `{"include": [...]}` smoke matrix; throw on any drift or emptiness.
 *
 * Fails CLOSED three ways, because GitHub counts a skipped leg as success and an ungated build would
 * reach release: a registered ecosystem with no `smoke` config is untestable, a `smoke` config for an
 * unregistered ecosystem is a phantom leg, and a zero-leg matrix is no gate at all.
 *
 * `registered`/`descriptors` are injectable so a test can drive those branches with a fabricated
 * registry — ESM (ECMAScript modules) import bindings cannot be monkeypatched.
 */
export function buildMatrix(
  registered: readonly string[] = registeredTargetNames(),
  descriptors: Readonly<Record<string, EcosystemDescriptor>> = discover(),
): { readonly include: readonly SmokeLeg[] } {
  const missing = registered.filter((name) => !(name in descriptors)).sort();
  if (missing.length > 0) {
    throw new SmokeMatrixError(
      `registered ecosystems with no smoke.json config (untestable, gate would skip them): ${JSON.stringify(missing)}`,
    );
  }
  const registeredSet = new Set(registered);
  const orphan = Object.keys(descriptors)
    .filter((name) => !registeredSet.has(name))
    .sort();
  if (orphan.length > 0) {
    throw new SmokeMatrixError(
      `smoke config for unregistered ecosystems (phantom smoke legs): ${JSON.stringify(orphan)}`,
    );
  }

  const legs: SmokeLeg[] = [];
  for (const name of registered) {
    const cfg = descriptors[name]!.smoke;
    // Defaults to `{}`, not `{ method: 'npm' }`: only `install['method']` is read off this object,
    // and the next line already falls back to 'npm' — a `method` key here would be dead weight and
    // an unkillable mutation target.
    const install = (cfg.install as Record<string, unknown> | undefined) ?? {};
    const method = (install['method'] as string | undefined) ?? 'npm';
    legs.push({
      target: name,
      // `cli`/`test` are typed `string` by SmokeSchema, so they need no cast. The rest stay cast:
      // the schema deliberately leaves them `z.unknown()` (see SmokeSchema's own comment).
      cli: cfg.cli,
      test: cfg.test,
      install_method: method,
      npm_package: (cfg.npm_package as string | undefined) ?? '',
      npm_version: (cfg.npm_version as string | undefined) ?? '',
      install_url: (install['url'] as string | undefined) ?? '',
      install_flags: (install['flags'] as string | undefined) ?? '',
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
  // Always echo the resolved matrix to the job log, so an operator debugging "why did/didn't
  // ecosystem X get a smoke leg" can read the list off the Build job; also write it under CI.
  const legs = matrix.include.map((leg) => leg.target);
  process.stdout.write(`smoke matrix (${legs.length} legs): ${legs.join(', ')}\n`);
  process.stdout.write(line + '\n');
  const out = process.env['GITHUB_OUTPUT'];
  if (out) {
    appendFileSync(out, line + '\n', 'utf-8');
  }
}
