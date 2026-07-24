import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach } from 'vitest';

import type { CheckResult } from '../../scripts-ts/metrics/thresholdRunner.mjs';
import { loadThresholds, runThresholdChecks } from '../../scripts-ts/metrics/thresholdRunner.mjs';

/**
 * Shared helpers for the threshold-runner test files, mirroring tests/metrics/conftest.py's
 * `_write_thresholds`/`_run_one_check`: setup lives in one place so each test body stays a
 * Given/When/Then that fits on one screen.
 */

const dirs: string[] = [];

/** A fresh scratch directory, cleaned up automatically after each test in the importing file. */
export function tmpWorkspace(): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-thresholds-'));
  dirs.push(root);
  return root;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

export function writeThresholds(root: string, checks: readonly Record<string, unknown>[]): string {
  const f = join(root, 'thresholds.json');
  writeFileSync(f, JSON.stringify(checks), 'utf-8');
  return f;
}

/**
 * Write a single-threshold config plus any named target files under `root`, run the checks, and
 * return the results. Behaviour-identical to writing the config inline then running.
 */
export function runOneCheck(
  root: string,
  config: Record<string, unknown>,
  files: Record<string, string> = {},
): CheckResult[] {
  const thresholdFile = writeThresholds(root, [config]);
  for (const [name, text] of Object.entries(files)) writeFileSync(join(root, name), text, 'utf-8');
  return runThresholdChecks(root, loadThresholds(thresholdFile));
}
