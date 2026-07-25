import { spawnSync } from 'node:child_process';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { srcStems } from '../../tests/support/buildTree';
import { repoRoot } from '../../tests/support/repo';
import { which } from '../../tests/support/which';

// Ported from tests/build/test_grok_build_smoke.py — Grok Build smoke: the built plugin is
// structurally installable (checked against the committed dist/grok-build); live `grok` CLI
// check when present.
//
// The structural checks never skip (so the CI leg produces "N passed" without secrets); the
// live-CLI check skips cleanly when `grok` is absent, mirroring the Cursor smoke pattern.

const SRC_CONTENT = join(repoRoot, 'src', 'content');
const DIST = join(repoRoot, 'dist', 'grok-build');

function srcSkills(): string[] {
  return readdirSync(join(SRC_CONTENT, 'skills'), { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .sort();
}

function isFile(...segments: string[]): boolean {
  try {
    return statSync(join(...segments)).isFile();
  } catch {
    return false;
  }
}

it('marketplace descriptor points at the built plugin', () => {
  const mp = JSON.parse(
    readFileSync(join(repoRoot, '.grok-plugin', 'marketplace.json'), 'utf-8'),
  ) as { plugins: Array<{ source: string }> };
  expect(mp.plugins[0]?.source).toBe('./dist/grok-build');
  expect(isFile(DIST, '.grok-plugin', 'plugin.json')).toBe(true);
});

it('built plugin ships the core components', () => {
  const rels = [
    ['.grok-plugin', 'plugin.json'],
    ['CLAUDE.md'],
    ['hooks', 'hooks.json'],
    ['hooks', 'frozen_tests.py'],
    ['hooks', 'hercules_state.py'],
    ['agents', 'hercules.md'],
    ['commands', 'build.md'],
    ['settings.json'],
  ];
  for (const rel of rels) {
    expect(isFile(DIST, ...rel), `grok-build plugin missing ${rel.join('/')}`).toBe(true);
  }
});

it('ships the full component inventory', () => {
  // The installed plugin must carry the WHOLE inventory — all 5 commands, every advisor agent,
  // and every skill — so nothing silently fails to load. Names derive from content (the
  // single source of truth), so a dropped or renamed component fails here rather than shipping a
  // half-loaded plugin.
  for (const name of srcStems(SRC_CONTENT, 'commands')) {
    expect(isFile(DIST, 'commands', `${name}.md`), `grok-build missing command ${name}`).toBe(true);
  }
  for (const name of srcStems(SRC_CONTENT, 'agents')) {
    expect(isFile(DIST, 'agents', `${name}.md`), `grok-build missing agent ${name}`).toBe(true);
  }
  for (const skill of srcSkills()) {
    expect(isFile(DIST, 'skills', skill, 'SKILL.md'), `grok-build missing skill ${skill}`).toBe(true);
  }
  expect(isFile(DIST, 'CLAUDE.md'), 'grok-build persona instructions (CLAUDE.md) must ship').toBe(true);
});

describe.skipIf(which('grok') === null)('live grok binary', () => {
  it('grok cli is available', () => {
    const res = spawnSync('grok', ['--version'], { encoding: 'utf-8' });
    expect(res.status, 'grok --version must succeed once the CLI is installed').toBe(0);
  }, 30_000);
});
