/**
 * Ecosystem descriptors — the ONE per-ecosystem file, loaded and validated (closed vocabulary).
 *
 * An ecosystem is described entirely by `src/ecosystems/<name>.json`: token `vars`, `models`
 * tiers, the `smoke` install matrix entry, per-role output shapes (`roles`), destination `routes`,
 * inline JSON `artifacts`, shared-`guard` modules, write-`gate` params, and rendered `templates`.
 * The filename is the registry key; discovery is a glob — a new ecosystem is one new JSON file,
 * never new TypeScript.
 *
 * The DIRECTORY itself has a definitive schema, validated on discovery: every file is either a
 * `<name>.json` descriptor or a `<name>.dist.<dest>` shipped file — the filename IS the contract,
 * so the input→output mapping is a pure, testable function of the name. A stray file, an unknown
 * ecosystem prefix, or a nested dest fails discovery loudly.
 *
 * The vocabulary is CLOSED: a descriptor selects named, mutation-covered behaviours and supplies
 * operands only. An unknown key or enum value throws {@link DescriptorError} naming the offending
 * key and the allowed set — control flow stays typed, descriptors stay data.
 *
 * ── Zod validation (commit 5 of the migration) ───────────────────────────────
 * `parseDescriptor` is now backed by a Zod v4 schema: five `z.discriminatedUnion()`s (field `from`,
 * role `mode`, route `kind`, gate `protocol`, template-value `from`) each built from `z.strictObject`
 * variants — `strictObject`'s own unknown-key rejection replaces the hand-rolled `checkKeys` +
 * per-mode allowed-key tables commit 4 carried. Two `.superRefine()` blocks enforce the cross-field
 * rules a discriminated union can't express alone: wrap-mode fields must all be literals, and
 * `toml_command` emits exactly one field named `description`. `models` is a `z.partialRecord` over
 * the three tiers, nullable per tier, refined non-empty.
 *
 * Every issue gets a CUSTOM message via each schema node's own `error` callback — this is the actual
 * point of choosing Zod (see the migration spec's few-shot catalogue): byte-identical Python error
 * TEXT was a commit-4-only goal, not a permanent contract. What replaced it: every thrown
 * `DescriptorError` now carries the Zod-derived, dot/bracket-notation PATH of every failing field
 * ahead of its message (`roles.agent.fields[2].value: ...`), and — because Zod validates the WHOLE
 * shape rather than failing fast on the first problem the way commit 4's hand-written checks did —
 * a descriptor with several simultaneous problems now reports ALL of them in one error, semicolon
 * -separated, not just the first one encountered. `pyReprValue` still formats the "got X" part of
 * most leaf messages, for continuity with the rest of this codebase's formatting conventions; it is
 * a style choice here, not a parity requirement.
 *
 * `descriptor.mts` is the ONLY module in this codebase importing `zod` — every other module consumes
 * the plain `EcosystemDescriptor`/`RoleSpec`/etc. interfaces below, inferred from this file's schemas
 * but exported as ordinary TypeScript types. That boundary is what makes a future `z.toJSONSchema()`
 * follow-up (validating `src/ecosystems/*.json` live in an editor) a near-free addition later.
 *
 * Filesystem functions (`load`/`discover`/`distFiles`/`names`/`validateLayout`) are UNCHANGED from
 * commit 4 — Zod validates the parsed JSON shape, not the directory layout, so nothing here needed
 * to move.
 *
 * Accepted, documented divergences (all pre-dating this commit; see commit 4's own history for how
 * each was found — most are now MOOT rather than merely accepted, because Zod's own structural
 * checks made the original hand-written special case unnecessary):
 *
 * - Python treats `bool` as an `int` subclass, so `True == 1` makes `schema: true` ambiguously
 *   pass the `!= 1` check there. This port does not replicate that — `schema` must be exactly the
 *   JSON number 1.
 *
 * - Every `x not in <enum>` check backed by a Python SET (`dispatch`, role `mode`, route `kind`,
 *   gate `protocol`, field `from`, template-value `from`) CRASHES with an unhandled
 *   `TypeError: unhashable type` if the offending value is a list or a dict. Zod's own enum/literal
 *   matching never crashes regardless of input type, which is strictly more robust, not a regression.
 *
 * - `load`/`discover` guard the `*.json` glob with `statSync(path).isFile()` before reading it, where
 *   Python's own `path.read_text()` / `Path.glob("*.json")` would crash on a directory literally
 *   named `<name>.json` with an unhandled `IsADirectoryError`. `validateLayout`'s own sibling-file
 *   walk and `distFiles` both already carry an equivalent `is_file()` guard on the Python side too
 *   (`descriptor.py` lines 450 and 470), so only the `discover()` glob path itself diverges.
 *
 * - `load()`'s `JSON.parse` rejects the bare `NaN`/`Infinity`/`-Infinity` tokens that Python's
 *   `json.loads` accepts by default (a Python-specific, spec-violating extension). A descriptor file
 *   containing one crashes this port with an uncaught `SyntaxError` before `parseDescriptor` ever
 *   runs; Python parses it into `float('nan')`/`float('inf')` and rejects it through the normal,
 *   non-crashing path instead. Accepted because no legitimate descriptor ever contains a
 *   non-standard JSON token. (See below for the SECOND, narrower TS-stricter divergence — `key_prefix`
 *   — this file no longer claims to have only one.)
 *
 * - `role_entries_js`'s `key_prefix` is typed `z.string().nullable().default('')`, but Python's
 *   `TemplateValue` is a dataclass with an unenforced `str` annotation — `key_prefix=raw.get(
 *   "key_prefix", "")` accepts any JSON type at runtime with no `isinstance` check at all (a number,
 *   list, or object silently lands on the field as-is). Zod's `z.string()` rejects anything that
 *   isn't a string, null, or absent. Reverse-direction from every other divergence above (TS
 *   stricter, not looser) and low-impact — caught by review, no real descriptor has ever authored a
 *   non-string `key_prefix` — but recorded here rather than left to contradict the NaN/Infinity
 *   bullet's now-inaccurate "the one divergence" framing.
 *
 * - `Object.entries()`/`Object.keys()` on a plain JS object reorder integer-like string keys ahead of
 *   every other key, regardless of the source JSON's actual key order; Python's `dict.items()` always
 *   preserves it. `vars` and a `pre_tool` gate's `tools` both iterate their raw object this way (via
 *   Zod's own record/object traversal now, same underlying JS semantics as commit 4's hand-written
 *   loops) — a descriptor with MULTIPLE invalid entries in either section, where at least one key
 *   looks like a non-negative integer, can report a DIFFERENT offending key first than Python does.
 *   Moot in one sense post-Zod: since Zod reports ALL bad entries, not just the first, this only
 *   changes ORDER within the joined message, never which entries are reported at all.
 *
 * - An integer-VALUED float is indistinguishable from a true int once `JSON.parse` sees it — JS has
 *   one numeric type, so `JSON.parse('5.0')` and `JSON.parse('5')` are identical by the time any
 *   validation code runs. UNCHANGED post-Zod: the top-level "not an object" error's custom message
 *   callback still runs commit 4's own `Number.isInteger` check directly against the real
 *   `issue.input` value (Zod's OWN default `received: "number"` field doesn't distinguish them, but
 *   that only matters if the message relied on Zod's default text, which this one doesn't). Only the
 *   genuinely unavoidable integer-valued-float case remains a divergence — a plain `5.5` still
 *   correctly reports `got float`.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { z } from 'zod';

import { pyRepr, pyReprValue } from './pyCompat.mjs';

// Sibling filename markers: "<eco>.dist.<dest>" ships byte-identically at plugin-root <dest>;
// "<eco>.template.<dest>" is a text template the descriptor's `templates` section renders.
const DIST_MARKER = '.dist.';
const TEMPLATE_MARKER = '.template.';
const PLACEHOLDER = /^__[A-Z_]+__$/;
const ROLE_NAMES = ['agent', 'command', 'persona', 'default'] as const;

export class DescriptorError extends Error {
  override readonly name = 'DescriptorError';
}

// ── Shared leaf schemas and message formatting ─────────────────────────────

/** A Zod issue path (`['roles','agent','fields',2,'value']`) as `roles.agent.fields[2].value`. */
function formatPath(path: readonly PropertyKey[]): string {
  return path
    .map((segment, i) => (typeof segment === 'number' ? `[${segment}]` : i === 0 ? String(segment) : `.${String(segment)}`))
    .join('');
}

