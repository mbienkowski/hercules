import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

/**
 * A throwaway repository for the recipe build to run against: real files, directories, permissions.
 * Nothing is mocked — the build's whole job is turning files on disk into other files on disk.
 */
export interface RecipeFixture {
  /** The scratch repository root. */
  readonly root: string;
  /** Write a file (parents created) at a repository-relative path. */
  file(relativePath: string, text: string): string;
  /** Write `src/targets/<name>.json`, returning its repository-relative path. */
  recipe(name: string, recipe: unknown): string;
}

/** The version files the build's first stage reads. Written into every fixture root. */
const PACKAGE_JSON = `${JSON.stringify({ name: 'fixture', version: '9.9.9' }, null, 2)}\n`;
const PYPROJECT = '[project]\nname = "fixture"\nversion = "9.9.9"\n';

export function recipeFixture(root: string): RecipeFixture {
  const write = (relativePath: string, text: string): string => {
    const full = join(root, relativePath);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, text, 'utf-8');
    return relativePath;
  };
  write('package.json', PACKAGE_JSON);
  write('pyproject.toml', PYPROJECT);
  return {
    root,
    file: write,
    recipe(name: string, recipe: unknown): string {
      return write(`src/targets/${name}.json`, `${JSON.stringify(recipe, null, 2)}\n`);
    },
  };
}

/** A recipe with everything the schema requires and nothing it does not. */
export function minimalRecipe(name: string, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    name,
    variables: {},
    runtime_variables: [],
    targets: { 'README.md': { sources: ['src/content/readme.md'] } },
    ...overrides,
  };
}
