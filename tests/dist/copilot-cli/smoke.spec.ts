import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { repoRoot } from '../../support/repo';
import { tempWorkspace } from '../../support/tempWorkspace';
import { which } from '../../support/which';
import { scratchHome } from '../smokeHarness';

// Live Copilot CLI smoke, plus the always-on guard that is Copilot's alone: it is the only host whose
// hook config carries a per-SHELL command pair, so its write gate can be wired on POSIX and not Windows.

const DIST = join(repoRoot, 'dist', 'copilot-cli');
const TIMEOUT_MS = 60_000;

const workspace = tempWorkspace();
afterEach(workspace.cleanup, 30_000);

it('the write gate is wired for both shells Copilot may launch', () => {
  // A missing shell is silent: Copilot lets the edit through, so half the installed base loses the gate.
  const hooks = JSON.parse(readFileSync(join(DIST, 'hooks', 'hooks.json'), 'utf-8')) as {
    hooks: { preToolUse?: Array<{ bash?: string; powershell?: string }> };
  };
  const entries = hooks.hooks.preToolUse ?? [];
  expect(entries.length, 'the preToolUse write-gate must be wired').toBeGreaterThan(0);
  for (const entry of entries) {
    for (const shell of ['bash', 'powershell'] as const) {
      expect(entry[shell], `preToolUse carries no ${shell} command`).toContain('hercules_gate.py');
    }
  }
});

describe.skipIf(which('copilot') === null)('live copilot binary', () => {
  it('the plugin installs into the real cli and is listed', (ctx) => {
    // Plugin management may require a login, so any error or timeout SKIPs; a success MUST list it.
    const { root, env } = scratchHome();
    workspace.track(root);

    const add = spawnSync('copilot', ['plugin', 'marketplace', 'add', repoRoot], {
      encoding: 'utf-8', timeout: TIMEOUT_MS, env,
    });
    if (add.error || add.status !== 0) {
      ctx.skip(`copilot marketplace add unavailable here: ${((add.stderr || add.stdout) ?? '').slice(0, 300)}`);
    }
    const inst = spawnSync('copilot', ['plugin', 'install', 'hercules@hercules'], {
      encoding: 'utf-8', timeout: TIMEOUT_MS, env,
    });
    if (inst.error || inst.status !== 0) {
      ctx.skip(`copilot plugin install unavailable here: ${((inst.stderr || inst.stdout) ?? '').slice(0, 300)}`);
    }
    const listed = spawnSync('copilot', ['plugin', 'list'], { encoding: 'utf-8', timeout: TIMEOUT_MS, env });
    if (listed.error) {
      ctx.skip(`copilot plugin management could not run here: ${listed.error.message}`);
    }
    expect(listed.status, `\`copilot plugin list\` failed: ${listed.stdout}\n${listed.stderr}`).toBe(0);
    expect(listed.stdout.toLowerCase(), `installed plugin not listed:\n${listed.stdout}`).toContain('hercules');
  }, TIMEOUT_MS * 3 + 5_000);
});