/** Every Zod issue's own `error` callback supplies the "what's wrong" half; this supplies "where". */
function formatIssue(issue: z.core.$ZodIssue): string {
  const where = formatPath(issue.path);
  return where ? `${where}: ${issue.message}` : issue.message;
}

/**
 * `DescriptorError`'s message for a whole failed parse: every issue Zod collected, not just the
 * first — Zod validates the WHOLE shape rather than failing fast the way commit 4's hand-written
 * checks did, so a descriptor with several simultaneous problems now reports all of them at once.
 */
function formatError(descriptorName: string, error: z.core.$ZodError): string {
  const parts = error.issues.map(formatIssue);
  return `ecosystem descriptor ${pyRepr(descriptorName)}: ${parts.join('; ')}`;
}

/** A required, non-empty string leaf — the single most common check in this schema. */
function nonEmptyStr(): z.ZodString {
  return z.string({ error: (issue) => `must be a non-empty string, got ${pyReprValue(issue.input)}` })
    .min(1, { error: (issue) => `must be a non-empty string, got ${pyReprValue(issue.input)}` });
}

/** A dest/src path inside the tree: relative, no parent escapes. */
function relPath() {
  return nonEmptyStr().check((ctx) => {
    const path = ctx.value;
    if (path.startsWith('/') || path.split('/').includes('..')) {
      ctx.issues.push({
        code: 'custom',
        input: path,
        message: `must be a relative path without '..', got ${pyRepr(path)}`,
      });
    }
  });
}

