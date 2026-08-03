/**
 * The variables one file renders with: the distribution's, overridden key by key by the entry's.
 *
 * A value is used as written and never re-scanned, so a host's own `${PLACEHOLDER}` travels through
 * untouched.
 */

/** A declared value: text, a real boolean, or `null` meaning "remove this key here". */
export type VariableValue = string | boolean | null;

/** Raised when a scope cannot be built — the two namespaces overlapping is the only way. */
export class ScopeError extends Error {
  override readonly name = 'ScopeError';
}

/** The rendering scope for one entry: `global`, overridden key by key by `entry`. */
export function buildVariableScope(
  global: Readonly<Record<string, VariableValue>>,
  entry: Readonly<Record<string, VariableValue>> = {},
): Record<string, string | boolean> {
  const scope: Record<string, string | boolean> = {};
  for (const [key, value] of Object.entries(global)) {
    if (value !== null) scope[key] = value;
  }
  for (const [key, value] of Object.entries(entry)) {
    // A tombstone DELETES. See this file's header: storing null would render falsy and silent.
    if (value === null) delete scope[key];
    else scope[key] = value;
  }
  return scope;
}

/**
 * Refuse a name claimed as both ours to substitute and the host's to resolve — either guess ships a
 * wrong file, and nothing downstream can tell the two apart.
 */
export function assertNamespacesDisjoint(
  variableNames: readonly string[],
  runtimeNames: readonly string[],
  where: string,
): void {
  const runtime = new Set(runtimeNames);
  const clash = variableNames.filter((name) => runtime.has(name)).sort();
  if (clash.length > 0) {
    throw new ScopeError(
      `${where}: ${clash.map((n) => `'${n}'`).join(', ')} declared both as a build variable and in ` +
        "'runtime_variables' — a name is either ours to substitute now or the host's to resolve later, never both",
    );
  }
}
