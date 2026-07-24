import { describe, expect, it } from 'vitest';

import { names as registeredTargetNames } from '../../scripts-ts/build/descriptor.mjs';
import { SmokeMatrixError, buildMatrix } from '../../scripts-ts/ci/smokeMatrix.mjs';

// Ported from tests/build/test_ci_smoke_matrix.py's unit-level (build_matrix()) assertions. The
// CI-job-graph assertions (smoke/mutation `needs`/`if` wiring) live in tests-ts/releasePipeline.spec.ts
// instead — they parse the workflow YAML directly and never call buildMatrix().
//
// The Python original monkeypatched GITHUB_REF and asserted the matrix was the same either way — but
// buildMatrix() (like build_matrix() before it) never reads that env var at all; the matrix is a pure
// function of the descriptor registry. That assertion is preserved here as "every ecosystem is present
// regardless of context" without actually touching the environment, since there is nothing to fake.

function legsByTarget(): Record<string, ReturnType<typeof buildMatrix>['include'][number]> {
  const legs = buildMatrix().include;
  return Object.fromEntries(legs.map((leg) => [leg.target, leg]));
}

describe('the smoke matrix', () => {
  it('includes every registered ecosystem, including the script-installed one', () => {
    const legs = legsByTarget();
    expect(Object.keys(legs)).toEqual(expect.arrayContaining(['claude-code', 'opencode', 'cursor']));
    expect(legs['cursor']?.install_method).toBe('script');
    expect(legs['claude-code']?.install_method).toBe('npm');
  });

  it('every leg carries the fields the install and run scripts read', () => {
    const legs = legsByTarget();
    for (const leg of Object.values(legs)) {
      expect(leg).toHaveProperty('target');
      expect(leg).toHaveProperty('cli');
      expect(leg).toHaveProperty('test');
      expect(leg).toHaveProperty('install_method');
    }
  });

  it('the matrix targets come from the build registry, not an independently maintained list', () => {
    const legs = legsByTarget();
    expect(new Set(Object.keys(legs))).toEqual(new Set(registeredTargetNames()));
  });

  it('a registered ecosystem missing its smoke.json fails closed', () => {
    // A ghost ecosystem the real descriptor registry does not know about — not undiscoverable, just
    // fabricated for this test via the injectable `registered` param.
    expect(() =>
      buildMatrix(['claude-code', 'opencode', 'cursor', 'ghost-ecosystem']),
    ).toThrowError(SmokeMatrixError);
    expect(() => buildMatrix(['claude-code', 'opencode', 'cursor', 'ghost-ecosystem'])).toThrow(
      /no smoke\.json/,
    );
  });

  it('a smoke.json for an unregistered ecosystem fails closed', () => {
    // cursor's descriptor (with its smoke.json config) exists on disk but is deliberately left out
    // of this fabricated registry — a phantom leg the real build never produces.
    expect(() => buildMatrix(['claude-code', 'opencode'])).toThrowError(SmokeMatrixError);
    expect(() => buildMatrix(['claude-code', 'opencode'])).toThrow(/unregistered ecosystems/);
  });
});