function oneOf<T extends readonly [string, ...string[]]>(values: T): z.ZodEnum<{ [K in T[number]]: K }> {
  const sorted = [...values].sort();
  const shape = Object.fromEntries(values.map((v) => [v, v])) as { [K in T[number]]: K };
  return z.enum(shape, { error: (issue) => `must be one of ${pyReprValue(sorted)}, got ${pyReprValue(issue.input)}` });
}

/**
 * `z.strictObject()`'s own object-level `error` param fires for BOTH "the input isn't an object at
 * all" (`invalid_type`) and "the input has a key `strictObject` doesn't recognise" (`unrecognized_
 * keys`) — a single string param can't distinguish them, so every `strictObject` in this file that
 * needs a custom "must be an object" message ALSO needs this to keep its unknown-key message
 * sensible rather than falling back to Zod's generic one.
 */
function objectError(label: string): (issue: { code: string; input?: unknown; keys?: string[] }) => string | undefined {
  return (issue) => {
    if (issue.code === 'invalid_type') return `${label} must be an object, got ${pyReprValue(issue.input)}`;
    if (issue.code === 'unrecognized_keys') {
      return `${label} has unknown key(s) ${pyReprValue([...(issue.keys ?? [])].sort())}`;
    }
    // Structurally unreachable, not merely untested: `z.strictObject()`'s OWN object-level check
    // (as opposed to a nested field's) can only ever produce 'invalid_type' or 'unrecognized_keys'
    // at this object's own path — every other issue code Zod defines belongs to a FIELD schema
    // (too_small, invalid_value, ...) or a record/union wrapper this function is never attached to,
    // and those report through their OWN error settings at their OWN nested path, never through
    // this callback. Kept as a fallback anyway so this function's return type stays honest (Zod's
    // `error` callback signature always permits `undefined`) rather than asserting a code union
    // this function doesn't actually need to enumerate.
    return undefined;
  };
}

/**
 * `z.discriminatedUnion(field, variants)`'s own top-level `error` param fires for TWO distinct
 * issue codes, exactly the same ambiguity `objectError` above resolves for `strictObject`: `
 * invalid_union` when the input IS an object but its discriminant value matches no variant (read
 * the real discriminant off `issue.input[field]`), and `invalid_type` when the input isn't an
 * object at all (a string/array/number/null) — there `issue.input[field]` is always `undefined`,
 * so reporting it would print "got None" regardless of the actual offending value. A code-blind
 * version of this shipped briefly and was caught by review before commit: `routes: ['oops']`
 * rendered "'kind' must be one of [...], got None" instead of naming the string `'oops'` that was
 * actually rejected. Shared by all five discriminated unions in this file so each call site stays
 * a single, unindented line instead of repeating this cast-and-format boilerplate five times over.
 */
function discriminantError(field: string, values: readonly string[]) {
  const sorted = [...values].sort();
  return (issue: { code: string; input?: unknown }) => {
    const got = issue.code === 'invalid_type'
      ? issue.input
      : (issue.input as Record<string, unknown> | undefined)?.[field];
    return `'${field}' must be one of ${pyReprValue(sorted)}, got ${pyReprValue(got)}`;
  };
}

// ── Shapes ──────────────────────────────────────────────────────────────────

/**
 * The closed field-generator vocabulary — kept as a literal union (not widened to `string`)
 * specifically so a CONSUMER of `FieldSpec` (`genSerialize.mts`'s `computeFields`) can dispatch on
 * `.source` through an exhaustive switch ending `satisfies never`: a sixth generator added here
 * without a matching case there is then a compile error in the CONSUMER too, not just a runtime
 * surprise discovered by running the build.
 */
export type FieldSource = 'flag_if_name_in' | 'frontmatter' | 'literal' | 'primary_mode' | 'stem';

/** One emitted frontmatter field: its output `key` and the named generator producing it. */
export interface FieldSpec {
  readonly key: string;
  readonly source: FieldSource;
  readonly field: string | null;
  readonly render: boolean;
  readonly value: string | null;
  readonly primary: string | null;
  readonly names: readonly string[];
}

const emptyField = { field: null, render: false, value: null, primary: null, names: [] } as const;

