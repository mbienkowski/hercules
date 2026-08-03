import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { describe, expect, it } from 'vitest';

import { listRecipeNames } from '../../internal/builder/recipe-loader.mjs';
import { pathsUnder } from '../support/buildTree';
import { repoRoot } from '../support/repo';

/**
 * What an eighth ecosystem costs in test code: every line under tests/dist/<ecosystem>/ plus every
 * fenced per-ecosystem block, measured against a ceiling.
 */

const PER_ECOSYSTEM_TREE = join(repoRoot, 'tests', 'dist');

/**
 * Fences around a block carrying one entry per ecosystem, so it is counted without this file knowing
 * where any of them live. Plain comments, so the same pair works in TypeScript and in Python.
 */
const BLOCK_START = 'ecosystem-tax:start';
const BLOCK_END = 'ecosystem-tax:end';

/** Lines in a file, not counting the empty string a trailing newline leaves behind. */
function lineCount(file: string): number {
  const lines = readFileSync(file, 'utf-8').split('\n');
  if (lines[lines.length - 1] === '') lines.pop();
  return lines.length;
}

/** Every test source in the repository, both runtimes, except this one — it carries both fences and would count itself. */
function testSources(): string[] {
  const self = join(repoRoot, 'tests', 'budgets', 'ecosystemTax.spec.ts');
  return pathsUnder(join(repoRoot, 'tests'), {
    extensions: ['.ts', '.mts', '.py'],
    skipDirs: ['__pycache__'],
  }).filter((file) => file !== self);
}

/** The directories directly under tests/dist/ — one per ecosystem that carries host-specific tests. */
function ecosystemDirectories(): string[] {
  return readdirSync(PER_ECOSYSTEM_TREE, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

/** Lines of test code living under tests/dist/<ecosystem>/, keyed by ecosystem. */
function perEcosystemLines(): Map<string, number> {
  const counted = new Map<string, number>();
  for (const name of ecosystemDirectories()) {
    const root = join(PER_ECOSYSTEM_TREE, name);
    let lines = 0;
    for (const file of pathsUnder(root, { extensions: ['.ts', '.mts', '.py'] })) {
      lines += lineCount(file);
    }
    counted.set(name, lines);
  }
  return counted;
}

/** Lines inside every fenced per-ecosystem block, keyed by the file that carries it. */
function fencedBlockLines(): Map<string, number> {
  const counted = new Map<string, number>();
  for (const file of testSources()) {
    const relativePath = relative(repoRoot, file).split(sep).join('/');
    const lines = readFileSync(file, 'utf-8').split('\n');
    let openedAt: number | null = null;
    let total = 0;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i] as string;
      if (line.includes(BLOCK_START)) {
        expect(openedAt, `${relativePath}:${i + 1}: a second ${BLOCK_START} before the first was closed`).toBeNull();
        openedAt = i;
      } else if (line.includes(BLOCK_END)) {
        expect(openedAt, `${relativePath}:${i + 1}: ${BLOCK_END} with no ${BLOCK_START} above it`).not.toBeNull();
        total += i - (openedAt as number) + 1;
        openedAt = null;
      }
    }
    expect(openedAt, `${relativePath}: ${BLOCK_START} was never closed`).toBeNull();
    if (total > 0) counted.set(relativePath, total);
  }
  return counted;
}

/** The ceiling, in lines of test code scaling with the ecosystem count: what the tree measured, never a chosen figure. */
const CEILING = 1069;

/** How few fenced blocks would mean somebody deleted the fences rather than the duplication. */
const MINIMUM_FENCED_BLOCKS = 3;

describe('what a new ecosystem costs the test suite', () => {
  it('there is a per-ecosystem surface to measure at all', () => {
    // Guards the guard: with nothing found, the total is zero and the budget reads green vacuously.
    expect(ecosystemDirectories().length, 'no per-ecosystem test directories found').toBeGreaterThan(1);
    expect(
      fencedBlockLines().size,
      `fewer than ${MINIMUM_FENCED_BLOCKS} fenced per-ecosystem blocks found — were the fences removed?`,
    ).toBeGreaterThanOrEqual(MINIMUM_FENCED_BLOCKS);
  });

  it('every per-ecosystem test directory belongs to a registered target', () => {
    // A directory for an ecosystem nobody builds is test code with no product behind it, eating budget.
    const registered = new Set(listRecipeNames());
    const orphans = ecosystemDirectories().filter((name) => !registered.has(name));
    expect(orphans, 'these tests/dist/ directories name no registered target').toEqual([]);
  });

  it('the per-ecosystem test surface stays inside its ceiling', () => {
    const perEcosystem = perEcosystemLines();
    const blocks = fencedBlockLines();
    const total = [...perEcosystem.values(), ...blocks.values()].reduce((a, b) => a + b, 0);

    const breakdown = [
      ...[...perEcosystem].map(([name, n]) => `  tests/dist/${name}/ ${n}`),
      ...[...blocks].map(([file, n]) => `  ${file} ${n}`),
    ].join('\n');

    expect(
      total,
      `test code scaling with the ecosystem count is ${total} lines, over its ${CEILING} ceiling:\n${breakdown}`,
    ).toBeLessThanOrEqual(CEILING);
  });
});
