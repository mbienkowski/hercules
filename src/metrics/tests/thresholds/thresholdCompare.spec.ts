import { describe, expect, it } from 'vitest';

import { compareValue } from '../../thresholdRunner.mjs';

// Ported from tests/metrics/test_threshold_compare.py.

describe('compareValue', () => {
  it('gives the right pass/fail verdict for every supported comparison rule', () => {
    expect(compareValue(7, '==', 7)).toEqual([true, '']);
    expect(compareValue(8, '==', 7)).toEqual([false, '']);
    expect(compareValue(7, '<=', 20)).toEqual([true, '']);
    expect(compareValue(21, '<=', 20)).toEqual([false, '']);
    expect(compareValue(130, '>=', 100)).toEqual([true, '']);
    expect(compareValue(5, '<', 10)).toEqual([true, '']);
    expect(compareValue(10, '<', 10)).toEqual([false, '']);
    expect(compareValue(10, '>', 9)).toEqual([true, '']);

    const [, err] = compareValue(1, '??', 1);
    expect(err).not.toBe('');
  });

  it.each([
    [20, '<=', 20, true], // at boundary
    [21, '<=', 20, false], // over boundary
    [100, '>=', 100, true], // at boundary
    [99, '>=', 100, false], // under boundary
    [42, '==', 42, true], // exact match
    [42, '==', 43, false], // off by one (value < limit)
    [43, '==', 42, false], // off by one (value > limit)
    [9, '<', 10, true], // strictly below
    [10, '<', 10, false], // at limit — must fail for strict <
    [11, '>', 10, true], // strictly above
    [10, '>', 10, false], // at limit — must fail for strict >
  ] as const)('judges a metric exactly at its limit consistently: %s %s %s -> %s', (value, op, limit, expected) => {
    expect(compareValue(value, op, limit)).toEqual([expected, '']);
  });

  it('fails safe with a clear reason for an unrecognized comparison rule', () => {
    const [passed, err] = compareValue(1, '??', 1);
    expect(passed).toBe(false);
    expect(err.startsWith('unknown op')).toBe(true);
  });
});