const FieldSchema = z.discriminatedUnion('from', [
  z.strictObject({
    key: nonEmptyStr(), from: z.literal('frontmatter'),
    field: nonEmptyStr(), render: z.boolean({ error: () => 'must be a boolean' }).default(false),
  }, { error: objectError('field (from=frontmatter)') })
    .transform((f): FieldSpec => ({ key: f.key, source: f.from, ...emptyField, field: f.field, render: f.render })),
  z.strictObject({ key: nonEmptyStr(), from: z.literal('stem') }, { error: objectError('field (from=stem)') })
    .transform((f): FieldSpec => ({ key: f.key, source: f.from, ...emptyField })),
  z.strictObject(
    { key: nonEmptyStr(), from: z.literal('literal'), value: nonEmptyStr() },
    { error: objectError('field (from=literal)') },
  ).transform((f): FieldSpec => ({ key: f.key, source: f.from, ...emptyField, value: f.value })),
  z.strictObject(
    { key: nonEmptyStr(), from: z.literal('primary_mode'), primary: nonEmptyStr() },
    { error: objectError('field (from=primary_mode)') },
  ).transform((f): FieldSpec => ({ key: f.key, source: f.from, ...emptyField, primary: f.primary })),
  z.strictObject({
    key: nonEmptyStr(), from: z.literal('flag_if_name_in'),
    names: z.array(nonEmptyStr(), { error: () => 'must be a non-empty list' }).min(1, { error: () => 'must be a non-empty list' }),
    value: nonEmptyStr(),
  }, { error: objectError('field (from=flag_if_name_in)') })
    .transform((f): FieldSpec => ({ key: f.key, source: f.from, ...emptyField, value: f.value, names: f.names })),
], { error: discriminantError('from', ['flag_if_name_in', 'frontmatter', 'literal', 'primary_mode', 'stem']) });

/** How one role (agent/command/persona/default) serializes for this ecosystem. */
export interface RoleSpec {
  readonly mode: string;
  readonly fields: readonly FieldSpec[];
  readonly body: string;
  readonly resolveModelTier: boolean;
  readonly required: readonly string[];
}

const BODY = oneOf(['keep', 'lstrip_newlines', 'strip_newlines']);
const nonEmptyFields = z.array(FieldSchema).min(1, { error: () => "requires a non-empty 'fields' list" });

const RoleSchema = z.discriminatedUnion('mode', [
  z.strictObject({
    mode: z.literal('preserve'),
    resolve_model_tier: z.boolean({ error: () => 'must be a boolean' }).default(false),
    required: z.array(nonEmptyStr(), { error: () => 'must be a list' }).default([]),
  }, { error: objectError('role (mode=preserve)') }),
  z.strictObject({
    mode: z.literal('fields'), fields: nonEmptyFields, body: BODY.default('keep'),
  }, { error: objectError('role (mode=fields)') }),
  z.strictObject({ mode: z.literal('wrap'), fields: nonEmptyFields }, { error: objectError('role (mode=wrap)') }),
  z.strictObject({ mode: z.literal('plain') }, { error: objectError('role (mode=plain)') }),
  z.strictObject({
    mode: z.literal('toml_command'), fields: nonEmptyFields, body: BODY.default('keep'),
  }, { error: objectError('role (mode=toml_command)') }),
], { error: discriminantError('mode', ['fields', 'plain', 'preserve', 'toml_command', 'wrap']) })
  .transform((r): RoleSpec => ({
    mode: r.mode,
    fields: 'fields' in r ? r.fields : [],
    body: 'body' in r ? r.body : 'keep',
    resolveModelTier: 'resolve_model_tier' in r ? r.resolve_model_tier : false,
    required: 'required' in r ? r.required : [],
  }))
  .check((ctx) => {
    const role = ctx.value;
    if (role.mode === 'wrap' && role.fields.some((f) => f.source !== 'literal')) {
      ctx.issues.push({ code: 'custom', input: role, message: "wrap-mode fields must all be literals (generated frontmatter)" });
    }
    if (role.mode === 'toml_command') {
      const keys = role.fields.map((f) => f.key);
      if (keys.length !== 1 || keys[0] !== 'description') {
        ctx.issues.push({ code: 'custom', input: role, message: "toml_command emits exactly one field, 'description'" });
      }
    }
  });

/** One src→dest relocation rule (ordered, first match wins, identity fallback). */
export interface Route {
  readonly kind: string;
  readonly src: string | null;
  readonly dest: string | null;
  readonly prefix: string | null;
  readonly fromSuffix: string | null;
  readonly toSuffix: string | null;
}

const emptyRoute = { src: null, dest: null, prefix: null, fromSuffix: null, toSuffix: null } as const;

const RouteSchema = z.discriminatedUnion('kind', [
  z.strictObject(
    { kind: z.literal('exact'), src: relPath(), dest: relPath() },
    { error: objectError('route (kind=exact)') },
  ).transform((r): Route => ({ kind: r.kind, ...emptyRoute, src: r.src, dest: r.dest })),
  z.strictObject({
    kind: z.literal('suffix_swap'), prefix: relPath(), from_suffix: relPath(), to_suffix: relPath(),
  }, { error: objectError('route (kind=suffix_swap)') }).transform((r): Route => ({
    kind: r.kind, ...emptyRoute, prefix: r.prefix, fromSuffix: r.from_suffix, toSuffix: r.to_suffix,
  })),
  z.strictObject({ kind: z.literal('omit'), src: relPath() }, { error: objectError('route (kind=omit)') })
    .transform((r): Route => ({ kind: r.kind, ...emptyRoute, src: r.src })),
], { error: discriminantError('kind', ['exact', 'omit', 'suffix_swap']) });

