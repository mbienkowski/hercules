import { spawnSync } from 'node:child_process';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { tempWorkspace } from '../../support/tempWorkspace';
import { which } from '../../support/which';
import { scratchHome } from '../smokeHarness';

// Live Cursor CLI smoke. Cursor exposes no plugin-management command and no auth-free introspection,
// so all that is provable here needs the real binary: that it runs, and completes a headless prompt.

const TIMEOUT_MS = 60_000;

const workspace = tempWorkspace();
afterEach(workspace.cleanup, 30_000);

function isolatedHomeEnv(): NodeJS.ProcessEnv {
  const { root, env } = scratchHome((home) => ({
    XDG_CONFIG_HOME: join(home, '.config'),
    XDG_CACHE_HOME: join(home, '.cache'),
  }));
  workspace.track(root);
  return env;
}

describe.skipIf(which('cursor-agent') === null)('cursor live-CLI smoke', () => {
  it('the real cursor-agent binary runs', () => {
    // Must exit 0 from an isolated home — a stub on PATH would not, nor an install with no config root.
    const res = spawnSync('cursor-agent', ['--version'], {
      encoding: 'utf-8', timeout: TIMEOUT_MS, env: isolatedHomeEnv(),
    });
    expect(res.status, `cursor-agent --version failed: ${res.stdout}\n${res.stderr}`).toBe(0);
  }, TIMEOUT_MS + 5_000);

  it.skipIf(!process.env['CURSOR_API_KEY'])(
    'the real cursor-agent runs a headless prompt',
    () => {
      // With a key present, the real binary must complete one trivial headless `cursor-agent -p` prompt.
      const env = isolatedHomeEnv();
      const res = spawnSync(
        'cursor-agent',
        ['-p', 'Reply with the single word OK.', '--output-format', 'text'],
        { encoding: 'utf-8', timeout: TIMEOUT_MS, env },
      );
      expect(res.status, `headless cursor-agent run failed: ${res.stdout}\n${res.stderr}`).toBe(0);
    },
    TIMEOUT_MS + 5_000,
  );
});
