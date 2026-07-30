import { existsSync, readdirSync, statSync } from 'node:fs';

import { expect } from 'vitest';

import { readFile } from '../commands/support';
import { repoRoot } from '../../../commons/support/repo';

/**
 * The six shipped editions and where each keeps the artifacts these guards read.
 *
 * One source tree compiles into six, and a change applied to some and not the others is a defect the
 * requirements name outright — so every guard reads all six rather than the gated one. The editions
 * name and wrap the same artifact differently, which is why a path is resolved per edition and an
 * unresolved path is a failure: a sweep that opens nothing passes silently, and that is the exact
 * defect these guards exist to catch.
 */

export const TREES = ['claude-code', 'opencode', 'cursor', 'copilot-cli', 'gemini-cli', 'grok-build'] as const;

export type Tree = (typeof TREES)[number];

/** The always-loaded persona, named differently per host. */
export const PERSONA_PER_TREE: Record<Tree, string> = {
  'claude-code': 'CLAUDE.md',
  'grok-build': 'CLAUDE.md',
  opencode: 'instructions.md',
  cursor: 'rules/hercules-persona.mdc',
  'copilot-cli': 'AGENTS.md',
  'gemini-cli': 'GEMINI.md',
};

/** Commands, whose extension differs per host (Copilot prompts, Gemini TOML). */
export function commandPath(tree: Tree, name: string): string {
  if (tree === 'copilot-cli') return `commands/${name}.prompt.md`;
  if (tree === 'gemini-cli') return `commands/${name}.toml`;
  return `commands/${name}.md`;
}

export const RUBRIC = 'protocols/debate-consensus-protocol.md';
export const REFERENCE = 'skills/hercules-reference/SKILL.md';

/**
 * Read a file from an edition, failing loudly when the edition does not carry it. Returning `''` for
 * a missing path is how a per-edition guard silently degrades into a single-edition one.
 */
export function distFile(tree: Tree, rel: string): string {
  const abs = `${repoRoot}/dist/${tree}/${rel}`;
  expect(existsSync(abs), `dist/${tree}/${rel} does not exist — this edition would be skipped `
    + 'silently, and a guard that opens nothing reports success').toBe(true);
  return readFile(`dist/${tree}/${rel}`);
}

/** Every shipped text file in an edition, absolute paths — a short literal list skips the rest. */
export function shippedFiles(tree: Tree): string[] {
  const root = `${repoRoot}/dist/${tree}`;
  const out: string[] = [];
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      const abs = `${dir}/${name}`;
      if (statSync(abs).isDirectory()) walk(abs);
      else if (/\.(md|toml|mdc|json|js)$/.test(name)) out.push(abs);
    }
  };
  walk(root);
  expect(out.length, `dist/${tree} yielded ${out.length} files — a sweep that opens almost nothing `
    + 'reports success').toBeGreaterThan(10);
  return out;
}
