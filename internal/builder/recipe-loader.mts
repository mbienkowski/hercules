/**
 * Loading one recipe: duplicate keys are scanned on the TEXT before parsing (JSON.parse keeps the
 * last of two and says nothing), then the published schema, then the rules a schema cannot state —
 * the file's own name, disjoint namespaces, sources that exist.
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { Ajv, type ErrorObject, type SchemaObject, type ValidateFunction } from 'ajv';

import { assertNamespacesDisjoint, type VariableValue } from './variable-scope.mjs';

/** Raised when a recipe, or a file it declares, is not what it must be. */
export class RecipeError extends Error {
  override readonly name = 'RecipeError';
}

/** One shipped file's declaration. */
export interface RecipeEntry {
  readonly sources: readonly string[];
  readonly variables?: Readonly<Record<string, VariableValue>>;
  readonly permissions?: string;
}

/** One distribution's whole recipe, exactly as it reads on disk. */
export interface Recipe {
  readonly name: string;
  readonly variables: Readonly<Record<string, VariableValue>>;
  readonly runtime_variables: readonly string[];
  readonly targets: Readonly<Record<string, RecipeEntry | null>>;
}

// `process.cwd()`, not a hop relative to this file: this module runs both as source (Vitest, under
// internal/builder/) and as compiled output (.local/ts-out/builder/), which sit at different depths.
const REPO_ROOT = process.cwd();
export const TARGETS_DIR = join(REPO_ROOT, 'src', 'targets');
const RECIPE_SCHEMA_PATH = join(TARGETS_DIR, 'recipe.schema.json');


/** The destination suffix whose rendered JSON is checked against the write-gate schema. */
export const WRITE_GATE_DEST = 'hooks/write_gate.json';

const compiled = new Map<string, ValidateFunction>();

/** The compiled validator for a schema, or for one shape inside it (`#/$defs/writeGate`). */
function validatorFor(schemaPath: string, pointer = ''): ValidateFunction {
  const key = schemaPath + pointer;
  const cached = compiled.get(key);
  if (cached !== undefined) return cached;
  const whole = JSON.parse(readFileSync(schemaPath, 'utf-8')) as SchemaObject;
  const schema = pointer === ''
    ? whole
    : { ...(whole['$defs'] as Record<string, SchemaObject>)['writeGate'], $defs: whole['$defs'] } as SchemaObject;
  // `useDefaults` MUTATES what it validates, so callers pass their own freshly parsed object.
  const validate = new Ajv({ allErrors: true, discriminator: true, useDefaults: true, strict: false })
    .compile(schema);
  compiled.set(key, validate);
  return validate;
}

function formatErrors(errors: readonly ErrorObject[] | null | undefined): string {
  if (errors === null || errors === undefined || errors.length === 0) return 'invalid';
  return errors
    .map((e) => {
      const where = e.instancePath === '' ? '(root)' : e.instancePath;
      const extra = e.params !== undefined && Object.keys(e.params).length > 0
        ? ` ${JSON.stringify(e.params)}`
        : '';
      return `  ${where} ${e.message ?? 'is invalid'}${extra}`;
    })
    .join('\n');
}

/** Every duplicated key in `text`, as `object path → key` — walked on the bytes a parser would discard. */
export function findDuplicateKeys(text: string): Array<{ path: string; key: string; line: number }> {
  const found: Array<{ path: string; key: string; line: number }> = [];
  const seen: Array<Set<string> | null> = []; // null == inside an array, which has no keys
  const path: string[] = [];
  let line = 1;
  let index = 0;
  let lastKey: string | null = null;

  const readString = (): { value: string; startLine: number } => {
    const startLine = line;
    let out = '';
    index += 1; // the opening quote
    while (index < text.length) {
      const character = text[index] as string;
      if (character === '\\') {
        out += text.slice(index, index + 2);
        index += 2;
        continue;
      }
      if (character === '"') {
        index += 1;
        return { value: out, startLine };
      }
      if (character === '\n') line += 1;
      out += character;
      index += 1;
    }
    return { value: out, startLine };
  };

  while (index < text.length) {
    const character = text[index] as string;
    if (character === '\n') { line += 1; index += 1; continue; }
    if (character === '"') {
      const { value, startLine } = readString();
      let peek = index;
      while (peek < text.length && /\s/.test(text[peek] as string)) peek += 1;
      const container = seen[seen.length - 1];
      if (text[peek] === ':' && container !== undefined && container !== null) {
        if (container.has(value)) {
          found.push({ path: path.join('/') || '(root)', key: value, line: startLine });
        }
        container.add(value);
        lastKey = value;
      }
      continue;
    }
    if (character === '{') { seen.push(new Set()); path.push(lastKey ?? '(root)'); lastKey = null; index += 1; continue; }
    if (character === '[') { seen.push(null); path.push(lastKey ?? '[]'); lastKey = null; index += 1; continue; }
    if (character === '}' || character === ']') { seen.pop(); path.pop(); index += 1; continue; }
    index += 1;
  }
  return found;
}

