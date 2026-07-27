import { join } from 'node:path';
import { expect } from 'vitest';

import { parseDescriptor } from '../../builder/descriptor.mjs';
import { repoRoot } from './repo';

/** Shared across every descriptor.*.spec.ts file. */
export const ECOSYSTEMS = join(repoRoot, 'src', 'targets');

/** The minimal valid descriptor every case builds from — deep-cloned per call so one test's
 * overrides never leak into another's. */
export function minimal(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const base = {
    schema: 1,
    name: 'eco',
    vars: { product: 'Eco' },
    models: { high: null, medium: null, low: null },
    smoke: { cli: 'eco', test: 'builder/tests/smoke/ecoSmoke.spec.ts' },
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
 * Assert the EXACT rejection message, never a substring: a substring check lets an unrelated literal
 * fragment elsewhere in the same message mutate freely and still pass, which is precisely the class
 * of Stryker survivor a loose assertion leaves behind.
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
