import { execFileSync } from 'node:child_process';
import { existsSync, globSync } from 'node:fs';
import { basename, join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { readRepoFile, repoRoot } from '../support/repo';

// Guards that keep the `plugin/` flat tree gone: no source file or tracked markdown may reference
// it, and mutation testing must scan src/scripts/hooks/ where the shipped Python really lives.

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
    // Scope: every Python file that is not shipped — the test trees and the release tooling.
    const files = [
      ...globSync('tests/**/*.py', { cwd: repoRoot }),
      ...globSync('internal/release/**/*.py', { cwd: repoRoot }),
    ].filter((relativePath) => basename(relativePath) !== 'conftest.py');

    const offenders: string[] = [];
    for (const relativePath of files) {
      const lines = readRepoFile(relativePath).split('\n');
      lines.forEach((line, i) => {
        if (RAW_PLUGIN.test(line)) offenders.push(`${relativePath}:${i + 1}`);
      });
    }
    expect(offenders, `raw plugin/ path literals (retired tree): ${offenders.join(', ')}`).toEqual([]);
  });
});

describe('project documentation never points readers to the retired plugin/ folder', () => {
  it('scans every git-tracked markdown file (excluding generated files like the changelog)', () => {
    // git-tracked only, so the gitignored root CLAUDE.md is never swept. A tracked path whose file is
    // gone — a deletion not yet staged — is documentation nobody can read, so it is skipped.
    const tracked = execFileSync('git', ['ls-files', '*.md'], { cwd: repoRoot, encoding: 'utf-8' })
      .split('\n')
      .filter((relativePath) => relativePath.length > 0 && existsSync(join(repoRoot, relativePath)));

    const offenders: string[] = [];
    for (const relativePath of tracked) {
      if (MD_GUARD_SKIP.has(basename(relativePath))) continue;
      const lines = readRepoFile(relativePath).split('\n');
      lines.forEach((line, i) => {
        if (RETIRED_PLUGIN_MD.test(line)) {
          offenders.push(`${relativePath}:${i + 1}: ${line.trim().slice(0, 100)}`);
        }
      });
    }
    expect(offenders, `retired plugin/ tree referenced in tracked markdown:\n${offenders.join('\n')}`).toEqual([]);
  });
});

it('mutation testing targets every shipped-Python island, not the retired location', () => {
  // Mutation testing must scan the shipped code where it lives, or it exercises the wrong files and
  // gives false confidence. Both islands count: src/scripts/hooks/ and src/scripts/tools/.
  const pyproject = readRepoFile('pyproject.toml');
  expect(pyproject).toContain('paths_to_mutate = "src/scripts/hooks/,src/scripts/tools/"');
  expect(pyproject).not.toContain('plugin/hooks/');
});
