import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { buildTarget } from '../../bin/cli.mjs';
import { which } from '../../../commons/support/which';

// Live OpenCode CLI smoke check: the built plugin loads in the real tool, which a Node `require()`
// probe cannot establish. The real `opencode` binary is compiled with Bun, whose CJS (CommonJS)/ESM
// (ES module) interop differs from Node's, and a path-installed plugin must also carry a top-level
// `id` — hence `ecosystems/opencode.template.plugin.js` exporting `{ id: "hercules", server: fn }`.

// 60s, matching the other smoke legs: a cold `opencode agent list` warms the Bun runtime and loads
// the plugin on first invocation, which can exceed a tight 30s on a loaded CI runner.
const TIMEOUT_MS = 60_000;

const dirs: string[] = [];
afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
}, 30_000);

/**
 * A scratch OpenCode project with a freshly-built plugin.js in the project-level `plugins` folder
 * OpenCode's load-order convention expects (it has no flag to load an arbitrary path), plus an
 * isolated config/cache home so this can never touch a real developer's OpenCode setup.
 */
function opencodeProjectWithPluginInstalled(): { project: string; env: NodeJS.ProcessEnv } {
  const root = mkdtempSync(join(tmpdir(), 'hercules-opencode-smoke-'));
  dirs.push(root);

  const out = join(root, 'opencode-dist');
  buildTarget('opencode', out);

  const project = join(root, 'project');
  const pluginsDir = join(project, '.opencode', 'plugins');
  mkdirSync(pluginsDir, { recursive: true });
  symlinkSync(join(out, 'plugin.js'), join(pluginsDir, 'hercules.js'));

  const home = join(root, 'home');
  mkdirSync(home);
  const env = {
    ...process.env,
    HOME: home,
    XDG_CONFIG_HOME: join(home, '.config'),
    XDG_CACHE_HOME: join(home, '.cache'),
  };
  return { project, env };
}

describe.skipIf(which('opencode') === null)('opencode live-CLI smoke', () => {
  it('the real opencode cli loads the plugin and lists its agents', () => {
    // The real `opencode` binary must list hercules among its agents — proving the plugin loads
    // the way a user's session would, not merely the way a direct Node import would.
    const { project, env } = opencodeProjectWithPluginInstalled();
    const res = spawnSync('opencode', ['agent', 'list'], {
      cwd: project, env, timeout: TIMEOUT_MS, encoding: 'utf-8',
    });
    expect(res.status, `stdout=${res.stdout}\nstderr=${res.stderr}`).toBe(0);
    // A loose "hercules" substring would pass on skill-path noise alone (every agent's permission
    // dump names the `hercules-reference` skill path); only an agent line proves registration.
    const agentLines = res.stdout
      .split('\n')
      .map((ln) => ln.trim())
      .filter((ln) => ln.toLowerCase().startsWith('hercules '));
    expect(agentLines.length, `no 'hercules' agent line in \`opencode agent list\` output:\n${res.stdout}`).toBeGreaterThan(0);
  }, TIMEOUT_MS + 5_000);
});
