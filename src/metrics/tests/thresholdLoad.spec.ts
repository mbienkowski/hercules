import { describe, expect, it } from 'vitest';

import { coreTokenCount, loadThresholds } from '../thresholdRunner.mjs';
import { tmpWorkspace, writeThresholds } from './support';

// Ported from tests/metrics/test_threshold_load.py — config loading, validation, load-time errors.

describe('loadThresholds: safe defaults', () => {
  it('a rule without optional settings gets safe defaults', () => {
    const [c] = loadThresholds(writeThresholds(tmpWorkspace(), [
      { name: 'n', target: 't', metric: 'token_count', op: '<=', limit: 1, severity: 'gate' },
    ]));
    expect(c?.warnAt).toBeNull();
    expect(c?.perFile).toBe(false);
  });
});

describe('loadThresholds: load-time validation errors', () => {
  it('an unknown metric name raises a clear error', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'bad-metric', target: 'x.md', metric: 'nonexistent_metric', op: '<=', limit: 100, severity: 'gate' },
    ]);
    expect(() => loadThresholds(file)).toThrow(/unknown metric/);
  });

  it('lists every known metric name, sorted, in the unknown-metric error', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'bad-metric', target: 'x.md', metric: 'nonexistent_metric', op: '<=', limit: 100, severity: 'gate' },
    ]);
    expect(() => loadThresholds(file)).toThrow(
      '["core_entry_count","core_token_count","instruction_count","token_count"]',
    );
  });

  it('an unknown severity value raises a clear error', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'bad-severity', target: 'x.md', metric: 'token_count', op: '<=', limit: 100, severity: 'error' },
    ]);
    expect(() => loadThresholds(file)).toThrow(/unknown severity/);
  });

  it('an early-warning level above the hard limit is rejected', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'bad-warn-at', target: 'x.md', metric: 'token_count', op: '<=', limit: 100, warn_at: 200, severity: 'gate' },
    ]);
    expect(() => loadThresholds(file)).toThrow(/warn_at/);
  });

  it('an unknown comparison operator raises a clear error', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'bad-op', target: 'x.md', metric: 'token_count', op: '!=', limit: 100, severity: 'gate' },
    ]);
    expect(() => loadThresholds(file)).toThrow(/unknown op/);
  });

  it('lists every known operator, sorted, in the unknown-op error', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'bad-op', target: 'x.md', metric: 'token_count', op: '!=', limit: 100, severity: 'gate' },
    ]);
    expect(() => loadThresholds(file)).toThrow('["<","<=","==",">",">="]');
  });

  it('a missing or empty name raises a clear error rather than surfacing as \'undefined\' downstream', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { target: 'x.md', metric: 'token_count', op: '<=', limit: 100, severity: 'gate' },
    ]);
    expect(() => loadThresholds(file)).toThrow(/missing or empty 'name'/);
  });

  it('a non-numeric limit is rejected loudly instead of string-coercing in the comparison', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'string-limit', target: 'x.md', metric: 'token_count', op: '<=', limit: '100', severity: 'gate' },
    ]);
    expect(() => loadThresholds(file)).toThrow(/'limit' must be a finite number/);
  });

  it('skips the warn_at-vs-limit check entirely when warn_at is not provided, even for a negative limit', () => {
    // If the omitted-check guard were dropped, a negative limit would make `warnAt > limit` (with
    // warnAt coerced from null to 0) spuriously true, and this would throw instead of loading clean.
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'neg-limit', target: 'f.md', metric: 'token_count', op: '<=', limit: -5, severity: 'gate' },
    ]);
    expect(() => loadThresholds(file)).not.toThrow();
  });
});

describe('coreTokenCount', () => {
  it('fails loudly instead of counting zero when the Core section is missing', () => {
    expect(() => coreTokenCount('This is plain markdown\n\n## No fence here\n'))
      .toThrow(/no fenced Core block found/);
  });
});

describe('loadThresholds: accepted values', () => {
  it('accepts the "warn" severity level', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'w', target: 'f.md', metric: 'token_count', op: '<=', limit: 100, severity: 'warn' },
    ]);
    expect(loadThresholds(file)[0]?.severity).toBe('warn');
  });

  it('accepts the equality comparison', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'eq', target: 'f.md', metric: 'token_count', op: '==', limit: 100, severity: 'gate' },
    ]);
    expect(loadThresholds(file)[0]?.op).toBe('==');
  });

  it('accepts the less-than comparison', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'lt', target: 'f.md', metric: 'token_count', op: '<', limit: 100, severity: 'gate' },
    ]);
    expect(loadThresholds(file)[0]?.op).toBe('<');
  });

  it('accepts the greater-than comparison', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'gt', target: 'f.md', metric: 'token_count', op: '>', limit: 100, severity: 'gate' },
    ]);
    expect(loadThresholds(file)[0]?.op).toBe('>');
  });

  it('defaults a rule without a severity to a hard gate', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'no-sev', target: 'f.md', metric: 'token_count', op: '<=', limit: 100 },
    ]);
    expect(loadThresholds(file)[0]?.severity).toBe('gate');
  });
});
