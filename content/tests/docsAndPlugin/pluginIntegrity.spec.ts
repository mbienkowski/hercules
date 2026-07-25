import { globSync } from 'node:fs';
import { join } from 'node:path';

import { expect, it } from 'vitest';

import { loadThresholds, runThresholdChecks } from '../../../metrics/thresholdRunner.mjs';
import { isFile } from '../../../tests/support/buildTree';
import { readRepoFile, readRepoJson, repoRoot } from '../../../tests/support/repo';
import type { PluginManifest } from './support';

// Ported from tests/plugin/test_plugin_integrity.py — plugin file hygiene and shared settings
// correctness: token-budget gate, lowercase filenames, plugin.json required fields, marketplace
// resolution, README permissions-section checks, agent-name casing.

const CONTENT_DIRS = ['dist/claude-code/commands', 'dist/claude-code/agents', 'dist/claude-code/skills'];
const LOWERCASE_EXCEPT = new Set(['SKILL.md']);
const PLUGIN_JSON = ['dist', 'claude-code', '.claude-plugin', 'plugin.json'];

function walkMarkdown(): string[] {
  return CONTENT_DIRS.flatMap((dir) => globSync(`${dir}/**/*.md`, { cwd: repoRoot }));
}

interface MarketplaceEntry {
  name?: string;
  source?: string;
}
interface Marketplace {
  name?: string;
  plugins?: MarketplaceEntry[];
}

it('shipped content never exceeds its size budget', () => {
  const thresholdFile = join(repoRoot, 'metrics', 'tests', 'testdata', 'thresholds.json');
  const checks = loadThresholds(thresholdFile);
  const results = runThresholdChecks(repoRoot, checks);

  const failures = results.filter((r) => !r.passed && r.severity === 'gate');
  expect(failures, `Token budget gate failures:\n${failures.map((r) => `  ${r.message}`).join('\n')}`).toEqual([]);
  // warn_at exists to give a pre-limit signal — surface it, or it is a dead feature.
  for (const r of results) if (r.nearWarn) console.warn(`approaching budget limit: ${r.message}`);
});

it('shipped file names are always lowercase', () => {
  const violations = walkMarkdown().filter((rel) => {
    const name = rel.split('/').pop() as string;
    return !LOWERCASE_EXCEPT.has(name) && name !== name.toLowerCase();
  });
  expect(violations, `Uppercase filenames found (will fail to load on Linux): ${violations}`).toEqual([]);
});

it('the plugin listing declares its name, version, and author', () => {
  const fields = readRepoJson<PluginManifest>(...PLUGIN_JSON);
  for (const required of ['name', 'version', 'description', 'author'] as const) {
    expect(fields[required], `plugin.json missing required field: ${required}`).toBeTruthy();
  }
});

it('the marketplace listing can actually find and install hercules', () => {
  const data = readRepoJson<Marketplace>('.claude-plugin', 'marketplace.json');
  expect(data.name, "marketplace.json missing 'name'").toBeTruthy();
  const entry = (data.plugins ?? []).find((p) => p.name === 'hercules');
  expect(entry, "marketplace.json does not list a plugin named 'hercules'").toBeDefined();
  const source = entry?.source ?? '';
  expect(source, "hercules plugin entry missing 'source'").toBeTruthy();
  expect(
    isFile(repoRoot, source, '.claude-plugin', 'plugin.json'),
    `marketplace source '${source}' must resolve to a dir containing .claude-plugin/plugin.json`,
  ).toBe(true);
});

it('the shipped plugin never requires an experimental feature flag', () => {
  const flag = 'CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS';
  const files = globSync('dist/claude-code/**/*.{md,json}', { cwd: repoRoot });
  const offenders = files.filter((rel) => readRepoFile(rel).includes(flag));
  expect(offenders, `shipped plugin artifacts must not reference ${flag}: ${offenders}`).toEqual([]);
});

it('plugin docs never claim to make their own network calls', () => {
  for (const rel of globSync('dist/claude-code/**/*.md', { cwd: repoRoot })) {
    const content = readRepoFile(rel).toLowerCase();
    expect(content, `${rel} claims direct API calls`).not.toContain('direct api call');
    expect(content, `${rel} claims external network channel`).not.toContain('external network channel');
  }
});

it('documented permissions promise only one write location and no data collection', () => {
  const readme = readRepoFile('README.md');
  const claudeMd = readRepoFile('dist/claude-code/CLAUDE.md').toLowerCase();
  expect(readme.toLowerCase(), 'README must document the ~/.hercules/ write location').toContain('~/.hercules/');
  expect(claudeMd, 'dist/claude-code/CLAUDE.md must reference ~/.hercules/').toContain('~/.hercules/');

  const match = readme.match(/## Plugin permissions\n([\s\S]*?)(?=\n## |$)/);
  expect(match, "README must contain a '## Plugin permissions' section").toBeTruthy();
  const perms = ((match as RegExpMatchArray)[1] as string).toLowerCase();

  const homeWrites = perms.match(/~\/\.[a-z][a-z0-9_-]+\//g) ?? [];
  expect(homeWrites.every((p) => p === '~/.hercules/'), 'unexpected home-dir locations in Plugin permissions').toBe(
    true,
  );
  expect(perms, 'Plugin permissions must state no credentials are stored').toContain('no credentials');
  expect(
    perms.includes('no direct api calls') || perms.includes('no separate network channel'),
    'Plugin permissions must state no direct API calls or separate network channel',
  ).toBe(true);
});

it('every agent frontmatter name is lowercase', () => {
  const nameRe = /^name:\s*(\S+)\s*$/m;
  const violations: string[] = [];
  for (const rel of globSync('dist/claude-code/agents/*.md', { cwd: repoRoot }).sort()) {
    const name = readRepoFile(rel).match(nameRe)?.[1];
    if (name && name !== name.toLowerCase()) violations.push(`${rel.split('/').pop()}: name=${JSON.stringify(name)}`);
  }
  expect(violations, `Agent frontmatter name fields with uppercase: ${violations}`).toEqual([]);
});
