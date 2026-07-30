import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  CHAIN_TEMPLATES, HARD_GATE, resolveChains, WAIVERS, WARN_AT,
} from '../../loadingChains.mjs';
import { repoRoot } from '../../../commons/support/repo';

// Gates every loading chain's atomic instruction count directly against the absolute ceiling, with
// no per-role scaling — see loadingChains.mts for the chain data and instructionCounter.mts for the
// counting rules.

const DIST_CLAUDE_CODE = join(repoRoot, 'dist', 'claude-code');

describe('every loading chain stays within the instruction budget', () => {
  const chains = resolveChains(DIST_CLAUDE_CODE, CHAIN_TEMPLATES);
  const waiverByChain = new Map(WAIVERS.map((w) => [w.chain, w]));

  it.each(chains.map((c) => [c.name, c] as const))('%s', (_name, chain) => {
    const waiver = waiverByChain.get(chain.name);
    if (chain.value <= HARD_GATE) {
      // A waiver whose chain sits under the gate is dead weight: there is nothing left to waive.
      expect(waiver, `${chain.name}: measures ${chain.value} (under the gate) but still carries a waiver — delete it`).toBeUndefined();
      return;
    }
    expect(
      waiver,
      `${chain.name}: ${chain.value} instructions exceeds the ${HARD_GATE} gate ` +
        `(${[...chain.breakdown.entries()].map(([k, v]) => `${k}:${v}`).join(' + ')}) with no waiver on record`,
    ).toBeDefined();
    expect(
      chain.value,
      `${chain.name}: grew to ${chain.value}, past its waiver's pinned ${waiver?.measuredAt} — ` +
        'either the waiver needs updating (a reviewed diff) or the chain needs trimming back down',
    ).toBeLessThanOrEqual(waiver?.measuredAt as number);
  });
});

describe('every waiver names a chain that actually exists and actually breaches the gate', () => {
  it('no stale waivers', () => {
    const chains = resolveChains(DIST_CLAUDE_CODE, CHAIN_TEMPLATES);
    const byName = new Map(chains.map((c) => [c.name, c]));
    for (const waiver of WAIVERS) {
      const chain = byName.get(waiver.chain);
      expect(chain, `waiver names an unknown chain: '${waiver.chain}'`).toBeDefined();
      expect((chain?.value as number) > HARD_GATE, `'${waiver.chain}' no longer breaches the gate`).toBe(true);
    }
  });
});

describe('near-warn visibility', () => {
  it('flags chains within the warn margin without failing the build', () => {
    // WARN, not GATE: nothing fails here by design — a chain approaching the ceiling surfaces in
    // CI output before it breaches and needs a waiver.
    const chains = resolveChains(DIST_CLAUDE_CODE, CHAIN_TEMPLATES);
    const nearWarn = chains.filter((c) => c.value >= WARN_AT && c.value <= HARD_GATE);
    for (const c of nearWarn) {
      // eslint-disable-next-line no-console
      console.warn(`near warn: ${c.name} measures ${c.value} (warn margin ${WARN_AT}, gate ${HARD_GATE})`);
    }
    // No assertion on the count: this is deliberately warn-only. `expect(...).toBeGreaterThanOrEqual(0)`
    // stood here and was a tautology — a named passing test that could not fail, in the module whose
    // unit tests are its only gate.
  });

  /**
   * The gate values themselves, pinned as literals.
   *
   * Every other test compares a chain against whatever `HARD_GATE` and `WARN_AT` happen to hold, so
   * raising them to 400/380 left the whole suite green and silently deleted the constraint that
   * instruction-size increases be explicit, justified line items. `src/metrics/` is outside the mutation
   * gate, so nothing else would have caught it.
   */
  it('states the ceiling and the warn margin as reviewed numbers', () => {
    expect(HARD_GATE, 'the hard ceiling is grounded in arXiv:2507.11538 (IFScale) — adherence holds '
      + 'through roughly 150 instructions before declining. Changing it changes the research claim, so '
      + 'it is a reviewed decision, not an edit that rides along with a chain that outgrew it.')
      .toBe(150);
    expect(WARN_AT, 'the warn margin is ~87% of the ceiling, the room a chain has to grow before it '
      + 'needs a waiver. Raising it removes the early warning without touching the gate.').toBe(130);
    expect(WARN_AT, 'the margin must sit below the gate it warns about').toBeLessThan(HARD_GATE);
  });
});
