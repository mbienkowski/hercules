import { execFileSync } from 'node:child_process';
import { globSync } from 'node:fs';
import { basename } from 'node:path';

import { describe, expect, it } from 'vitest';

import { isFile } from '../support/buildTree';
import { readRepoFile, readRepoJson, repoRoot } from '../support/repo';

// Ported from tests/build/test_cutover.py — spec-04 cutover guards: no raw `plugin/` path literals
// pointing at the retired flat tree, tracked markdown never sends readers there either, the shared
// test setup resolves to the shipped dist/claude-code tree, both marketplaces (claude-code AND
// cursor) resolve to a real plugin manifest, and mutation testing targets the current hooks
// location. This file does not import scripts.build itself (verified against the Python original),
// so it is ported for completeness/parity rather than to unblock scripts/build/'s deletion.
//
// The claude-code marketplace-resolves case is already covered, with the same assertion, by
// docsAndPlugin/pluginIntegrity.spec.ts's "the marketplace listing can actually find and install
// hercules" — not duplicated here; only the cursor-specific case (genuinely uncovered — the
// existing ci/validatePackage.spec.ts and docsAndPlugin/pluginIntegrity.spec.ts checks stop at "the
// manifest lists hercules" and never resolve cursor's `source` to a real `.cursor-plugin/plugin.json`)
// is added below.

// Path-literal patterns that reach the retired plugin/ tree (NOT `.claude-plugin/`, `plugin.json`,
// the `plugin_root` fixture name, or the prose "Claude Code plugin").
const RAW_PLUGIN = /parents\[\d+]\s*\/\s*["']plugin["']|\/\s*["']plugin["']\s*\//;
// Markdown reference to the retired `plugin/` tree. The negative lookbehind excludes the legitimate
// `.claude-plugin/` (and `opencode-plugin/`) — a bare `plugin/` segment is the retired path.
const RETIRED_PLUGIN_MD = /(?<![-.\w])plugin\//;
// Generated / not-authored-here markdown the guard must not police.
const MD_GUARD_SKIP = new Set(['CHANGELOG.md']);

describe('no source file hardcodes a path into the retired plugin/ folder', () => {
  it('scans every tests/ and scripts/ Python file (other than conftest.py)', () => {
    const files = [
      ...globSync('tests/**/*.py', { cwd: repoRoot }),
      ...globSync('scripts/**/*.py', { cwd: repoRoot }),
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

it('the shared test setup points at the shipped claude-code tree', () => {
  // Positive companion to the guard above: the shared pytest fixture must point at the shipped
  // dist/claude-code output rather than some stale or alternate location, since every test relying
  // on that fixture depends on it finding the actual shipped files.
  const src = readRepoFile('tests', 'conftest.py');
  expect(src).toContain('repo_root / "dist" / "claude-code"');
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
  // The mutation-testing configuration must scan the hooks code at its current, migrated location
  // and must not still reference an old, retired location. Otherwise mutation testing would
  // silently exercise the wrong (or no longer existing) files, giving false confidence in how well
  // the real hooks code is covered.
  const pyproject = readRepoFile('pyproject.toml');
  expect(pyproject).toContain('src/hooks/');
  expect(pyproject).not.toContain('src/targets/');
  expect(pyproject).not.toContain('plugin/hooks/');
});