/** One inline-JSON file the build emits: `content` dumped canonically to `dest`. */
export interface Artifact {
  readonly dest: string;
  readonly content: Readonly<Record<string, unknown>>;
  readonly versioned: boolean;
}

const ArtifactSchema = z.strictObject({
  dest: relPath(),
  content: z.record(z.string(), z.unknown(), { error: () => "'content' must be a JSON object" }),
  versioned: z.boolean({ error: () => "'versioned' must be a boolean" }).default(false),
}, { error: objectError('an artifact') })
  .transform((a): Artifact => ({ dest: a.dest, content: a.content, versioned: a.versioned }));

/** One computed template value: a closed `kind` plus its data operands. */
export interface TemplateValue {
  readonly kind: string;
  readonly value: string | null;
  readonly values: readonly string[];
  readonly paths: readonly string[];
  readonly role: string | null;
  readonly drop: readonly string[];
  readonly bodyKey: string | null;
  readonly keyPrefix: string | null;
}

// Python's TemplateValue dataclass defaults `key_prefix` to `""` at the FIELD level: js_string/
// js_string_list/js_root_joins never pass key_prefix to the constructor at all, so they always get
// that structural `""` default. Only role_entries_js reads an explicit `key_prefix` from raw input.
const emptyTplVal = { value: null, values: [], paths: [], role: null, drop: [], bodyKey: null, keyPrefix: '' } as const;

const TemplateValueSchema = z.discriminatedUnion('from', [
  z.strictObject(
    { from: z.literal('js_string'), value: nonEmptyStr() },
    { error: objectError('template value (from=js_string)') },
  ).transform((v): TemplateValue => ({ kind: v.from, ...emptyTplVal, value: v.value })),
  z.strictObject({
    from: z.literal('js_string_list'),
    values: z.array(nonEmptyStr(), { error: () => "'values' must be a non-empty list" }).min(1, { error: () => "'values' must be a non-empty list" }),
  }, { error: objectError('template value (from=js_string_list)') })
    .transform((v): TemplateValue => ({ kind: v.from, ...emptyTplVal, values: v.values })),
  z.strictObject({
    from: z.literal('js_root_joins'),
    paths: z.array(relPath(), { error: () => "'paths' must be a non-empty list" }).min(1, { error: () => "'paths' must be a non-empty list" }),
  }, { error: objectError('template value (from=js_root_joins)') })
    .transform((v): TemplateValue => ({ kind: v.from, ...emptyTplVal, paths: v.paths })),
  z.strictObject({
    from: z.literal('role_entries_js'),
    role: oneOf(ROLE_NAMES),
    drop: z.array(nonEmptyStr(), { error: () => "'drop' must be a list" }).default([]),
    body_key: nonEmptyStr(),
    key_prefix: z.string().nullable().default(''),
  }, { error: objectError('template value (from=role_entries_js)') }).transform((v): TemplateValue => ({
    kind: v.from, ...emptyTplVal, role: v.role, drop: v.drop, bodyKey: v.body_key, keyPrefix: v.key_prefix,
  })),
], { error: discriminantError('from', ['js_root_joins', 'js_string', 'js_string_list', 'role_entries_js']) });

/** One rendered template: a `<eco>.template.<dest>` sibling filled with computed values. */
export interface Template {
  readonly src: string;
  readonly dest: string;
  readonly values: Readonly<Record<string, TemplateValue>>;
}

const TemplateSchema = z.strictObject({
  src: nonEmptyStr().check((ctx) => {
    if (ctx.value.includes('/') || !ctx.value.includes(TEMPLATE_MARKER)) {
      ctx.issues.push({
        code: 'custom', input: ctx.value,
        message: `'src' must be a flat '<eco>${TEMPLATE_MARKER}<dest>' sibling, got ${pyRepr(ctx.value)}`,
      });
    }
  }),
  dest: relPath(),
  values: z.record(
    z.string().regex(PLACEHOLDER, { error: (issue) => `placeholder ${pyRepr(String(issue.input))} must match __UPPER_SNAKE__` }),
    TemplateValueSchema,
    {
      // Same class of bug as ModelsSchema's — caught by the SAME review pass: a code-blind `error`
      // here swallowed the key schema's own "must match __UPPER_SNAKE__" message under the generic
      // "'values' must be an object" text for a MALFORMED PLACEHOLDER (code 'invalid_key'), not just
      // for "values isn't an object at all" (code 'invalid_type'). Unlike objectError/ModelsSchema's
      // invalid_key branch, `z.record()`'s own key-schema error does NOT bubble up to this issue's
      // own `.message` even when this callback returns `undefined` for it (verified empirically) —
      // it stays the generic "Invalid key in record" wrapper text — so the nested issue's message
      // has to be read out and returned explicitly here.
      error: (issue) => {
        if (issue.code === 'invalid_type') return "'values' must be an object";
        if (issue.code === 'invalid_key') {
          const nested = (issue as { issues?: readonly { message: string }[] }).issues ?? [];
          return nested[0]?.message;
        }
        return undefined;
      },
    },
  ).default({}),
}, { error: objectError('a template') })
  .transform((t): Template => ({ src: t.src, dest: t.dest, values: t.values }));

