import { execFileSync } from 'node:child_process';
import { globSync } from 'node:fs';
import { basename } from 'node:path';

import { describe, expect, it } from 'vitest';

import { isFile } from '../../../commons/support/buildTree';
import { readRepoFile, readRepoJson, repoRoot } from '../../../commons/support/repo';

// Guards that keep the `plugin/` flat tree gone: no source file or tracked markdown may reference it. The cursor
// marketplace listing must also resolve to a real plugin manifest, and mutation testing must scan src/hooks/.

// Path literals that reach into a `plugin/` folder. Deliberately unmatched: `.claude-plugin/`,
// `plugin.json`, the `plugin_root` fixture name, and the prose "Claude Code plugin".
const RAW_PLUGIN = /parents\[\d+]\s*\/\s*["']plugin["']|\/\s*["']plugin["']\s*\//;
// Markdown reference to a bare `plugin/` path segment. The negative lookbehind exempts the legitimate
// `.claude-plugin/` and `opencode-plugin/`.
const RETIRED_PLUGIN_MD = /(?<![-.\w])plugin\//;
// Generated / not-authored-here markdown the guard must not police.
const MD_GUARD_SKIP = new Set(['CHANGELOG.md']);

describe('no source file hardcodes a path into the retired plugin/ folder', () => {
  it('scans every Python test and tooling file (other than conftest.py)', () => {
    // Scope: both Python test trees (commons/repo/, hooks/tests/) plus the release tooling.
    const files = [
      ...globSync('src/commons/repo/**/*.py', { cwd: repoRoot }),
      ...globSync('src/hooks/tests/**/*.py', { cwd: repoRoot }),
      ...globSync('src/release/**/*.py', { cwd: repoRoot }),
    ].filter((rel) => basename(rel) !== 'conftest.py');

    const offenders: string[] = [];
    for (const rel of files) {
      const lines = readRepoFile(rel).split('\n');
      lines.forEach((line, i) => {
        if (RAW_PLUGIN.test(line)) offenders.push(`${rel}:${i + 1}`);
      });
    }
    expect(offenders, `raw plugin/ path literals (retired tree): ${offenders.join(', ')}`).toEqual([]);
  });
});

describe('project documentation never points readers to the retired plugin/ folder', () => {
  it('scans every git-tracked markdown file (excluding generated files like the changelog)', () => {
    // git-tracked only (so the gitignored root CLAUDE.md is never swept); .claude-plugin/ is
    // excluded by the pattern's lookbehind.
    const tracked = execFileSync('git', ['ls-files', '*.md'], { cwd: repoRoot, encoding: 'utf-8' })
      .split('\n')
      .filter((rel) => rel.length > 0);

    const offenders: string[] = [];
    for (const rel of tracked) {
      if (MD_GUARD_SKIP.has(basename(rel))) continue;
      const lines = readRepoFile(rel).split('\n');
      lines.forEach((line, i) => {
        if (RETIRED_PLUGIN_MD.test(line)) {
          offenders.push(`${rel}:${i + 1}: ${line.trim().slice(0, 100)}`);
        }
      });
    }
    expect(offenders, `retired plugin/ tree referenced in tracked markdown:\n${offenders.join('\n')}`).toEqual([]);
  });
});

it('the cursor marketplace listing points to a plugin that actually exists', () => {
  // The same guarantee the claude-code listing carries (asserted in pluginIntegrity.spec.ts), so a
  // broken/stale cursor source can't ship silently.
  interface CursorMarketplace {
    name?: string;
    owner?: { name?: string };
    plugins?: Array<{ name?: string; source?: string }>;
  }
  const mk = readRepoJson<CursorMarketplace>('.cursor-plugin', 'marketplace.json');
  expect(mk.name, 'Cursor marketplace needs a name').toBeTruthy();
  expect(mk.owner?.name, 'Cursor marketplace needs an owner name').toBeTruthy();

  const entry = (mk.plugins ?? []).find((p) => p.name === 'hercules');
  expect(entry, "'.cursor-plugin/marketplace.json' does not list a plugin named 'hercules'").toBeDefined();
  const source = entry?.source ?? '';
  expect(
    isFile(repoRoot, source, '.cursor-plugin', 'plugin.json'),
    `cursor marketplace source '${source}' must resolve to a .cursor-plugin/plugin.json`,
  ).toBe(true);
});

it('mutation testing targets the current hooks location, not the retired one', () => {
  // Mutation testing must scan the hooks code where it actually lives; pointed anywhere else it
  // exercises the wrong files and gives false confidence in how well the hooks are covered.
  const pyproject = readRepoFile('pyproject.toml');
  expect(pyproject).toContain('paths_to_mutate = "src/hooks/"');
  expect(pyproject).not.toContain('plugin/hooks/');
});
