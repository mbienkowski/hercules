import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  CHAIN_TEMPLATES, HARD_GATE, resolveChains, WAIVERS, WARN_AT,
} from '../loadingChains.mjs';
import { repoRoot } from '../../tests/support/repo';

// Replaces tests/budgets/test_instruction_budget.py. That file counted "instruction blocks"
// (bullets/numbers/bold-labels — one block bundles 2-4 real directives) and divided the 150
// research ceiling by 3, giving three independently-guessed gates (35/55/20). This gates the ONE
// atomic count (`countAtomicInstructions`) directly against the absolute ceiling, no scaling — see
// loadingChains.mts's own top comment for why chain definitions are data here, and
// instructionCounter.mts for why the counter shipped without a vocabulary filter.

const DIST_CLAUDE_CODE = join(repoRoot, 'dist', 'claude-code');

describe('every loading chain stays within the instruction budget', () => {
  const chains = resolveChains(DIST_CLAUDE_CODE, CHAIN_TEMPLATES);
  const waiverByChain = new Map(WAIVERS.map((w) => [w.chain, w]));

  it.each(chains.map((c) => [c.name, c] as const))('%s', (_name, chain) => {
    const waiver = waiverByChain.get(chain.name);
    if (chain.value <= HARD_GATE) {
      // A waiver whose chain no longer breaches the gate is dead weight — the fix landed, the
      // waiver should have been deleted with it.
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
    // No assertion failure here by design (WARN, not GATE) — this test exists so a chain
    // approaching the ceiling shows up in CI output rather than only being noticed once it
    // actually breaches and needs a waiver.
    const chains = resolveChains(DIST_CLAUDE_CODE, CHAIN_TEMPLATES);
    const nearWarn = chains.filter((c) => c.value >= WARN_AT && c.value <= HARD_GATE);
    for (const c of nearWarn) {
      // eslint-disable-next-line no-console
      console.warn(`near warn: ${c.name} measures ${c.value} (warn margin ${WARN_AT}, gate ${HARD_GATE})`);
    }
    expect(nearWarn.length).toBeGreaterThanOrEqual(0);
  });
});
