import { spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, expect, it, describe } from 'vitest';

import { buildDistribution } from '../../../internal/builder/build.mjs';
import { loadRecipe } from '../../../internal/builder/recipe-loader.mjs';
import { repoRoot } from '../../support/repo';
import { tempWorkspace } from '../../support/tempWorkspace';
import { which } from '../../support/which';
import { scratchHome } from '../smokeHarness';

// Codex smoke: what only the real `codex` binary can prove — a marketplace install into a scratch
// CODEX_HOME — plus the one clause of its listing no other host's marketplace schema has.

const RECIPE_FILE = 'src/targets/codex.json';
const TIMEOUT_MS = 60_000;
const scratchDirs = tempWorkspace();

/** Render the codex distribution into `out`, exactly as `make build` does. */
async function build(out: string): Promise<void> {
  await buildDistribution(loadRecipe(RECIPE_FILE, repoRoot), RECIPE_FILE, out, repoRoot);
}

afterEach(scratchDirs.cleanup);

it('the marketplace listing grants Codex the install policy it asks for', () => {
  // Codex alone carries an install POLICY in its marketplace schema: a bundle listed but not
  // `AVAILABLE`, or never asking to authenticate, is a plugin a user can see and cannot use.
  const listing = JSON.parse(readFileSync(join(repoRoot, '.agents', 'plugins', 'marketplace.json'), 'utf-8')) as {
    name: string;
    plugins: Array<{ name: string; policy?: unknown; category?: string }>;
  };
  // The marketplace id is half of the `hercules@mbienkowski` a user (and the live check below) types.
  expect(listing.name).toBe('mbienkowski');
  const hercules = listing.plugins.find((plugin) => plugin.name === 'hercules');
  expect(hercules?.policy).toEqual({ installation: 'AVAILABLE', authentication: 'ON_INSTALL' });
  expect(hercules?.category).toBe('Development');
});

describe.skipIf(which('codex') === null)('live Codex CLI', () => {
  it('installs the local marketplace bundle and lists Hercules', async () => {
    // Codex documents CODEX_HOME as its state root; a fresh one never touches a developer's plugins.
    const { root, env } = scratchHome((codexState) => ({ CODEX_HOME: codexState }));
    scratchDirs.track(root);
    const marketplacePath = join(root, '.agents', 'plugins', 'marketplace.json');
    mkdirSync(join(root, '.agents', 'plugins'), { recursive: true });
    writeFileSync(marketplacePath, readFileSync(join(repoRoot, '.agents', 'plugins', 'marketplace.json')));
    await build(join(root, 'dist', 'codex'));

    const addMarketplace = spawnSync('codex', ['plugin', 'marketplace', 'add', root], {
      cwd: root, env, encoding: 'utf-8', timeout: TIMEOUT_MS,
    });
    expect(addMarketplace.status, `${addMarketplace.stdout}\n${addMarketplace.stderr}`).toBe(0);

    const install = spawnSync('codex', ['plugin', 'add', 'hercules@mbienkowski'], {
      cwd: repoRoot, env, encoding: 'utf-8', timeout: TIMEOUT_MS,
    });
    expect(install.status, `${install.stdout}\n${install.stderr}`).toBe(0);

    const listed = spawnSync('codex', ['plugin', 'list', '--marketplace', 'mbienkowski', '--json'], {
      cwd: repoRoot, env, encoding: 'utf-8', timeout: TIMEOUT_MS,
    });
    expect(listed.status, `${listed.stdout}\n${listed.stderr}`).toBe(0);
    const plugins = JSON.parse(listed.stdout) as {
      installed: Array<{ pluginId: string; enabled: boolean; source: { source: string; path: string } }>;
    };
    const hercules = plugins.installed.find((plugin) => plugin.pluginId === 'hercules@mbienkowski');
    expect(hercules).toBeDefined();
    expect(hercules?.enabled).toBe(true);
    expect(hercules?.source.source).toBe('local');
    // macOS resolves the tmp directory through `/private`, while Node starts with `/var`.
    expect(hercules?.source.path).toMatch(/\/dist\/codex$/);
  }, (TIMEOUT_MS * 3) + 5_000);
});
