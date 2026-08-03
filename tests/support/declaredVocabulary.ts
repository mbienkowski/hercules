import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { repoRoot } from './repo';

/**
 * Where this project declares its names, read from the declarations themselves — the recipe schema
 * and the guard's own source — so no hand-written allowlist has to be edited as the vocabulary grows.
 */

const SCHEMA = join(repoRoot, 'src', 'targets', 'recipe.schema.json');
const HOOKS = join(repoRoot, 'src', 'scripts', 'hooks');

function schema(): unknown {
  return JSON.parse(readFileSync(SCHEMA, 'utf-8'));
}

function walk(node: unknown, visit: (key: string, value: unknown) => void): void {
  if (node === null || typeof node !== 'object') return;
  if (Array.isArray(node)) {
    node.forEach((child) => walk(child, visit));
    return;
  }
  for (const [key, value] of Object.entries(node)) {
    visit(key, value);
    walk(value, visit);
  }
}

/** Every property name the configuration schema defines, at any depth. */
export function schemaPropertyNames(): Set<string> {
  const names = new Set<string>();
  walk(schema(), (key, value) => {
    if (key === 'properties' && value !== null && typeof value === 'object') {
      Object.keys(value).forEach((name) => names.add(name));
    }
  });
  return names;
}

/** Every value the schema fixes by name — `enum` members and `const` values — words a document may quote. */
export function schemaFixedValues(): Set<string> {
  const values = new Set<string>();
  walk(schema(), (key, value) => {
    if (key === 'enum' && Array.isArray(value)) {
      value.forEach((entry) => { if (typeof entry === 'string') values.add(entry); });
    }
    if (key === 'const' && typeof value === 'string') values.add(value);
  });
  return values;
}

/**
 * Every state key the runtime guard reads, taken from the guard's own source, so a rename in Python
 * shows up on the markdown side rather than hiding in a hand-edited list.
 */
export function stateKeysTheGuardReads(): Set<string> {
  const found = new Set<string>();
  for (const name of readdirSync(HOOKS).filter((file) => file.endsWith('.py'))) {
    const source = readFileSync(join(HOOKS, name), 'utf-8');
    for (const match of source.matchAll(/(?:\.get\(|\[)"([a-z][a-z0-9_]{4,})"/g)) {
      found.add(match[1] as string);
    }
  }
  return found;
}
