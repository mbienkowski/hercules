import { join } from 'node:path';
import { expect } from 'vitest';

import { parseDescriptor } from '../../builder/descriptor.mjs';
import { repoRoot } from './repo';

/** Shared across every descriptor.*.spec.ts file — see builder/tests/descriptor.spec.ts's header
 * comment for why the suite is split across files in the first place. */
export const ECOSYSTEMS = join(repoRoot, 'src', 'targets');

/**
 * The same minimal valid skeleton test_descriptor_schema.py builds every case from — deep-cloned
 * per call so mutating one test's overrides never leaks into another's.
 */
export function minimal(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const base = {
    schema: 1,
    name: 'eco',
    vars: { product: 'Eco' },
    models: { high: null, medium: null, low: null },
    smoke: { cli: 'eco', test: 'tests/build/test_eco_smoke.py' },
    dispatch: 'path',
    roles: {
      agent: { mode: 'preserve' },
      command: { mode: 'preserve' },
      persona: { mode: 'plain' },
      default: { mode: 'preserve' },
    },
    routes: [],
  };
  return JSON.parse(JSON.stringify({ ...base, ...overrides })) as Record<string, unknown>;
}

export function withAgentRole(agentRole: unknown): Record<string, unknown> {
  const raw = minimal();
  (raw['roles'] as Record<string, unknown>)['agent'] = agentRole;
  return raw;
}

/**
 * Every message asserted via this helper is checked for EXACT equality, not a substring. A
 * substring check lets an unrelated literal fragment elsewhere in the SAME message mutate freely
 * and still pass — exactly the class of Stryker survivor a loose assertion leaves behind. Each
 * caller is independently proven correct against the Python original by the parity fixture of the
 * same name under tests/testdata/parity/descriptor-*.in.json.
 */
export function expectMessage(build: () => unknown, expected: string): void {
  let message = '<did not throw>';
  try {
    parseDescriptor('eco', build());
  } catch (error) {
    message = (error as Error).message;
  }
  expect(message).toBe(expected);
}
