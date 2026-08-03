import { existsSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { afterAll, describe, expect, it } from 'vitest';

import { buildDistribution, loadAllRecipes } from '../../internal/builder/build.mjs';
import type { NamedRecipe } from '../../internal/builder/recipe-lints.mjs';
import { repoRoot } from '../support/repo';
import { tempWorkspace } from '../support/tempWorkspace';

/**
 * Every authored source either arrives in a tool's distribution or is declined in writing by its
 * recipe — a gap the drift check cannot see, being absent from both trees it compares.
 */

const CONTENT = join(repoRoot, 'src', 'content');
const TARGETS_CONTENT = 'src/content/targets/';
const RECIPES: NamedRecipe[] = loadAllRecipes(repoRoot);
const workspace = tempWorkspace();

afterAll(workspace.cleanup);

/** Every authored source under src/content/, as repository-relative forward-slash paths. */
function sources(dir: string = CONTENT): string[] {
  const found: string[] = [];
  for (const name of readdirSync(dir).sort()) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (name !== 'tests') found.push(...sources(path));
    } else {
      found.push(`src/content/${relative(CONTENT, path).split(sep).join('/')}`);
    }
  }
  return found;
}

const SOURCES = sources();

/** What `name` is owed: everything authored, minus the material that belongs to another tool. */
function owed(name: string): string[] {
  const mine = `${TARGETS_CONTENT}${name}/`;
  return SOURCES.filter((relativePath) => !relativePath.startsWith(TARGETS_CONTENT) || relativePath.startsWith(mine));
}

/** Every source a recipe names, across all of its entries that ship something. */
function declared(named: NamedRecipe): Set<string> {
  const out = new Set<string>();
  for (const entry of Object.values(named.recipe.targets)) {
    if (entry !== null) entry.sources.forEach((source) => out.add(source));
  }
  return out;
}

describe('nothing an author writes falls out of a distribution unannounced', () => {
  it('there are sources and distributions to account for', () => {
    // Guards the guard: an empty walk would make every check below pass by having nothing to check.
    expect(SOURCES.length).toBeGreaterThan(0);
    expect(RECIPES.length).toBeGreaterThan(0);
  });

  for (const named of [...RECIPES].sort((a, b) => a.recipe.name.localeCompare(b.recipe.name))) {
    const target = named.recipe.name;

    it(`${target} ships every source it did not explicitly decline`, async () => {
      const names = declared(named);
      const authored = new Set(SOURCES);

      // Both sides come from the configuration, never the build — this must be able to disagree with it.
      const dropped = owed(target).filter((relativePath) => !names.has(relativePath));
      expect(dropped, `${target} renders none of these authored sources`).toEqual([]);

      const foreign = [...names].filter((relativePath) => authored.has(relativePath) && !owed(target).includes(relativePath));
      expect(foreign, `${target} renders content that belongs to another tool`).toEqual([]);

      // What the configuration promises is what lands: every declared destination, and nothing else.
      const root = workspace.make(`hercules-delivery-${target}-`);
      const written = await buildDistribution(named.recipe, named.file, root, repoRoot);
      const shipping = Object.entries(named.recipe.targets)
        .filter(([, entry]) => entry !== null)
        .map(([dest]) => dest)
        .sort();
      expect(written).toEqual(shipping);
      for (const dest of written) {
        expect(existsSync(join(root, dest)), `${target}: ${dest} was promised but not written`).toBe(true);
      }
    });
  }

  it('a tool that declines a file names one that exists, and every source it names is real', () => {
    // A `null` decline naming a destination nothing ships, or a `sources` path that is gone, looks
    // like a deliberate choice while protecting nothing, and hides the next real omission.
    const shippedSomewhere = new Set<string>();
    for (const { recipe } of RECIPES) {
      for (const [dest, entry] of Object.entries(recipe.targets)) {
        if (entry !== null) shippedSomewhere.add(dest);
      }
    }

    const stale: string[] = [];
    for (const { file, recipe } of RECIPES) {
      for (const [dest, entry] of Object.entries(recipe.targets)) {
        if (entry === null) {
          if (!shippedSomewhere.has(dest)) stale.push(`${file}: declines '${dest}', which nothing ships`);
          continue;
        }
        for (const source of entry.sources) {
          if (!existsSync(join(repoRoot, source))) stale.push(`${file}: '${dest}' ← ${source} (missing)`);
        }
      }
    }
    expect(stale, 'these configurations point at a file that no longer exists').toEqual([]);
    // Guards the guard: with nothing declared, the loop above would report a clean bill of health.
    expect(shippedSomewhere.size, 'no distribution declares a single shipped file').toBeGreaterThan(0);
  });
});
