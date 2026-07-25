import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { buildTarget } from '../bin/cli.mjs';
import { which } from '../../tests/support/which';

// Ported from tests/build/test_opencode_smoke.py (Spec 06) — a live OpenCode CLI smoke check:
// does the built plugin actually load in the real tool, not just in a Node `require()` probe?
//
// `test_opencode_entrypoint.py` proves the generated plugin.js is internally self-consistent
// (config() populates the right agent/command/skill counts) by requiring it directly in Node.
// That is NOT the same as proving OpenCode's own plugin loader accepts the file. It didn't,
// twice over: manually installing the real `opencode-ai` CLI and pointing it at this repo's
// built plugin.js reproduced two real, reproducible failures the Node-based probe could not see
// -- https://github.com/mbienkowski/hercules/issues/15 has the full root-cause diagnosis for
// both:
//
// 1. "Plugin export is not a function" -- Node's CJS/ESM interop for a bare
//    `module.exports = <function>` differs from Bun's (which is what the real `opencode` binary
//    is compiled with): Bun spreads the function's own `length`/`name` properties into the
//    imported module's namespace, and the loader throws on the first one that isn't a valid
//    plugin export.
// 2. Once fixed to export `{ server: fn }` instead, a second, previously-unknown failure
//    surfaced only by running the real binary: "must export id" -- a path-installed plugin also
//    requires a top-level `id` field that the Node probe never exercised.
//
// Both are now fixed in `ecosystems/opencode.template.plugin.js` (exports
// `{ id: "hercules", server: fn }`), verified against the real installed `opencode` binary
// before this test's `xfail` marker was removed.

// 60s (matching the cursor/gemini/copilot smoke legs): a cold `opencode agent list` warms the Bun
// runtime and loads the plugin on first invocation, which can exceed a tight 30s on a loaded CI
// runner (a real timeout there was a flake, not a plugin defect — the built bytes are
// drift-gate-pinned).
const TIMEOUT_MS = 60_000;

const dirs: string[] = [];
afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
}, 30_000);

/**
 * A scratch OpenCode project with a freshly-built plugin.js placed exactly where OpenCode's own
 * load-order convention expects it -- the project-level `plugins` folder under the hidden
 * OpenCode config directory; OpenCode has no flag to load an arbitrary path, unlike Claude Code
 * -- and an isolated config/cache home so this can never touch a real developer's OpenCode setup.
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
    // Running the actual `opencode` binary against a project with this plugin installed must
    // successfully list hercules among the available agents -- proving the plugin loads the way
    // a real user's OpenCode session would load it, not just the way a Node script loading its
    // JS module directly would.
    const { project, env } = opencodeProjectWithPluginInstalled();
    const res = spawnSync('opencode', ['agent', 'list'], {
      cwd: project, env, timeout: TIMEOUT_MS, encoding: 'utf-8',
    });
    expect(res.status, `stdout=${res.stdout}\nstderr=${res.stderr}`).toBe(0);
    // A loose "hercules" substring check would trivially pass on skill-path noise alone (every
    // agent's permission dump references the shipped `hercules-reference` skill path); only a
    // line naming the agent itself proves it actually registered.
    const agentLines = res.stdout
      .split('\n')
      .map((ln) => ln.trim())
      .filter((ln) => ln.toLowerCase().startsWith('hercules '));
    expect(agentLines.length, `no 'hercules' agent line in \`opencode agent list\` output:\n${res.stdout}`).toBeGreaterThan(0);
  }, TIMEOUT_MS + 5_000);
});
