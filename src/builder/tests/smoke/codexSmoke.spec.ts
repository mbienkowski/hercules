import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, expect, it, describe } from 'vitest';

import { buildTarget } from '../../bin/cli.mjs';
import { srcStems } from '../../../commons/support/buildTree';
import { repoRoot } from '../../../commons/support/repo';
import { which } from '../../../commons/support/which';

// Codex smoke: structural checks always run; the live marketplace install runs when the Codex CLI
// is available. The app's plugin review/trust flow remains a manual release checklist item.

const SRC_CONTENT = join(repoRoot, 'src', 'content');
const TIMEOUT_MS = 60_000;
const scratchDirs: string[] = [];

afterEach(() => {
  while (scratchDirs.length > 0) rmSync(scratchDirs.pop() as string, { recursive: true, force: true });
});

function isFile(root: string, ...parts: string[]): boolean {
  try {
    return statSync(join(root, ...parts)).isFile();
  } catch {
    return false;
  }
}

it('the built plugin is a valid Codex skills-and-hooks bundle', () => {
  const out = join(repoRoot, 'dist', 'codex');
  const manifest = JSON.parse(readFileSync(join(out, '.codex-plugin', 'plugin.json'), 'utf-8')) as {
    name: string; skills: string; hooks: string;
  };
  expect(manifest.name).toBe('hercules');
  expect(manifest.skills).toBe('./skills/');
  expect(manifest.hooks).toBe('./hooks/hooks.json');
  expect(isFile(out, 'AGENTS.md')).toBe(true);
  expect(isFile(out, 'hooks', 'hooks.json')).toBe(true);
  expect(isFile(out, 'hooks', 'hercules_gate.py')).toBe(true);
  const hooks = JSON.parse(readFileSync(join(out, 'hooks', 'hooks.json'), 'utf-8')) as {
    hooks: { PreToolUse?: Array<{ matcher?: string }> };
  };
  expect(hooks.hooks.PreToolUse?.[0]?.matcher).toContain('apply_patch');
  expect(hooks.hooks.PreToolUse?.[0]?.matcher).toContain('Bash');
});

it('publishes the Codex bundle through the repository marketplace', () => {
  const marketplace = JSON.parse(readFileSync(join(repoRoot, '.agents', 'plugins', 'marketplace.json'), 'utf-8')) as {
    name: string;
    plugins: Array<{ name: string; source: { source: string; path: string } }>;
  };
  expect(marketplace.name).toBe('mbienkowski');
  expect(marketplace.plugins).toContainEqual({
    name: 'hercules',
    source: { source: 'local', path: './dist/codex' },
    description: 'Methodology & workflow system for software delivery with AI',
    policy: { installation: 'AVAILABLE', authentication: 'ON_INSTALL' },
    category: 'Development',
  });
});

it('ships every authored command and advisor as a named Codex skill', () => {
  const out = join(repoRoot, 'dist', 'codex');
  for (const name of srcStems(SRC_CONTENT, 'commands')) {
    const path = join(out, 'skills', `hercules-${name}`, 'SKILL.md');
    expect(isFile(out, 'skills', `hercules-${name}`, 'SKILL.md'), `missing command skill ${name}`).toBe(true);
    expect(readFileSync(path, 'utf-8')).toMatch(new RegExp(`^name: hercules-${name}$`, 'm'));
  }
  for (const name of srcStems(SRC_CONTENT, 'agents')) {
    expect(isFile(out, 'skills', `hercules-advisor-${name}`, 'SKILL.md'), `missing advisor skill ${name}`).toBe(true);
  }
  expect(readdirSync(join(out, 'skills')).length).toBeGreaterThan(15);
});

describe.skipIf(which('codex') === null)('live Codex CLI', () => {
  it('the real codex binary runs', () => {
    const res = spawnSync('codex', ['--version'], { encoding: 'utf-8', timeout: TIMEOUT_MS });
    expect(res.status, `${res.stdout}\n${res.stderr}`).toBe(0);
  }, TIMEOUT_MS + 5_000);

  it('installs the local marketplace bundle and lists Hercules', () => {
    const root = mkdtempSync(join(tmpdir(), 'hercules-codex-smoke-'));
    scratchDirs.push(root);
    // Codex documents CODEX_HOME as its state root. A fresh one makes this a real installation
    // test without seeing, trusting, or mutating a developer's configured marketplaces/plugins.
    const codexState = join(root, 'codex-state');
    mkdirSync(codexState);
    const env = { ...process.env, CODEX_HOME: codexState };
    const marketplacePath = join(root, '.agents', 'plugins', 'marketplace.json');
    mkdirSync(join(root, '.agents', 'plugins'), { recursive: true });
    writeFileSync(marketplacePath, readFileSync(join(repoRoot, '.agents', 'plugins', 'marketplace.json')));
    buildTarget('codex', join(root, 'dist', 'codex'));

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
