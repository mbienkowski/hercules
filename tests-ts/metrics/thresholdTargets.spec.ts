import { globSync, writeFileSync } from 'node:fs';
import { basename, join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { loadThresholds, resolveTargets } from '../../scripts-ts/metrics/thresholdRunner.mjs';
import { repoRoot } from '../support/repo';
import { tmpWorkspace } from './support';

// Ported from tests/metrics/test_threshold_targets.py — resolveTargets: glob, comma-separated,
// dedup, plain-path.

describe('resolveTargets', () => {
  it('treats a comma-separated list of files as multiple targets', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a.md'), 'a');
    writeFileSync(join(root, 'b.md'), 'b');
    const names = new Set(resolveTargets(root, 'a.md,b.md').map((t) => basename(t)));
    expect(names).toEqual(new Set(['a.md', 'b.md']));
  });

  it('expands a wildcard pattern to every matching file', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'x.md'), 'x');
    writeFileSync(join(root, 'y.md'), 'y');
    expect(resolveTargets(root, '*.md')).toHaveLength(2);
  });

  it('yields no targets for a wildcard pattern that matches nothing', () => {
    const root = tmpWorkspace();
    expect(resolveTargets(root, 'nonexistent/*.md')).toEqual([]);
  });

  it('counts a file matched by two overlapping targets only once', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'z.md'), 'z');
    expect(resolveTargets(root, 'z.md,*.md')).toHaveLength(1);
  });

  it('a single-character placeholder (?) matches multiple files', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'ab.md'), 'x');
    writeFileSync(join(root, 'ac.md'), 'y');
    expect(resolveTargets(root, 'a?.md')).toHaveLength(2);
  });

  it('a bracketed character choice ([12]) matches multiple files', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a1.md'), 'x');
    writeFileSync(join(root, 'a2.md'), 'y');
    expect(resolveTargets(root, 'a[12].md')).toHaveLength(2);
  });

  it('an accidental double comma does not drop later files', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a.md'), 'x');
    writeFileSync(join(root, 'b.md'), 'y');
    // Double comma creates an empty pattern in the middle — must be skipped, not stop the scan.
    const names = new Set(resolveTargets(root, 'a.md,,b.md').map((t) => basename(t)));
    expect(names).toEqual(new Set(['a.md', 'b.md']));
  });

  it('a missing file named directly is still reported as a target', () => {
    const root = tmpWorkspace();
    expect(resolveTargets(root, 'nope.md')).toEqual([join(root, 'nope.md')]);
  });

  it('an ordinary filename is never mistaken for a wildcard pattern', () => {
    // Only *, ?, and [ mark a target as a wildcard — an ordinary letter like 'X' never does.
    const root = tmpWorkspace();
    expect(resolveTargets(root, 'Xnope.md')).toEqual([join(root, 'Xnope.md')]);
  });
});

describe('the real thresholds.json', () => {
  it('every shipped skill has a token-budget check configured', () => {
    const checks = loadThresholds(join(repoRoot, 'tests', 'testdata', 'thresholds.json'));
    const covered = new Set<string>();
    for (const check of checks) {
      if (check.metric === 'token_count') {
        for (const t of resolveTargets(repoRoot, check.target)) covered.add(t);
      }
    }
    const skills = globSync('dist/claude-code/skills/*/SKILL.md', { cwd: repoRoot }).map((rel) => join(repoRoot, rel));
    const missing = skills.filter((s) => !covered.has(s));
    expect(missing, `skills with no token-budget row: ${JSON.stringify(missing)}`).toEqual([]);
  });
});
