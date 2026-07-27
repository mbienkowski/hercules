import { spawnSync } from 'node:child_process';

import { describe, expect, it } from 'vitest';

import { discover } from '../../descriptor.mjs';
import { which } from '../../../commons/support/which';

// Ported from tests/build/test_universal_smoke.py — the universal smoke driver: live CLI checks
// steered by each descriptor's `smoke.expect`.
//
// The commands to run and what to expect are per-ecosystem CONFIG (the descriptor's
// `smoke.expect`, closed vocabulary), so a new ecosystem gets its basic live check by declaring
// data — no new test file. Deep host-specific install flows (marketplace add/install/list,
// extension installs) stay as named tests in each ecosystem's own smoke file, pointed at by
// `smoke.test`.

const TIMEOUT_MS = 120_000;

it('every ecosystem declares its smoke expectations', () => {
  // Fail-closed: every descriptor must declare smoke.expect.version_cmd — a target cannot ship
  // without at least the basic live-CLI check being configured.
  for (const [name, d] of Object.entries(discover()).sort(([a], [b]) => a.localeCompare(b))) {
    const cmd = (d.smoke['expect'] as { version_cmd?: string[] } | undefined)?.version_cmd;
    expect(cmd, `${name}: smoke.expect.version_cmd missing from the descriptor`).toBeTruthy();
    expect((cmd as string[])[0], `${name}: version_cmd must invoke the declared cli`).toBe(d.smoke['cli']);
  }
});

describe('the declared version command succeeds when the cli is present', () => {
  // @pytest.mark.parametrize("name", sorted(discover())) becomes a one-`it()`-per-ecosystem loop,
  // matching the Python original's per-parametrization test granularity rather than one combined
  // test.
  for (const name of Object.keys(discover()).sort()) {
    const smoke = discover()[name]?.smoke as Record<string, unknown>;
    const cli = smoke['cli'] as string;

    it.skipIf(which(cli) === null)(`[${name}]`, () => {
      // With the real CLI installed (CI smoke legs; skipped locally when absent), the
      // descriptor's declared version command must exit 0 — a stub-on-PATH would not.
      const cmd = (smoke['expect'] as { version_cmd: string[] }).version_cmd;
      const res = spawnSync(cmd[0] as string, cmd.slice(1), { encoding: 'utf-8', timeout: TIMEOUT_MS });
      expect(res.status, `${name}: ${cmd.join(' ')} failed: ${res.stdout}\n${res.stderr}`).toBe(0);
    }, TIMEOUT_MS + 5_000);
  }
});
