import { readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { describe, expect, it } from 'vitest';

import { loadAllRecipes } from '../../internal/builder/build.mjs';
import type { NamedRecipe } from '../../internal/builder/recipe-lints.mjs';
import { pathsUnder } from '../support/buildTree';
import { isFile, SRC_CONTENT } from './smokeHarness';

/**
 * Every authored command, advisor and skill is present in the COMMITTED `dist/` trees — the bytes a
 * user downloads — at the destination that tool's own recipe declares for it.
 */

const RECIPES: NamedRecipe[] = loadAllRecipes();

/** Every authored source under `folder`, as repository-relative forward-slash paths. */
function authored(folder: string): string[] {
  const root = join(SRC_CONTENT, folder);
  return pathsUnder(root).map((abs) => `src/content/${folder}/${relative(root, abs).split(sep).join('/')}`);
}

const COMMANDS = authored('commands');
const AGENTS = authored('agents');
const SKILLS = authored('skills');

/** Where one recipe sends each source: `source → every destination made from it`. */
function destinations(named: NamedRecipe): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const [dest, entry] of Object.entries(named.recipe.targets)) {
    if (entry === null) continue; // an explicit decline — this tool deliberately ships no such file
    for (const source of entry.sources) {
      out.set(source, [...(out.get(source) ?? []), dest]);
    }
  }
  return out;
}

describe('every authored component reaches every distribution', () => {
  it('there are components and distributions to check', () => {
    // Guards the guard: with either side empty, every case below would pass by checking nothing.
    expect(COMMANDS.length, 'no authored commands were found').toBeGreaterThan(0);
    expect(AGENTS.length, 'no authored advisors were found').toBeGreaterThan(0);
    expect(SKILLS.length, 'no authored skills were found').toBeGreaterThan(0);
    expect(RECIPES.length, 'no distributions were found').toBeGreaterThan(0);
  });

  for (const named of [...RECIPES].sort((a, b) => a.recipe.name.localeCompare(b.recipe.name))) {
    const target = named.recipe.name;
    const dests = destinations(named);
    // A component no entry names has fallen out of the pipeline: absent, not declined in writing.
    const shipped = (relativePath: string): boolean => {
      const landing = dests.get(relativePath);
      if (landing === undefined) return false;
      return landing.every((dest) => isFile(join(process.cwd(), 'dist', target, dest)));
    };

    describe(target, () => {
      it('carries every command a person can run', () => {
        expect(COMMANDS.filter((relativePath) => !shipped(relativePath)), `${target} is missing these commands`).toEqual([]);
      });

      it('carries every advisor the workflow can call on', () => {
        // The workflow asks for a second opinion, gets nothing, and carries on as if it happened.
        expect(AGENTS.filter((relativePath) => !shipped(relativePath)), `${target} is missing these advisors`).toEqual([]);
      });

      it('carries every skill, with the file that defines it', () => {
        expect(SKILLS.filter((relativePath) => !shipped(relativePath)), `${target} is missing these skills`).toEqual([]);
      });

      it('ships nothing empty', () => {
        // A zero-byte file installs cleanly and does nothing — the failure a person blames themselves for.
        const root = join(process.cwd(), 'dist', target);
        const empty: string[] = [];
        const walk = (dir: string): void => {
          for (const entry of readdirSync(dir, { withFileTypes: true })) {
            const path = join(dir, entry.name);
            if (entry.isDirectory()) walk(path);
            else if (statSync(path).size === 0) empty.push(relative(root, path).split(sep).join('/'));
          }
        };
        walk(root);
        expect(empty, `${target} ships empty files`).toEqual([]);
      });
    });
  }
});