/** Parse `text` as a recipe, refusing a duplicated key before anything can swallow one. */
export function parseRecipeText(text: string, file: string): Recipe {
  const duplicates = findDuplicateKeys(text);
  if (duplicates.length > 0) {
    const lines = duplicates.map((d) => `  line ${d.line}: '${d.key}' under ${d.path}`);
    throw new RecipeError(
      `${file}: duplicate key(s) — JSON silently keeps the LAST one, so an earlier declaration ` +
        `would vanish without a word:\n${lines.join('\n')}`,
    );
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new RecipeError(`${file}: not valid JSON — ${error instanceof Error ? error.message : String(error)}`);
  }
  const validate = validatorFor(RECIPE_SCHEMA_PATH);
  if (!validate(parsed)) {
    throw new RecipeError(
      `${file}: does not match src/targets/recipe.schema.json\n${formatErrors(validate.errors)}`,
    );
  }
  return parsed as Recipe;
}

/** Rules the schema cannot state, checked with the file's real name and the real tree. */
export function checkRecipeAgainstTree(recipe: Recipe, file: string, repoRoot: string): void {
  const stem = (file.split('/').pop() as string).replace(/\.json$/, '');
  if (recipe.name !== stem) {
    throw new RecipeError(
      `${file}: 'name' is '${recipe.name}' but the file is '${stem}.json' — the name IS the ` +
        'directory under dist/, so the two have to agree or the distribution lands somewhere nobody looks',
    );
  }
  assertNamespacesDisjoint(Object.keys(recipe.variables), recipe.runtime_variables, file);
  const missing: string[] = [];
  for (const [dest, entry] of Object.entries(recipe.targets)) {
    if (entry === null) continue;
    assertNamespacesDisjoint(
      Object.keys(entry.variables ?? {}),
      recipe.runtime_variables,
      `${file} → '${dest}'`,
    );
    for (const source of entry.sources) {
      if (!existsSync(join(repoRoot, source))) missing.push(`  '${dest}' ← ${source}`);
    }
  }
  if (missing.length > 0) {
    throw new RecipeError(`${file}: declared source(s) do not exist:\n${missing.join('\n')}`);
  }
}

/** The distributions this checkout builds: one `<name>.json` per tool, read from the directory. */
export function listRecipeNames(dir: string = TARGETS_DIR): string[] {
  return readdirSync(dir)
    .filter((entry) => entry.endsWith('.json') && !entry.endsWith('.schema.json'))
    .map((entry) => entry.slice(0, -'.json'.length))
    .sort();
}

/** Load, parse and check one recipe file. */
export function loadRecipe(file: string, repoRoot: string = REPO_ROOT): Recipe {
  const recipe = parseRecipeText(readFileSync(join(repoRoot, file), 'utf-8'), file);
  checkRecipeAgainstTree(recipe, file, repoRoot);
  return recipe;
}

/** Check a rendered `hooks/write_gate.json` against the shape `hercules_gate.py` really reads. */
export function checkWriteGate(text: string, where: string): void {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new RecipeError(
      `${where}: renders a ${WRITE_GATE_DEST} that is not valid JSON — ` +
        `${error instanceof Error ? error.message : String(error)}`,
    );
  }
  const validate = validatorFor(RECIPE_SCHEMA_PATH, '#/$defs/writeGate');
  if (!validate(parsed)) {
    throw new RecipeError(
      `${where}: does not match recipe.schema.json#/$defs/writeGate\n${formatErrors(validate.errors)}`,
    );
  }
}
