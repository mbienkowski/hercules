import { spawnSync } from 'node:child_process';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { expect, it, describe } from 'vitest';

import { srcStems } from '../../../commons/support/buildTree';
import { repoRoot } from '../../../commons/support/repo';
import { which } from '../../../commons/support/which';

// Codex smoke: structural checks always run; the live version check runs when the Codex CLI is
// available. The app's plugin review/trust flow remains a manual release checklist item.

const SRC_CONTENT = join(repoRoot, 'src', 'content');

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
    const res = spawnSync('codex', ['--version'], { encoding: 'utf-8', timeout: 60_000 });
    expect(res.status, `${res.stdout}\n${res.stderr}`).toBe(0);
  }, 65_000);
});
