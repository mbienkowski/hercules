import { spawnSync } from 'node:child_process';
import { mkdirSync, symlinkSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { buildDistribution } from '../../../internal/builder/build.mjs';
import { loadRecipe } from '../../../internal/builder/recipe-loader.mjs';
import { repoRoot } from '../../support/repo';
import { tempWorkspace } from '../../support/tempWorkspace';
import { which } from '../../support/which';
import { scratchHome } from '../smokeHarness';

// Live OpenCode CLI smoke: the built plugin loads in the real tool, which a Node `require()` probe
// cannot establish — the binary is Bun-compiled, with CJS (CommonJS)/ESM (ES module) interop of its own.

// A cold `opencode agent list` warms the Bun runtime and loads the plugin on first invocation.
const TIMEOUT_MS = 60_000;
const RECIPE_FILE = 'src/targets/opencode.json';

const workspace = tempWorkspace();
afterEach(workspace.cleanup, 30_000);

/**
 * A scratch OpenCode project with a freshly-built plugin.js under the project-level `plugins` folder
 * its load order expects, an isolated config/cache home, and the models.dev catalog fetch disabled.
 */
async function opencodeProjectWithPluginInstalled(): Promise<{ project: string; env: NodeJS.ProcessEnv }> {
  const { root, env } = scratchHome((home) => ({
    XDG_CONFIG_HOME: join(home, '.config'),
    XDG_CACHE_HOME: join(home, '.cache'),
    OPENCODE_DISABLE_MODELS_FETCH: 'true',
    OPENCODE_DISABLE_AUTOUPDATE: 'true',
    OPENCODE_DISABLE_DEFAULT_PLUGINS: 'true',
    OPENCODE_DISABLE_LSP_DOWNLOAD: 'true',
  }));
  workspace.track(root);

  const out = join(root, 'opencode-dist');
  await buildDistribution(loadRecipe(RECIPE_FILE, repoRoot), RECIPE_FILE, out, repoRoot);

  const project = join(root, 'project');
  const pluginsDir = join(project, '.opencode', 'plugins');
  mkdirSync(pluginsDir, { recursive: true });
  symlinkSync(join(out, 'plugin.js'), join(pluginsDir, 'hercules.js'));

  return { project, env };
}

describe.skipIf(which('opencode') === null)('opencode live-CLI smoke', () => {
  it('the real opencode cli loads the plugin and lists its agents', async () => {
    const { project, env } = await opencodeProjectWithPluginInstalled();
    const res = spawnSync('opencode', ['agent', 'list'], {
      cwd: project, env, timeout: TIMEOUT_MS, encoding: 'utf-8',
    });
    expect(res.status, `stdout=${res.stdout}\nstderr=${res.stderr}`).toBe(0);
    // A loose "hercules" substring passes on skill-path noise; only an agent line proves registration.
    const agentLines = res.stdout
      .split('\n')
      .map((ln) => ln.trim())
      .filter((ln) => ln.toLowerCase().startsWith('hercules '));
    expect(agentLines.length, `no 'hercules' agent line in \`opencode agent list\` output:\n${res.stdout}`).toBeGreaterThan(0);
  }, TIMEOUT_MS + 5_000);
});
