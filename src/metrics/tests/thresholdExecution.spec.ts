import { writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { countTokens } from '../tokenCounter.mjs';
import type { ThresholdCheck } from '../thresholdRunner.mjs';
import { loadThresholds, runThresholdChecks } from '../thresholdRunner.mjs';
import { runOneCheck, tmpWorkspace, writeThresholds } from './support';

// Ported from tests/metrics/test_threshold_execution.py — summed and per-file modes, warn_at,
// results, messages.

function check(overrides: Partial<ThresholdCheck> & Pick<ThresholdCheck, 'name' | 'target' | 'metric' | 'op' | 'limit'>): ThresholdCheck {
  return { severity: 'gate', warnAt: null, perFile: false, ...overrides };
}

describe('summed mode', () => {
  it('a valid threshold file passes all its checks', () => {
    const results = runOneCheck(
      tmpWorkspace(),
      { name: 'test-instruction-count', target: 'some.md', metric: 'instruction_count', op: '<=', limit: 100, severity: 'gate' },
      { 'some.md': '- bullet one\n- bullet two\n' },
    );
    expect(results).toHaveLength(1);
    expect(results[0]?.passed).toBe(true);
  });

  it('a check with no matching files fails instead of crashing', () => {
    const results = runOneCheck(
      tmpWorkspace(),
      { name: 'missing-target', target: 'nonexistent/*.md', metric: 'instruction_count', op: '<=', limit: 100, severity: 'gate' },
    );
    expect(results).toHaveLength(1);
    expect(results[0]?.passed).toBe(false);
    expect(results[0]?.message).toContain('matched no files');
  });

  it('a value past the warning level but under the limit still passes, flagged', () => {
    const results = runOneCheck(
      tmpWorkspace(),
      { name: 'warn-check', target: 'agent.md', metric: 'token_count', op: '<=', limit: 5000, warn_at: 10, severity: 'gate' },
      { 'agent.md': 'This is a test file with some content.\n'.repeat(5) },
    );
    expect(results[0]?.passed).toBe(true);
    expect(results[0]?.nearWarn).toBe(true);
  });

  it('a value exactly at the warning level (== limit) is still flagged', () => {
    const results = runOneCheck(
      tmpWorkspace(),
      { name: 'warn-equals-limit', target: 'f.md', metric: 'instruction_count', op: '<=', limit: 2, warn_at: 2, severity: 'gate' },
      { 'f.md': '- one\n- two\n' },
    );
    expect(results[0]?.passed).toBe(true);
    expect(results[0]?.nearWarn).toBe(true);
  });

  it('a check with no matching files reports a measured value of zero', () => {
    const results = runOneCheck(
      tmpWorkspace(),
      { name: 'empty-target', target: 'missing/*.md', metric: 'instruction_count', op: '<=', limit: 100, severity: 'gate' },
    );
    expect(results[0]?.value).toBe(0);
  });

  it('is never flagged as near-warn when no warn_at is configured, even though the check passes', () => {
    const results = runOneCheck(
      tmpWorkspace(),
      { name: 'no-warn-at', target: 'a.md', metric: 'instruction_count', op: '<=', limit: 100, severity: 'gate' },
      { 'a.md': '- one\n- two\n' },
    );
    expect(results[0]?.passed).toBe(true);
    expect(results[0]?.nearWarn).toBe(false);
  });

  it('a value comfortably below the warning level is not flagged', () => {
    const results = runOneCheck(
      tmpWorkspace(),
      { name: 'well-below-warn', target: 'g.md', metric: 'instruction_count', op: '<=', limit: 1000, warn_at: 500, severity: 'gate' },
      { 'g.md': '- one bullet\n' },
    );
    expect(results[0]?.nearWarn).toBe(false);
  });

  it('a later check still runs after an earlier check finds no files', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'missing', target: 'nonexistent/*.md', metric: 'instruction_count', op: '<=', limit: 100, severity: 'gate' },
      { name: 'present', target: 'real.md', metric: 'instruction_count', op: '<=', limit: 100, severity: 'gate' },
    ]);
    writeFileSync(join(root, 'real.md'), '- one\n');
    const results = runThresholdChecks(root, loadThresholds(file));
    expect(results).toHaveLength(2);
    expect(results[0]?.passed).toBe(false);
    expect(results[1]?.passed).toBe(true);
  });

  it('a check spanning multiple files adds up their counts', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'multi', target: '*.md', metric: 'instruction_count', op: '<=', limit: 1000, severity: 'gate' },
    ]);
    writeFileSync(join(root, 'a.md'), '- one\n- two\n'); // 2 instructions
    writeFileSync(join(root, 'b.md'), '- three\n'); // 1 instruction
    const results = runThresholdChecks(root, loadThresholds(file));
    expect(results[0]?.value).toBe(3); // must sum both files
  });

  it('a check with no matching files is never flagged as approaching its limit', () => {
    const root = tmpWorkspace();
    const file = writeThresholds(root, [
      { name: 'empty', target: 'missing/*.md', metric: 'instruction_count', op: '<=', limit: 100, severity: 'gate' },
    ]);
    expect(runThresholdChecks(root, loadThresholds(file))[0]?.nearWarn).toBe(false);
  });

  it('files are combined into one total unless a per-file limit is requested', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a.md'), 'a');
    writeFileSync(join(root, 'b.md'), 'b'); // two 1-token files; summed = 2 > limit 1
    const file = writeThresholds(root, [
      { name: 'sum-tokens', target: '*.md', metric: 'token_count', op: '<=', limit: 1, severity: 'gate' },
    ]);
    const checks = loadThresholds(file);
    const results = runThresholdChecks(root, checks);
    expect(checks[0]?.perFile).toBe(false);
    expect(results[0]?.passed).toBe(false);
  });

  it('an unrecognized comparison operator produces a clearly labeled error (summed mode)', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a.md'), 'x');
    // The `as` cast deliberately forges a check that could only exist if it bypassed loadThresholds —
    // proving the evaluate-time net still throws, not just the load-time validation.
    const bad = check({ name: 'bad', target: 'a.md', metric: 'token_count', op: '??' as ThresholdCheck['op'], limit: 1 });
    expect(() => runThresholdChecks(root, [bad])).toThrow(/^check/);
  });

  it('a failing check message reports the measured value and the required limit exactly', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a.md'), '- one\n- two\n- three\n');
    const c = check({ name: 'summed', target: 'a.md', metric: 'instruction_count', op: '<=', limit: 2 });
    const [result] = runThresholdChecks(root, [c]);
    expect(result?.passed).toBe(false);
    expect(result?.message).toBe('summed: instruction_count(a.md)=3, want <= 2');
  });
});

