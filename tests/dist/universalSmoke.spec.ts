import { spawnSync } from 'node:child_process';

import { describe, expect, it } from 'vitest';

import { listRecipeNames } from '../../internal/builder/recipe-loader.mjs';
import { smokeTargets } from '../../internal/release/smoke-targets.mjs';
import { which } from '../support/which';

// The universal smoke driver: live CLI checks steered by each distribution's declaration in
// internal/release/smoke-targets.json, so a new ecosystem gets its live check from data alone.

const TIMEOUT_MS = 120_000;

const DECLARED = smokeTargets();
const DISTRIBUTIONS = listRecipeNames().sort();

it('every ecosystem declares its smoke expectations', () => {
  // Fail-closed: a target cannot ship without declaring `expect.version_cmd`.
  expect(DISTRIBUTIONS.length, 'no distributions were found').toBeGreaterThan(0);
  for (const name of DISTRIBUTIONS) {
    const declared = DECLARED[name];
    expect(declared, `${name}: no entry in internal/release/smoke-targets.json`).toBeDefined();
    const cmd = declared?.expect?.version_cmd;
    expect(cmd, `${name}: expect.version_cmd missing from the declaration`).toBeTruthy();
    expect((cmd as readonly string[])[0], `${name}: version_cmd must invoke the declared cli`)
      .toBe(declared?.cli);
  }
});

describe('the declared version command succeeds when the cli is present', () => {
  // One `it()` per ecosystem rather than one combined test, so a failing target is named directly.
  for (const name of DISTRIBUTIONS) {
    const declared = DECLARED[name];
    const cli = declared?.cli ?? '';

    it.skipIf(cli === '' || which(cli) === null)(`[${name}]`, () => {
      // With the real CLI installed, the declared version command must exit 0 — a stub would not.
      const cmd = (declared as { expect: { version_cmd: readonly string[] } }).expect.version_cmd;
      const res = spawnSync(cmd[0] as string, cmd.slice(1), { encoding: 'utf-8', timeout: TIMEOUT_MS });
      expect(res.status, `${name}: ${cmd.join(' ')} failed: ${res.stdout}\n${res.stderr}`).toBe(0);
    }, TIMEOUT_MS + 5_000);
  }
});
