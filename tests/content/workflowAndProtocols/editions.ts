import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { expect } from 'vitest';

import { readFile } from '../commands/support';
import { pathsUnder } from '../../support/buildTree';
import { repoRoot } from '../../support/repo';

/**
 * The seven shipped editions and where each keeps the artifacts these guards read. Each edition names
 * and wraps the same artifact differently, and an unresolved path fails: a sweep opening nothing passes.
 */

export const TREES = ['claude-code', 'opencode', 'cursor', 'copilot-cli', 'gemini-cli', 'grok-build', 'codex'] as const;

export type Tree = (typeof TREES)[number];

/**
 * The editions actually present under `dist/`. `TREES` is a hand-written literal that can lose an
 * entry and shrink the run instead of failing it, so `editions.spec.ts` reconciles the two.
 */
export function editionsOnDisk(): string[] {
  return readdirSync(join(repoRoot, 'dist'), { withFileTypes: true })
    .filter((e) => e.isDirectory()).map((e) => e.name).sort();
}

/** The always-loaded persona, named differently per host. */
export const PERSONA_PER_TREE: Record<Tree, string> = {
  'claude-code': 'CLAUDE.md',
  'grok-build': 'CLAUDE.md',
  opencode: 'instructions.md',
  cursor: 'rules/hercules-persona.mdc',
  'copilot-cli': 'AGENTS.md',
  'gemini-cli': 'GEMINI.md',
  codex: 'AGENTS.md',
};

/** Commands, whose extension differs per host (Copilot prompts, Gemini TOML). */
export function commandPath(tree: Tree, name: string): string {
  if (tree === 'copilot-cli') return `commands/${name}.prompt.md`;
  if (tree === 'gemini-cli') return `commands/${name}.toml`;
  if (tree === 'codex') return `skills/hercules-${name}/SKILL.md`;
  return `commands/${name}.md`;
}

export const RUBRIC = 'protocols/debate-consensus-protocol.md';
export const REFERENCE = 'skills/hercules-reference/SKILL.md';

/**
 * Read a file from an edition, failing loudly when the edition does not carry it. Returning `''` for
 * a missing path is how a per-edition guard silently degrades into a single-edition one.
 */
export function distFile(tree: Tree, relativePath: string): string {
  const abs = `${repoRoot}/dist/${tree}/${relativePath}`;
  expect(existsSync(abs), `dist/${tree}/${relativePath} does not exist — this edition would be skipped `
    + 'silently, and a guard that opens nothing reports success').toBe(true);
  return readFile(`dist/${tree}/${relativePath}`);
}

/**
 * Every shipped text file in an edition, absolute paths. `.py` is included: the shipped hooks are text
 * an agent's host executes, and leaving them out puts them outside every cross-surface sweep.
 */
export function shippedFiles(tree: Tree): string[] {
  const root = `${repoRoot}/dist/${tree}`;
  const out = pathsUnder(root, { extensions: ['.md', '.toml', '.mdc', '.json', '.js', '.py'] });
  expect(out.length, `dist/${tree} yielded ${out.length} files — a sweep that opens almost nothing `
    + 'reports success').toBeGreaterThan(10);
  return out;
}
