/**
 * The ONE generic extras emitter — every non-content artifact, driven by the descriptor.
 *
 * Four descriptor sections map onto four named emission behaviors (a closed set, validated by
 * `descriptor.mts`):
 * - `artifacts` — inline JSON objects dumped canonically (2-space, trailing newline); `versioned`
 *   substitutes the single `${version}` token from the canonical version, fail-loud on zero/many
 *   (the same contract as the version-injection invariant).
 * - shipped siblings — every `src/ecosystems/<name>.dist.<dest>` file byte-copied to plugin-root
 *   `<dest>`: the filename IS the routing (`descriptor.distFiles`), no separate mapping to drift.
 * - `guard` + `gate` — the shared enforcement code (`src/hooks/`: canonical guard modules and the
 *   ONE generic write-gate adapter) byte-copied into `hooks/`, with the ecosystem's `gate`
 *   parameters emitted as `hooks/gate.json` beside it.
 * - `templates` — `<name>.template.<dest>` sibling text rendered by single-pass placeholder
 *   substitution with values from a closed computed-value vocabulary (`js_string`,
 *   `js_string_list`, `js_root_joins`, `role_entries_js`). Role entries are computed from the SAME
 *   descriptor role fields the standalone files use, so an inlined entry (e.g. OpenCode's
 *   `plugin.js` agent map) and its standalone mirror can never drift by construction.
 *
 * Accepted, documented divergence — NOT covered by `make parity`'s cross-engine fixtures, which
 * require byte-identical output and would simply fail on this input (verified directly: pinned by
 * `genExtras.spec.ts`'s own "V8 key reordering" test instead, the same way `descriptor.mts`
 * documents its own `Object.entries()` divergence rather than fixturing it):
 *
 * - `jsObjectLiteral`'s plain-object branch reads `Object.entries(obj)`, which V8 walks with
 *   integer-like string keys FIRST (ascending, ahead of every other key) regardless of insertion
 *   order; Python's `dict.items()` always preserves insertion order. `js_object_literal({"b": 1,
 *   "1": "one", "a": 2, "0": "zero"})` therefore renders key order `b, 1, a, 0` in Python but `0, 1,
 *   b, a` in this port. Latent in practice: the only real caller (`templateValue`'s
 *   `role_entries_js` branch) always passes a `Map` built from source-file stems, which are never
 *   integer-like, and the `Map` branch above preserves insertion order on BOTH engines regardless.
 */

import { readdirSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';

import { copyMap, readSource, write } from './emit.mjs';
import { ECOSYSTEMS_DIR, distFiles, parseDescriptor } from './descriptor.mjs';
import type { EcosystemDescriptor, Template, TemplateValue } from './descriptor.mjs';
import { computeFields } from './genSerialize.mjs';
import { parseFrontmatter, splitDocument } from './parse.mjs';
import { renderBody } from './render.mjs';

const VERSION_TOKEN = /\$\{version\}/g;
const PLACEHOLDER = /__[A-Z_]+__/g;

/** Raised when a versioned artifact's content does not carry exactly one `${version}` token. */
export class GenExtrasError extends Error {
  override readonly name = 'GenExtrasError';
}

/** Everything `emitExtras` needs to emit a target's non-content artifacts. */
export interface ExtrasContext {
  readonly outRoot: string;
  /** `src/hooks` — canonical guard + generic gate adapter, byte-copied everywhere. */
  readonly sharedHooksSrc: string;
  /** `src/content`. */
  readonly srcContent: string;
  /** The target's token vars. */
  readonly tokens: ReadonlyMap<string, string>;
  /** Canonical build version (from `package.json`) — injected into versioned manifests. */
  readonly version: string;
}

/** The one canonical JSON byte-format every emitted artifact uses. */
function dumpJson(content: unknown): string {
  return `${JSON.stringify(content, null, 2)}\n`;
}

/**
 * Substitute the single `${version}` token; fail LOUD on zero or many — a release manifest must
 * never ship the literal token or a stray extra substitution.
 */
function versionedText(text: string, version: string, dest: string): string {
  const matches = text.match(VERSION_TOKEN);
  const count = matches === null ? 0 : matches.length;
  if (count !== 1) {
    throw new GenExtrasError(`genextras: expected exactly one \${version} token in artifact ${JSON.stringify(dest)}, found ${count}`);
  }
  return text.replace(VERSION_TOKEN, () => version);
}

// ---- JavaScript-literal serialization (generic; used by the js_* template value kinds) ----

const BARE_KEY = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

/** A JSON-serialisable value, generalised over both plain objects and order-preserving Maps. */
export type JsLiteralValue =
  | string
  | number
  | boolean
  | null
  | readonly JsLiteralValue[]
  | JsLiteralMap
  | JsLiteralRecord;

// Split out as their own interfaces (rather than inlined `ReadonlyMap<string, JsLiteralValue>` /
// `Readonly<Record<string, JsLiteralValue>>` directly in the union above): TypeScript's circularity
// check for a recursive type alias does not see through `Readonly<Record<...>>`'s utility-type
// wrapping, and rejects the union as self-referencing even though the recursion is only ever
// reached through a Map/object boundary. An `interface` breaks the cycle the same way a `type`
// with a named object-literal shape would, without losing the `Readonly`/index-signature semantics.
interface JsLiteralMap extends ReadonlyMap<string, JsLiteralValue> {}
interface JsLiteralRecord extends Readonly<Record<string, JsLiteralValue>> {}

/** Return a JSON-stringified JavaScript string literal (non-ASCII kept literal). */
export function jsString(value: string): string {
  return JSON.stringify(value);
}

/** Render a JSON-serialisable value as a JS object literal (keys bare when identifier-safe). */
export function jsObjectLiteral(obj: JsLiteralValue, indent = 8): string {
  const spaces = ' '.repeat(indent);
  if (obj instanceof Map) {
    if (obj.size === 0) return '{}';
    const items = [...obj].map(
      ([k, v]) => `${spaces}  ${BARE_KEY.test(k) ? k : jsString(k)}: ${jsObjectLiteral(v, indent + 2)},`,
    );
    return `{\n${items.join('\n')}\n${spaces}}`;
  }
  if (Array.isArray(obj)) {
    if (obj.length === 0) return '[]';
    return `[${obj.map((v) => jsObjectLiteral(v as JsLiteralValue, indent + 2)).join(', ')}]`;
  }
  if (typeof obj === 'boolean') return obj ? 'true' : 'false';
  if (typeof obj === 'string') return jsString(obj);
  if (obj === null) return 'null';
  if (typeof obj === 'object') {
    // A plain object: same shape as the Map branch above, but reading Object.entries() — the
    // integer-like-key reordering divergence this implies is documented at this file's top.
    const entries = Object.entries(obj as Record<string, JsLiteralValue>);
    if (entries.length === 0) return '{}';
    const items = entries.map(
      ([k, v]) => `${spaces}  ${BARE_KEY.test(k) ? k : jsString(k)}: ${jsObjectLiteral(v, indent + 2)},`,
    );
    return `{\n${items.join('\n')}\n${spaces}}`;
  }
  return String(obj);
}

// ---- role entries (generic; the shared source for inlined entry maps and their mirrors) ----

const ROLE_SUBDIRS: Readonly<Record<string, string>> = { agent: 'agents', command: 'commands' };

export interface RoleEntry {
  readonly stem: string;
  readonly fields: ReadonlyMap<string, string>;
  readonly body: string;
}

/**
 * Collect `{stem, fields, body}` triples for `role` — fields computed from the descriptor's OWN
 * role field specs (minus `name`, which becomes the entry key), body rendered and fully stripped.
 * One source of truth for template entry maps and the standalone-file mirror tests.
 */
export function roleEntries(
  descriptor: EcosystemDescriptor,
  srcContent: string,
  tokens: ReadonlyMap<string, string>,
  role: string,
): RoleEntry[] {
  const dir = join(srcContent, ROLE_SUBDIRS[role] as string);
  const out: RoleEntry[] = [];
  const names = readdirSync(dir).filter((n) => n.endsWith('.md')).sort();
  for (const name of names) {
    const path = join(dir, name);
    const text = readSource(path);
    const { metadata: meta } = parseFrontmatter(text);
    const { body } = splitDocument(text);
    const stem = name.slice(0, -'.md'.length);
    const roleSpec = descriptor.roles[role];
    const fields = computeFields((roleSpec?.fields ?? []), meta, descriptor.name, tokens, stem);
    fields.delete('name');
    out.push({ stem, fields, body: renderBody(body, descriptor.name, tokens).trim() });
  }
  return out;
}

/** Evaluate one closed-vocabulary template value to its substitution text. */
function templateValue(spec: TemplateValue, descriptor: EcosystemDescriptor, ctx: ExtrasContext): string {
  if (spec.kind === 'js_string') return jsString(spec.value as string);
  if (spec.kind === 'js_string_list') return spec.values.map((v) => jsString(v)).join(', ');
  if (spec.kind === 'js_root_joins') {
    return spec.paths.map((p) => `path.join(PLUGIN_ROOT, ${jsString(p)})`).join(',\n        ');
  }
  // spec.kind === 'role_entries_js' — the only other validated kind
  const entries = new Map<string, ReadonlyMap<string, string>>();
  for (const { stem, fields, body } of roleEntries(descriptor, ctx.srcContent, ctx.tokens, spec.role as string)) {
    const kept = new Map(fields);
    for (const dropped of spec.drop) kept.delete(dropped);
    kept.set(spec.bodyKey as string, body);
    entries.set((spec.keyPrefix ?? '') + stem, kept);
  }
  return jsObjectLiteral(entries);
}

/**
 * Single-pass placeholder substitution: every `__X__` is filled from values computed up front, so
 * an inserted value can never be re-scanned and have a LATER placeholder rewritten inside it; an
 * unknown placeholder passes through unchanged.
 */
function renderTemplate(descriptor: EcosystemDescriptor, template: Template, ctx: ExtrasContext): string {
  const text = readSource(join(ECOSYSTEMS_DIR, template.src));
  const values = new Map<string, string>();
  for (const [placeholder, spec] of Object.entries(template.values)) {
    values.set(placeholder, templateValue(spec, descriptor, ctx));
  }
  return text.replace(PLACEHOLDER, (whole) => values.get(whole) ?? whole);
}

/** Emit every non-content artifact the descriptor declares; return the written rels. */
export function emitExtras(ctx: ExtrasContext, descriptor: EcosystemDescriptor): string[] {
  const written: string[] = [];
  for (const artifact of descriptor.artifacts) {
    let text = dumpJson(artifact.content);
    if (artifact.versioned) text = versionedText(text, ctx.version, artifact.dest);
    write(join(ctx.outRoot, artifact.dest), text);
    written.push(artifact.dest);
  }
  const siblings = distFiles(descriptor.name);
  if (Object.keys(siblings).length > 0) {
    const mapping = new Map<string, string>();
    for (const [destName, path] of Object.entries(siblings)) mapping.set(basename(path), destName);
    written.push(...copyMap(ECOSYSTEMS_DIR, ctx.outRoot, mapping));
  }
  if (descriptor.guard.length > 0) {
    const mapping = new Map(descriptor.guard.map((name) => [name, `hooks/${name}`]));
    written.push(...copyMap(ctx.sharedHooksSrc, ctx.outRoot, mapping));
  }
  if (descriptor.gate !== null) {
    write(join(ctx.outRoot, 'hooks', 'gate.json'), dumpJson(descriptor.gate));
    written.push('hooks/gate.json');
  }
  for (const template of descriptor.templates) {
    write(join(ctx.outRoot, template.dest), renderTemplate(descriptor, template, ctx));
    written.push(template.dest);
  }
  return written;
}

/**
 * `parseDescriptor` + `ExtrasContext` + `emitExtras`, composed into ONE module-level function so
 * the parity harness — which only knows how to call a single named function per fixture (see
 * `scripts-ts/bin/parityRun.mts`) — can drive `emitExtras` from a raw descriptor JSON value, the
 * same wire shape the `descriptor`/`genSerialize` modules' own fixtures already use.
 * `sharedHooksSrc`/`srcContent` are the REAL repo directories (not fixture-supplied): every real
 * ecosystem's `guard`/`templates` data names real files there, so a synthetic stand-in would only
 * prove the composition works, not that it works against the actual shipped content the build
 * itself reads. Test-support only; the real CLI composes these steps itself (commit 8's `cli.mts`).
 */
export function emitExtrasForFixture(
  descriptorRaw: unknown,
  tokens: ReadonlyMap<string, string>,
  version: string,
  outRoot: string,
): string[] {
  const name = (descriptorRaw as { name: string }).name;
  const d = parseDescriptor(name, descriptorRaw);
  const src = dirname(ECOSYSTEMS_DIR);
  const ctx: ExtrasContext = {
    outRoot,
    sharedHooksSrc: join(src, 'hooks'),
    srcContent: join(src, 'content'),
    tokens,
    version,
  };
  return emitExtras(ctx, d).slice().sort();
}