/** One write-gate configuration — returned as-is (not transformed), matching Python's dict. */
const GateSchema = z.discriminatedUnion('protocol', [
  z.strictObject({
    protocol: z.literal('pre_tool'),
    tools: z.record(z.string(), nonEmptyStr(), { error: () => "'tools' must be a non-empty object mapping host tool → canonical tool" })
      .refine((t) => Object.keys(t).length > 0, { error: () => "'tools' must be a non-empty object mapping host tool → canonical tool" }),
    path_keys: z.array(z.unknown()).min(1, { error: () => "'path_keys' must be a non-empty list" }),
    nested_keys: z.array(z.unknown(), { error: () => "'nested_keys' must be a list" }).optional(),
    allow: z.record(z.string(), z.unknown(), { error: () => "'allow' must be an object when present" }).optional(),
    deny: z.record(z.string(), z.unknown(), { error: () => "'deny' must be an object (the host's decision shape)" }),
    reason_key: nonEmptyStr(),
  }, { error: objectError('gate (protocol=pre_tool)') }),
  z.strictObject({
    protocol: z.literal('event_guards'),
    allow: z.record(z.string(), z.unknown(), { error: () => "must be an object (the host's decision shape)" }),
    deny: z.record(z.string(), z.unknown(), { error: () => "must be an object (the host's decision shape)" }),
    user_key: nonEmptyStr(),
    agent_key: nonEmptyStr(),
  }, { error: objectError('gate (protocol=event_guards)') }),
], { error: discriminantError('protocol', ['event_guards', 'pre_tool']) });

/** The validated, immutable form of one `src/ecosystems/<name>.json`. */
export interface EcosystemDescriptor {
  readonly name: string;
  readonly vars: Readonly<Record<string, string>>;
  readonly models: Readonly<Record<string, string | null>>;
  readonly smoke: Readonly<Record<string, unknown>>;
  readonly dispatch: string;
  readonly roles: Readonly<Record<string, RoleSpec>>;
  readonly routes: readonly Route[];
  readonly artifacts: readonly Artifact[];
  readonly guard: readonly string[];
  readonly gate: Readonly<Record<string, unknown>> | null;
  readonly templates: readonly Template[];
}

const MODEL_TIERS = ['high', 'low', 'medium'] as const;

const ModelsSchema = z.partialRecord(
  oneOf(['high', 'medium', 'low']),
  z.string({ error: (issue) => `must be a string or null, got ${pyReprValue(issue.input)}` }).nullable(),
  {
    // A blind, code-blind `error` here would swallow EVERY issue this schema can produce under the
    // SAME "must be a non-empty object" text, including a wrong TIER NAME (code 'invalid_key') —
    // caught by review: `models: {high: null, turbo: 'x'}` was reporting "models.turbo: 'models'
    // must be a non-empty object" instead of naming the allowed tiers. Only 'invalid_type' (the
    // "not an object at all" case) gets this message; 'invalid_key' gets its own, using the same
    // pyReprValue-formatted style as every other enum-membership message in this file rather than
    // the key schema's own generic-enum wording (which `undefined` here would otherwise expose).
    error: (issue) => {
      if (issue.code === 'invalid_type') return "'models' must be a non-empty object";
      if (issue.code === 'invalid_key') {
        const path = issue.path ?? [];
        const badKey = path[path.length - 1];
        return `must be one of ${pyReprValue(MODEL_TIERS)}, got ${pyReprValue(badKey)}`;
      }
      // Structurally unreachable: `z.partialRecord()`'s own record-level check can only ever
      // produce 'invalid_type' or 'invalid_key' at this record's own path — same reasoning as
      // objectError's identical fallback above.
      return undefined;
    },
  },
).refine((m) => Object.keys(m).length > 0, { error: () => "'models' must be a non-empty object" });

const SmokeSchema = z.strictObject({
  cli: nonEmptyStr(),
  test: nonEmptyStr(),
  // npm_package/npm_version/install are ALLOWED keys with no type validation of their own in the
  // Python original (`_SMOKE_KEYS` only names them; nothing checks their shape) — `install` in
  // particular carries an OBJECT for some ecosystems (`{method, url, flags}`), not a string, so
  // z.unknown() here is deliberate, not an oversight. Only `cli`/`test`/`expect` are actually typed.
  npm_package: z.unknown().optional(),
  npm_version: z.unknown().optional(),
  install: z.unknown().optional(),
  expect: z.strictObject({
    version_cmd: z.array(nonEmptyStr(), { error: () => "'version_cmd' must be a non-empty command list" })
      .min(1, { error: () => "'version_cmd' must be a non-empty command list" }),
  }, { error: objectError("smoke 'expect'") }).optional(),
}, { error: objectError("'smoke'") });

