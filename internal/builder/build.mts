/**
 * The build: read the version, then per declared file merge variables, render its sources in
 * order, join, write, chmod. `--check` compares a fresh render with committed `dist/` by bytes and
 * permission bits. `bin/recipe.mts` is the process entry point; this module holds the logic.
 */

import { mkdtempSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { createTemplateEngine } from './template-engine.mjs';
import { describeDifferences, findDifferences, listFilesUnder } from './dist-diff.mjs';
import {
  checkWriteGate, loadRecipe, listRecipeNames, WRITE_GATE_DEST, type Recipe,
} from './recipe-loader.mjs';
import { lintRecipes, type NamedRecipe } from './recipe-lints.mjs';
import { renderEntry } from './render-entry.mjs';
import { buildVariableScope } from './variable-scope.mjs';
import { readCanonicalVersion } from '../release/version-files.mjs';
import { writeEntry } from './write-entry.mjs';

const REPO_ROOT = process.cwd();
const DIST = join(REPO_ROOT, 'dist');

/** The recipe file for one distribution, repository-relative. */
export function getRecipePath(name: string): string {
  return `src/targets/${name}.json`;
}

/** Load every recipe on disk — the input both the lints and the build read. */
export function loadAllRecipes(repoRoot: string = REPO_ROOT): NamedRecipe[] {
  return listRecipeNames(join(repoRoot, 'src', 'targets')).map((name) => ({
    file: getRecipePath(name),
    recipe: loadRecipe(getRecipePath(name), repoRoot),
  }));
}

/**
 * Render one distribution into `outRoot`; return the destination paths written, sorted.
 *
 * `version` arrives as an ordinary variable, so a manifest asking for it writes `{{ version }}` like
 * any source asking for anything else.
 */
export async function buildDistribution(
  recipe: Recipe,
  file: string,
  outRoot: string,
  repoRoot: string = REPO_ROOT,
): Promise<string[]> {
  const engine = createTemplateEngine();
  const version = readCanonicalVersion(repoRoot);
  const written: string[] = [];
  for (const [dest, entry] of Object.entries(recipe.targets)) {
    if (entry === null) continue; // an explicit decline — this tool deliberately ships no such file
    const scope = buildVariableScope({ version, ...recipe.variables }, entry.variables ?? {});
    const text = await renderEntry(
      engine,
      entry.sources,
      scope,
      (source) => join(repoRoot, source),
      { config: file, dest, declared: Object.keys(scope).sort() },
    );
    if (dest.endsWith(WRITE_GATE_DEST)) checkWriteGate(text, `${file} → '${dest}'`);
    writeEntry(join(outRoot, dest), text, entry.permissions);
    written.push(dest);
  }
  return written.sort();
}

/** Render `name` into a scratch tree and compare with committed `dist/<name>`; 0 == in sync. */
export async function checkAgainstDist(
  named: NamedRecipe,
  tmpRoot: string,
  distRoot: string = DIST,
  repoRoot: string = REPO_ROOT,
): Promise<number> {
  const out = join(tmpRoot, named.recipe.name);
  await buildDistribution(named.recipe, named.file, out, repoRoot);
  const committed = join(distRoot, named.recipe.name);
  try {
    statSync(committed);
  } catch {
    return listFilesUnder(out).size === 0 ? 0 : 1;
  }
  const differences = findDifferences(committed, out);
  if (differences.length === 0) return 0;
  for (const line of describeDifferences(committed, out, differences)) {
    process.stderr.write(`  ${named.recipe.name}/${line}\n`);
  }
  return 1;
}

/** Parse `--target {name|all} [--check]`; an unrecognised argument errors rather than falling through. */
export function parseCommandLine(argv: readonly string[]): { target: string; check: boolean } {
  let target = 'all';
  let check = false;
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index] as string;
    if (arg === '--target') {
      const value = argv[index + 1];
      if (value === undefined) throw new Error('--target requires a value');
      target = value;
      index += 1;
    } else if (arg.startsWith('--target=')) {
      target = arg.slice('--target='.length);
    } else if (arg === '--check') {
      check = true;
    } else {
      throw new Error(`unrecognized argument: ${arg}`);
    }
  }
  return { target, check };
}

export async function main(
  argv: readonly string[],
  distRoot: string = DIST,
  repoRoot: string = REPO_ROOT,
): Promise<number> {
  const { target, check } = parseCommandLine(argv);
  const all = loadAllRecipes(repoRoot);
  const known = new Map(all.map((named) => [named.recipe.name, named]));
  if (target !== 'all' && !known.has(target)) {
    throw new Error(`unknown target: '${target}' — known: ${[...known.keys()].join(', ')}`);
  }
  // Lints read EVERY recipe, whatever one target was asked for: "is this variable declared in all
  // seven?" has no answer from one file, and a per-target build must not be a way to skip the check.
  lintRecipes(all, repoRoot);
  const selected = target === 'all' ? all : [known.get(target) as NamedRecipe];
  let anyStale = false;
  for (const named of selected) {
    if (check) {
      const tmp = mkdtempSync(join(tmpdir(), 'hercules-recipe-'));
      try {
        if (await checkAgainstDist(named, tmp, distRoot, repoRoot) !== 0) anyStale = true;
      } finally {
        rmSync(tmp, { recursive: true, force: true });
      }
    } else {
      await buildDistribution(named.recipe, named.file, join(distRoot, named.recipe.name), repoRoot);
    }
  }
  if (check && anyStale) {
    process.stderr.write('dist/ does not match a fresh render. Each path above says which fix applies '
      + '— `make build` refreshes stale and missing files but never prunes, so a STRAY file has to be '
      + 'deleted by hand. Commit the result.\n');
  }
  return anyStale ? 1 : 0;
}