describe('per-file mode', () => {
  it('passes when every individual file is under the limit', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a.md'), 'aaa');
    writeFileSync(join(root, 'b.md'), 'bb');
    const file = writeThresholds(root, [
      { name: 'per-file-tokens', target: '*.md', metric: 'token_count', op: '<=', limit: 50, severity: 'gate', per_file: true },
    ]);
    expect(runThresholdChecks(root, loadThresholds(file))[0]?.passed).toBe(true);
  });

  it('a failure names only the files that broke it', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'small.md'), 'a');
    writeFileSync(join(root, 'big.md'), 'word '.repeat(100));
    const file = writeThresholds(root, [
      { name: 'per-file-tokens', target: '*.md', metric: 'token_count', op: '<=', limit: 5, severity: 'gate', per_file: true },
    ]);
    const result = runThresholdChecks(root, loadThresholds(file))[0];
    expect(result?.passed).toBe(false);
    expect(result?.message).toContain('big.md');
    expect(result?.message).not.toContain('small.md');
  });

  it('reports the single worst file and flags a warning off it, not a sum', () => {
    const root = tmpWorkspace();
    const big = 'alpha beta gamma delta epsilon';
    const small = 'x';
    writeFileSync(join(root, 'big.md'), big);
    writeFileSync(join(root, 'small.md'), small);
    const worst = Math.max(countTokens(big), countTokens(small));
    const file = writeThresholds(root, [
      { name: 'pf', target: '*.md', metric: 'token_count', op: '<=', limit: worst + 5, warn_at: worst, severity: 'gate', per_file: true },
    ]);
    const result = runThresholdChecks(root, loadThresholds(file))[0];
    expect(result?.passed).toBe(true);
    expect(result?.value, 'per_file must report the worst value, not the sum').toBe(worst);
    expect(result?.nearWarn, 'nearWarn fires when the worst value reaches warn_at').toBe(true);
  });

  it('is not flagged when every file stays below the warning level', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a.md'), 'x');
    const file = writeThresholds(root, [
      { name: 'pf', target: '*.md', metric: 'token_count', op: '<=', limit: 100, warn_at: 50, severity: 'gate', per_file: true },
    ]);
    const result = runThresholdChecks(root, loadThresholds(file))[0];
    expect(result?.passed).toBe(true);
    expect(result?.nearWarn).toBe(false);
  });

  it('an empty file counts as exactly zero', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'empty.md'), '');
    const file = writeThresholds(root, [
      { name: 'pf', target: '*.md', metric: 'token_count', op: '<=', limit: 5, severity: 'gate', per_file: true },
    ]);
    const result = runThresholdChecks(root, loadThresholds(file))[0];
    expect(result?.passed).toBe(true);
    expect(result?.value).toBe(0);
  });

  it('a failure lists every offending file, comma-separated, excluding compliant ones', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'big1.md'), 'word '.repeat(100));
    writeFileSync(join(root, 'big2.md'), 'word '.repeat(100));
    writeFileSync(join(root, 'ok.md'), 'x');
    const file = writeThresholds(root, [
      { name: 'pf', target: '*.md', metric: 'token_count', op: '<=', limit: 5, severity: 'gate', per_file: true },
    ]);
    const result = runThresholdChecks(root, loadThresholds(file))[0];
    expect(result?.passed).toBe(false);
    expect(result?.message).toContain('big1.md');
    expect(result?.message).toContain('big2.md');
    expect(result?.message).not.toContain('ok.md');
    expect(result?.message, 'multiple offenders must be comma-separated').toContain(', ');
  });

  it('an unrecognized comparison operator produces a clearly labeled error (per-file mode)', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a.md'), 'x');
    const badPf = check({ name: 'badpf', target: 'a.md', metric: 'token_count', op: '??' as ThresholdCheck['op'], limit: 1, perFile: true });
    expect(() => runThresholdChecks(root, [badPf])).toThrow(/^check/);
  });

  it('a passing check reports a clean summary with no offender list', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a.md'), '- one bullet\n');
    const c = check({ name: 'pf', target: 'a.md', metric: 'instruction_count', op: '<=', limit: 10, perFile: true });
    const [result] = runThresholdChecks(root, [c]);
    expect(result?.passed).toBe(true);
    expect(result?.message).toBe('pf: per-file instruction_count(a.md) want <= 10');
  });
});
