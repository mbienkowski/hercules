/**
 * Assemble the ecosystem smoke matrix from the build's target registry (invoked by `make smoke-matrix`).
 *
 * The ecosystem list comes from `descriptor.names()` — the SAME source the build dispatches on — so
 * the smoke matrix cannot drift from what actually ships. Each ecosystem's descriptor
 * (`src/ecosystems/<name>.json`) must declare a `smoke` section (its CLI + install method + smoke-test
 * path — schema-required); it becomes one parallel smoke leg that runs on every PR and on `main`. This
 * workflow uses `on: pull_request` with `permissions: contents: read` — a fork PR gets no repository
 * secrets — so every ecosystem's installer (npm-pinned or a script installer like Cursor's) runs on
 * PRs; the keyed live checks (e.g. Cursor's `cursor-agent -p` needing `CURSOR_API_KEY`) simply skip
 * when the secret is absent. NOTE: a script installer is not version-pinned (npm legs are), so a
 * change upstream at the installer URL can affect PR runs — pin it if that becomes flaky.
 *
 * Writes `matrix=<json>` to `$GITHUB_OUTPUT` when set, else prints it (for local inspection).
 */

import { appendFileSync } from 'node:fs';

import { discover, names as registeredTargetNames } from '../build/descriptor.mjs';

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
 * Fail CLOSED in three ways, because an empty/partial matrix expands to fewer jobs and GitHub counts
 * a skipped leg as success — which would let an ungated build reach release:
 *
 * - a registered ecosystem with no descriptor `smoke` config is untestable → error (don't skip it);
 * - a smoke config for an unregistered ecosystem is a phantom leg → error (don't smoke a ghost);
 * - a matrix that resolves to zero legs → error (the whole gate would vanish).
 *
 * `registered` (an addition over the Python original's hardcoded `registered_target_names()` call,
 * purely for test benefit — same rationale as cli.mts's `distRoot` params) lets a test inject a
 * fabricated registry to exercise the drift-detection branches directly, since ESM import bindings
 * cannot be monkeypatched the way Python's `smoke_matrix.registered_target_names` could.
 */
export function buildMatrix(
  registered: readonly string[] = registeredTargetNames(),
): { readonly include: readonly SmokeLeg[] } {
  const descriptors = discover();

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
    const install = (cfg['install'] as Record<string, unknown> | undefined) ?? { method: 'npm' };
    const method = (install['method'] as string | undefined) ?? 'npm';
    legs.push({
      target: name,
      cli: cfg['cli'] as string,
      test: cfg['test'] as string,
      install_method: method,
      npm_package: (cfg['npm_package'] as string | undefined) ?? '',
      npm_version: (cfg['npm_version'] as string | undefined) ?? '',
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
  // Always echo the resolved matrix to the job log — so an operator debugging "why did/didn't
  // ecosystem X get a smoke leg" can read the chosen list off the Build job's log — and additionally
  // write it to $GITHUB_OUTPUT when running under CI.
  const legs = matrix.include.map((leg) => leg.target);
  process.stdout.write(`smoke matrix (${legs.length} legs): ${legs.join(', ')}\n`);
  process.stdout.write(line + '\n');
  const out = process.env['GITHUB_OUTPUT'];
  if (out) {
    appendFileSync(out, line + '\n', 'utf-8');
  }
}
