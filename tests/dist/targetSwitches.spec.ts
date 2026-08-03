import { readFileSync } from 'node:fs';

import { afterEach, describe, expect, it } from 'vitest';

import { loadAllRecipes } from '../../internal/builder/build.mjs';
import { parseTemplateStructure, lintRecipes, type NamedRecipe } from '../../internal/builder/recipe-lints.mjs';
import type { Recipe } from '../../internal/builder/recipe-loader.mjs';
import { repoRoot } from '../support/repo';
import { recipeFixture } from '../support/recipeWorkspace';
import { tempWorkspace } from '../support/tempWorkspace';

/**
 * A typo in a branch label — `{% if plan_mode == "toool" %}` — silently drops that passage from every
 * distribution. Runs the engine's lints over the REAL recipes and sources; lints.spec.ts uses fixtures.
 */

const scratch = tempWorkspace();
afterEach(scratch.cleanup);

const REAL: NamedRecipe[] = loadAllRecipes(repoRoot);

/** Every source any recipe renders, sorted — the exact set the build's own lints walk. */
function renderedSources(recipes: readonly NamedRecipe[]): string[] {
  const out = new Set<string>();
  for (const { recipe } of recipes) {
    for (const entry of Object.values(recipe.targets)) {
      if (entry !== null) entry.sources.forEach((source) => out.add(source));
    }
  }
  return [...out].sort();
}

/** The first source carrying a `variable == "literal"` branch, with that branch's literal. */
function firstComparedLiteral(): { source: string; literal: string } {
  for (const source of renderedSources(REAL)) {
    const { blocks } = parseTemplateStructure(readFileSync(`${repoRoot}/${source}`, 'utf-8'), source);
    for (const block of blocks) {
      for (const branch of block.branches) {
        if (branch.literal !== null) return { source, literal: branch.literal };
      }
    }
  }
  throw new Error('no source compares a variable against a literal — nothing to spoil');
}

/** The real recipes, narrowed to the entries that render `source`, so every scope stays real. */
function rendering(source: string): NamedRecipe[] {
  return REAL.map(({ file, recipe }) => ({
    file,
    recipe: {
      ...recipe,
      targets: Object.fromEntries(
        Object.entries(recipe.targets).filter(([, entry]) => entry !== null && entry.sources.includes(source)),
      ),
    } as Recipe,
  }));
}

describe('content files never branch on a value no configuration assigns', () => {
  it('every branch label in the real sources names a value some real recipe assigns', () => {
    // The whole tree, exactly as `make build` lints it: seven recipes, every source they name.
    expect(REAL.length, 'no recipes were found to lint').toBeGreaterThan(0);
    expect(renderedSources(REAL).length, 'no sources were found to lint').toBeGreaterThan(0);
    expect(() => lintRecipes(REAL, repoRoot)).not.toThrow();
  });

  it('a spoiled branch label is refused by name — a typo cannot ship as "never taken"', () => {
    const { source, literal } = firstComparedLiteral();
    const bogus = `${literal}-no-configuration-assigns-this`;
    const original = readFileSync(`${repoRoot}/${source}`, 'utf-8');
    const recipes = rendering(source);

    // The unspoiled copy must pass, or a failure below would prove something about the copying.
    const clean = recipeFixture(scratch.make('hercules-switch-clean-'));
    clean.file(source, original);
    expect(() => lintRecipes(recipes, clean.root)).not.toThrow();

    const spoiled = recipeFixture(scratch.make('hercules-switch-spoiled-'));
    spoiled.file(source, original.replace(`== "${literal}"`, `== "${bogus}"`));
    let message = '';
    try {
      lintRecipes(recipes, spoiled.root);
    } catch (error) {
      message = error instanceof Error ? error.message : String(error);
    }
    expect(message, `a bogus branch label in ${source} was accepted`).toContain(bogus);
    expect(message).toContain('no configuration ever assigns that value');
  });
});