const GUARD_ENTRY = nonEmptyStr().check((ctx) => {
  if (ctx.value.includes('/')) {
    ctx.issues.push({ code: 'custom', input: ctx.value, message: `entries are module filenames (no '/'), got ${pyRepr(ctx.value)}` });
  }
});

const DescriptorSchema = z.strictObject({
  schema: z.literal(1, { error: (issue) => `must be 1, got ${pyReprValue(issue.input)}` }),
  name: z.string({ error: (issue) => `must be a string, got ${pyReprValue(issue.input)}` }),
  vars: z.record(
    z.string(),
    z.string({ error: (issue) => `must be a string, got ${pyReprValue(issue.input)}` }),
    { error: () => "'vars' must be a non-empty object" },
  ).refine((v) => Object.keys(v).length > 0, { error: () => "'vars' must be a non-empty object" }),
  models: ModelsSchema,
  smoke: SmokeSchema,
  dispatch: oneOf(['frontmatter', 'path']),
  roles: z.strictObject({
    agent: RoleSchema, command: RoleSchema, persona: RoleSchema, default: RoleSchema,
  }, { error: objectError("'roles'") }),
  // UNLIKE artifacts/guard/templates below, `routes` is a REQUIRED top-level key in the Python
  // original (`_check_keys`' required-key loop names schema/name/vars/models/smoke/dispatch/roles/
  // routes, and only those eight) — caught by review: an earlier draft of this schema gave routes
  // the SAME `.default([])` treatment as the three genuinely-optional array sections, so a
  // descriptor omitting 'routes' entirely was silently ACCEPTED here while Python correctly rejects
  // it with "missing required key 'routes'". No `.default()`: an absent key must fail the same way
  // a wrong-type one does, not fall through to an empty list.
  routes: z.array(RouteSchema, { error: () => "'routes' must be a list" }),
  artifacts: z.array(ArtifactSchema, { error: () => "'artifacts' must be a list" }).default([]),
  guard: z.array(GUARD_ENTRY, { error: () => "'guard' must be a list" }).default([]),
  // UNLIKE the OUTPUT type (`gate: ... | null`, coalesced below), the INPUT schema must not be
  // `.nullable()`: Python's `gate=_parse_gate(name, raw["gate"]) if "gate" in raw else None` only
  // treats an ABSENT key as None — an explicit `"gate": null` still reaches `_parse_gate`, which
  // rejects it (`isinstance(None, dict)` is False). A stray `.nullable()` here (the one place this
  // schema had it, unlike the plain `.default([])` on the sibling optional sections above) made an
  // explicit null silently equivalent to omitting the key — caught by review, no test had covered
  // `gate: null` to catch it beforehand.
  gate: GateSchema.optional(),
  templates: z.array(TemplateSchema, { error: () => "'templates' must be a list" }).default([]),
}, {
  error: (issue) => {
    if (issue.code === 'unrecognized_keys') {
      const keys = (issue as { keys?: string[] }).keys ?? [];
      return `descriptor has unknown key(s) ${pyReprValue([...keys].sort())}`;
    }
    // Restores commit 4's int-vs-float distinction (Number.isInteger), which the earlier draft of
    // this schema dropped under the mistaken assumption that it was "moot" because Zod's OWN
    // default `received` field doesn't have it — but this callback constructs its own message from
    // the real `issue.input` value directly, so nothing stops it from checking Number.isInteger
    // itself, same as commit 4 did. Only the genuinely unavoidable case remains a divergence:
    // JSON.parse('5.0') and JSON.parse('5') are both the identical JS number 5, so an
    // integer-VALUED float is still indistinguishable from a true int once JSON.parse has run.
    const typeName = issue.input === undefined ? 'undefined' : issue.input === null ? 'NoneType'
      : Array.isArray(issue.input) ? 'list' : typeof issue.input === 'string' ? 'str'
        : typeof issue.input === 'boolean' ? 'bool'
          : typeof issue.input === 'number' ? (Number.isInteger(issue.input) ? 'int' : 'float') : typeof issue.input;
    return `descriptor must be a JSON object, got ${typeName}`;
  },
});

