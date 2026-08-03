import { describe, expect, it } from 'vitest';

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { loadAllRecipes } from '../../internal/builder/build.mjs';
import { parseTemplateStructure } from '../../internal/builder/recipe-lints.mjs';
import { repoRoot } from '../support/repo';

/**
 * Seven flat recipes are near-copies, and near-copies drift. This compares their SHAPES, not their
 * contents: the same variable NAMES everywhere, and one shared destination built from one source set.
 */

const RECIPES = loadAllRecipes(repoRoot);

/** A destination built from a file under `src/content/targets/<ecosystem>/` is that tool's own. */
function isEcosystemSpecific(sources: readonly string[]): boolean {
  return sources.some((source) => source.startsWith('src/content/targets/'));
}

describe('seven flat configurations stay in step', () => {
  it('there are several configurations to compare', () => {
    // Guards the guard: with fewer than two recipes every comparison below is vacuously true.
    expect(RECIPES.length, 'fewer than two recipes — nothing to compare').toBeGreaterThan(1);
  });

  it('every configuration declares the same variable names', () => {
    const [first, ...rest] = RECIPES;
    const expected = Object.keys((first as (typeof RECIPES)[number]).recipe.variables).sort();
    expect(expected.length, 'the first recipe declares no variables at all').toBeGreaterThan(0);
    for (const { file, recipe } of rest) {
      const actual = Object.keys(recipe.variables).sort();
      const missing = expected.filter((name) => !actual.includes(name));
      const extra = actual.filter((name) => !expected.includes(name));
      expect(
        { missing, extra },
        `${file} and ${(first as (typeof RECIPES)[number]).file} declare different variables — a `
          + 'variable added to one configuration and forgotten in another is how a condition goes '
          + 'quiet on the tool nobody tested',
      ).toEqual({ missing: [], extra: [] });
    }
  });

  it('a destination several tools ship is built from the same sources', () => {
    const byDest = new Map<string, Array<{ file: string; sources: readonly string[] }>>();
    for (const { file, recipe } of RECIPES) {
      for (const [dest, entry] of Object.entries(recipe.targets)) {
        if (entry === null || isEcosystemSpecific(entry.sources)) continue;
        const seen = byDest.get(dest) ?? [];
        seen.push({ file, sources: entry.sources });
        byDest.set(dest, seen);
      }
    }
    const shared = [...byDest.entries()].filter(([, entries]) => entries.length > 1);
    expect(shared.length, 'no destination is shared between two tools — nothing was compared')
      .toBeGreaterThan(0);
    for (const [dest, entries] of shared) {
      const [first, ...rest] = entries as [{ file: string; sources: readonly string[] }, ...Array<{ file: string; sources: readonly string[] }>];
      for (const other of rest) {
        expect(
          other.sources,
          `'${dest}' is built from different sources in ${other.file} and ${first.file} — one of `
            + 'them names a file that exists and is not the right one, which no existence check can see',
        ).toEqual(first.sources);
      }
    }
  });

  it('every variable a configuration declares is one some source actually uses', () => {
    // The mirror of the engine's lint: it refuses an undeclared variable, this refuses an unused one.
    const mentioned = new Set<string>(['version']);
    const sources = new Set(
      RECIPES.flatMap(({ recipe }) => Object.values(recipe.targets))
        .filter((entry): entry is NonNullable<typeof entry> => entry !== null)
        .flatMap((entry) => entry.sources),
    );
    for (const source of sources) {
      for (const name of parseTemplateStructure(readFileSync(join(repoRoot, source), 'utf-8'), source).mentions) {
        mentioned.add(name);
      }
    }
    for (const { file, recipe } of RECIPES) {
      const unused = Object.keys(recipe.variables).filter((name) => !mentioned.has(name)).sort();
      expect(unused, `${file} declares variables no source ever mentions`).toEqual([]);
    }
  });
});