/** Validate `raw` (a decoded `<name>.json`) against the closed vocabulary; return the shape. */
export function parseDescriptor(descriptorName: string, raw: unknown): EcosystemDescriptor {
  const result = DescriptorSchema.safeParse(raw);
  if (!result.success) throw new DescriptorError(formatError(descriptorName, result.error));
  if (result.data.name !== descriptorName) {
    throw new DescriptorError(
      `ecosystem descriptor ${pyRepr(descriptorName)}: 'name' must equal the filename stem, got ${pyReprValue(result.data.name)}`,
    );
  }
  return {
    name: descriptorName,
    vars: result.data.vars,
    // Cast is safe: partialRecord only OMITS keys that weren't present, it never stores an
    // explicit `undefined` value for a present one — TS's Partial<Record<...>> typing is just
    // conservative about a hypothetical `obj.foo` access on an absent key.
    models: result.data.models as Record<string, string | null>,
    smoke: result.data.smoke,
    dispatch: result.data.dispatch,
    roles: result.data.roles,
    routes: result.data.routes,
    artifacts: result.data.artifacts,
    guard: result.data.guard,
    gate: (result.data.gate ?? null) as Readonly<Record<string, unknown>> | null,
    templates: result.data.templates,
  };
}

// ── Filesystem boundary ─────────────────────────────────────────────────────

const REPO_ROOT = join(import.meta.dirname, '..', '..');
// Exported (unlike REPO_ROOT) because genExtras.mts needs the SAME default `distFiles`/`discover`
// use, for reading a template's own `.src` sibling file directly — matching Python's
// `from scripts.build.descriptor import ECOSYSTEMS_DIR` import in `genextras.py`.
export const ECOSYSTEMS_DIR = join(REPO_ROOT, 'src', 'ecosystems');

/** Load and validate one descriptor file (the filename stem is the ecosystem name). */
export function load(path: string): EcosystemDescriptor {
  const stem = (path.split('/').pop() ?? path).replace(/\.json$/, '');
  return parseDescriptor(stem, JSON.parse(readFileSync(path, 'utf-8')));
}

/**
 * Enforce the directory's definitive schema: every non-descriptor file is `<known-eco>.dist.<dest>`
 * (shipped byte-identically) or `<known-eco>.template.<dest>` (a text template the descriptor
 * renders), with a flat, non-empty dest. A stray file, an unknown ecosystem prefix, or a nested
 * dest fails LOUDLY — nothing in this directory is ever silently ignored. (Hidden dotfiles are the
 * one tolerated exception.)
 */
function validateLayout(root: string, names: ReadonlySet<string>): void {
  const entries = readdirSync(root).sort();
  for (const entryName of entries) {
    const path = join(root, entryName);
    if (!statSync(path).isFile() || entryName.endsWith('.json') || entryName.startsWith('.')) continue;
    let matched = false;
    for (const marker of [DIST_MARKER, TEMPLATE_MARKER]) {
      const at = entryName.indexOf(marker);
      if (at === -1) continue;
      const eco = entryName.slice(0, at);
      const dest = entryName.slice(at + marker.length);
      if (names.has(eco) && dest !== '') { matched = true; break; }
    }
    if (!matched) {
      throw new DescriptorError(
        `src/ecosystems/${entryName}: every sibling file must be named ` +
          `'<ecosystem>${DIST_MARKER}<dest>' or '<ecosystem>${TEMPLATE_MARKER}<dest>' ` +
          `for a known ecosystem ${pyReprValue([...names].sort())}`,
      );
    }
  }
}

/**
 * The shipped sibling files for ecosystem `name`: `{destFilename: sourcePath}`, derived purely from
 * the filename schema (`<name>.dist.<dest>` → plugin-root `<dest>`) — the deterministic
 * input→output contract the build and its tests both read.
 */
export function distFiles(name: string, root: string = ECOSYSTEMS_DIR): Record<string, string> {
  const prefix = name + DIST_MARKER;
  const out: Record<string, string> = {};
  for (const entryName of readdirSync(root).sort()) {
    if (!entryName.startsWith(prefix)) continue;
    const path = join(root, entryName);
    if (!statSync(path).isFile()) continue;
    out[entryName.slice(prefix.length)] = path;
  }
  return out;
}

const CACHE = new Map<string, Readonly<Record<string, EcosystemDescriptor>>>();

/**
 * All descriptors under `root`, keyed by name — cached per root (the build reads many times;
 * descriptors are immutable within a run). Validates the whole directory layout, so a malformed
 * sibling file fails the FIRST build step, not a late copy.
 */
export function discover(root: string = ECOSYSTEMS_DIR): Readonly<Record<string, EcosystemDescriptor>> {
  const cached = CACHE.get(root);
  if (cached !== undefined) return cached;
  const found: Record<string, EcosystemDescriptor> = {};
  for (const entryName of readdirSync(root).sort()) {
    if (!entryName.endsWith('.json')) continue;
    const path = join(root, entryName);
    if (!statSync(path).isFile()) continue;
    const descriptor = load(path);
    found[descriptor.name] = descriptor;
  }
  validateLayout(root, new Set(Object.keys(found)));
  CACHE.set(root, found);
  return found;
}

/**
 * The one authoritative ecosystem list (sorted) — the descriptor files ARE the registry, so the
 * CLI target set and the CI smoke matrix derive from here; there is no separate registry to drift.
 */
export function names(root: string = ECOSYSTEMS_DIR): string[] {
  return Object.keys(discover(root)).sort();
}
