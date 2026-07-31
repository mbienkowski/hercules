/**
 * Ecosystem descriptors — the ONE per-ecosystem file, loaded and validated (closed vocabulary).
 *
 * An ecosystem is described entirely by `ecosystems/<name>.json`: token `vars`, `models` tiers, the
 * `smoke` install matrix entry, per-role output shapes (`roles`), destination `routes`, inline JSON
 * `artifacts`, shared-`guard` modules, write-`gate` params, and rendered `templates`. The filename is
 * the registry key and discovery is a glob, so a new ecosystem is one new JSON file, never new code.
 *
 * The DIRECTORY has a definitive schema too, validated on discovery: every file is a `<name>.json`
 * descriptor or a `<name>.dist.<dest>` / `<name>.template.<dest>` sibling, so the input→output
 * mapping is a pure function of the name. A stray file, an unknown ecosystem prefix, or a nested
 * dest fails loudly — nothing in this directory is ever silently ignored.
 *
 * The vocabulary is CLOSED: a descriptor selects named, mutation-covered behaviours and supplies
 * operands only. A Zod schema enforces that — five `z.discriminatedUnion()`s (field `from`, role
 * `mode`, route `kind`, gate `protocol`, template-value `from`) over `z.strictObject` variants, whose
 * own unknown-key rejection is the "no unknown keys" rule. Every schema node carries a custom `error`
 * callback, so a thrown {@link DescriptorError} names the offending key, its dot/bracket path
 * (`roles.agent.fields[2].value: …`) and the allowed set — and reports ALL failing fields at once,
 * semicolon-separated, because Zod validates the whole shape rather than failing fast.
 *
 * This is the ONLY module importing `zod`; every other module consumes the plain
 * `EcosystemDescriptor`/`RoleSpec`/etc. interfaces below, inferred from these schemas but exported as
 * ordinary TypeScript types. Zod validates the parsed JSON shape only — the filesystem functions
 * (`load`/`discover`/`distFiles`/`names`/`validateLayout`) own the directory layout.
 *
 * One irreducible quirk of decoded JSON: JavaScript has a single numeric type, so `JSON.parse('5.0')`
 * and `JSON.parse('5')` are the same value and an integer-valued float reads as `integer` in a
 * `got <type>` message. A plain `5.5` still correctly reports `got number`.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { z } from 'zod';

import { show } from './show.mjs';

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
    .map((segment, i) => {
      if (typeof segment === 'number') return `[${segment}]`; // array index -> bracket
      if (i === 0) return String(segment); // first key -> bare, no leading dot
      return `.${String(segment)}`; // later key -> dot-prefixed
    })
    .join('');
}

/** Every Zod issue's own `error` callback supplies the "what's wrong" half; this supplies "where". */
function formatIssue(issue: z.core.$ZodIssue): string {
  const where = formatPath(issue.path);
  return where ? `${where}: ${issue.message}` : issue.message;
}

/**
 * `DescriptorError`'s message for a whole failed parse: every issue Zod collected, not just the
 * first, so a descriptor with several simultaneous problems reports all of them at once.
 */
function formatError(descriptorName: string, error: z.core.$ZodError): string {
  const parts = error.issues.map(formatIssue);
  return `ecosystem descriptor ${show(descriptorName)}: ${parts.join('; ')}`;
}

/**
 * The JSON-Schema type name for a decoded-JSON value, for `got <type>` error strings.
 *
 * Uses JSON Schema's own vocabulary (`null`/`array`/`string`/`boolean`/`integer`/`number`) rather
 * than JS `typeof` — `typeof null` and `typeof []` are both `'object'`, so null and arrays MUST be
 * matched first. The number branch splits `integer` vs `number` via `Number.isInteger`, which keeps
 * a real validation distinction; the one unavoidable quirk is that `JSON.parse('5.0')` and
 * `JSON.parse('5')` are the identical JS number `5`, so an integer-valued float reads as `integer`.
 */
function jsonType(input: unknown): string {
  if (input === undefined) return 'undefined';
  if (input === null) return 'null';
  if (Array.isArray(input)) return 'array';
  if (typeof input === 'string') return 'string';
  if (typeof input === 'boolean') return 'boolean';
  if (typeof input === 'number') return Number.isInteger(input) ? 'integer' : 'number';
  return typeof input; // object/function/symbol/bigint — the raw JS typeof
}

/** A required, non-empty string leaf — the single most common check in this schema. */
function nonEmptyStr(): z.ZodString {
  return z.string({ error: (issue) => `must be a non-empty string, got ${show(issue.input)}` })
    .min(1, { error: (issue) => `must be a non-empty string, got ${show(issue.input)}` });
}

/** A dest/src path inside the tree: relative, no parent escapes. */
function relPath() {
  return nonEmptyStr().check((ctx) => {
    const path = ctx.value;
    if (path.startsWith('/') || path.split('/').includes('..')) {
      ctx.issues.push({
        code: 'custom',
        input: path,
        message: `must be a relative path without '..', got ${show(path)}`,
      });
    }
  });
}

function oneOf<T extends readonly [string, ...string[]]>(values: T): z.ZodEnum<{ [K in T[number]]: K }> {
  const sorted = [...values].sort();
  // z.enum wants an object whose keys ARE its values (`{ exact: 'exact', omit: 'omit' }`), so turn
  // the string array into that identity map. The `{ [K in T[number]]: K }` type just says "an object
  // whose keys equal their own values", which is what lets Zod infer the enum's literal union.
  const enumShape = Object.fromEntries(values.map((v) => [v, v])) as { [K in T[number]]: K };
  return z.enum(enumShape, { error: (issue) => `must be one of ${show(sorted)}, got ${show(issue.input)}` });
}

/**
 * `z.strictObject()`'s object-level `error` fires for BOTH "not an object at all" (`invalid_type`)
 * and "has an unrecognised key" (`unrecognized_keys`), which a plain string param cannot
 * distinguish — so every `strictObject` wanting a custom "must be an object" message routes through
 * here to keep its unknown-key message sensible too.
 */
function objectError(label: string): (issue: { code: string; input?: unknown; keys?: string[] }) => string | undefined {
  return (issue) => {
    if (issue.code === 'invalid_type') return `${label} must be an object, got ${show(issue.input)}`;
    if (issue.code === 'unrecognized_keys') {
      return `${label} has unknown key(s) ${show([...(issue.keys ?? [])].sort())}`;
    }
    // Structurally unreachable, not merely untested: `z.strictObject()`'s OWN object-level check can
    // only produce 'invalid_type' or 'unrecognized_keys' at this object's own path; every other issue
    // code belongs to a field or wrapper schema and reports through its own callback. Kept so the
    // return type stays honest — Zod's `error` callback signature always permits `undefined`.
    return undefined;
  };
}

/**
 * `z.discriminatedUnion()`'s top-level `error` carries the same ambiguity `objectError` resolves:
 * `invalid_union` means the input IS an object whose discriminant matches no variant (read the real
 * value off `issue.input[field]`), while `invalid_type` means it isn't an object at all — there that
 * lookup is always `undefined`, so a code-blind version reports "got null" for `routes: ['oops']`
 * instead of naming the string actually rejected. Shared by all five unions in this file.
 */
function discriminantError(field: string, values: readonly string[]) {
  const sorted = [...values].sort();
  return (issue: { code: string; input?: unknown }) => {
    const got = issue.code === 'invalid_type'
      ? issue.input
      : (issue.input as Record<string, unknown> | undefined)?.[field];
    return `'${field}' must be one of ${show(sorted)}, got ${show(got)}`;
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
      // `flag_if_name_in` omits its key entirely when the name doesn't match — for the mandatory
      // single `description` that means it renders literally as `description = "undefined"`. Its
      // one value must come from a generator that always emits.
      if (role.fields.some((f) => f.source === 'flag_if_name_in')) {
        ctx.issues.push({ code: 'custom', input: role, message: "toml_command's 'description' must use a generator that always emits (not flag_if_name_in)" });
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

// `key_prefix` defaults to `''` structurally: only `role_entries_js` reads an explicit one from raw
// input, so the other kinds always carry the empty default.
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
        message: `'src' must be a flat '<eco>${TEMPLATE_MARKER}<dest>' sibling, got ${show(ctx.value)}`,
      });
    }
  }),
  dest: relPath(),
  values: z.record(
    z.string().regex(PLACEHOLDER, { error: (issue) => `placeholder ${show(String(issue.input))} must match __UPPER_SNAKE__` }),
    TemplateValueSchema,
    {
      // Code-aware, not blind: only 'invalid_type' ("values isn't an object at all") gets the generic
      // text. A MALFORMED PLACEHOLDER arrives as 'invalid_key', and `z.record()`'s key-schema message
      // never bubbles up on its own — it stays the "Invalid key in record" wrapper — so the nested
      // issue's own message has to be read out and returned explicitly.
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

/** One write-gate configuration — returned as-is, never transformed. */
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

/** How a source file's role is determined — the same closed set the schema validates. */
const DISPATCH_MODES = ['frontmatter', 'path'] as const;
export type Dispatch = (typeof DISPATCH_MODES)[number];

/** The validated, immutable form of one `ecosystems/<name>.json`. */
export interface EcosystemDescriptor {
  readonly name: string;
  readonly vars: Readonly<Record<string, string>>;
  readonly models: Readonly<Record<string, string | null>>;
  // `smoke` and `gate` mirror their Zod schemas rather than restating them as bare key/value bags:
  // the schema is the single source of truth, so a consumer reads `smoke.cli` as a checked string
  // instead of casting its way out of `Record<string, unknown>`.
  readonly smoke: z.infer<typeof SmokeSchema>;
  readonly dispatch: Dispatch;
  readonly roles: Readonly<Record<string, RoleSpec>>;
  readonly routes: readonly Route[];
  readonly artifacts: readonly Artifact[];
  readonly guard: readonly string[];
  /** `tools/` — programs a COMMAND invokes deliberately, unlike `guard`, which the host fires on an
   * event. Separate because the two carry opposite failure postures: a guard fails open, a tool
   * that deletes fails closed. */
  readonly tools: readonly string[];
  readonly gate: z.infer<typeof GateSchema> | null;
  readonly templates: readonly Template[];
}

const MODEL_TIERS = ['high', 'low', 'medium'] as const;

const ModelsSchema = z.partialRecord(
  oneOf(['high', 'medium', 'low']),
  z.string({ error: (issue) => `must be a string or null, got ${show(issue.input)}` }).nullable(),
  {
    // Code-aware, not blind: only 'invalid_type' (not an object at all) gets the "must be a non-empty
    // object" text. A wrong TIER NAME arrives as 'invalid_key' and must name the allowed tiers
    // instead, in the same show()-formatted style as every other enum message in this file.
    error: (issue) => {
      if (issue.code === 'invalid_type') return "'models' must be a non-empty object";
      if (issue.code === 'invalid_key') {
        const path = issue.path ?? [];
        const badKey = path[path.length - 1];
        return `must be one of ${show(MODEL_TIERS)}, got ${show(badKey)}`;
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
  // npm_package/npm_version/install are allowed but untyped: `install` carries an OBJECT for some
  // ecosystems (`{method, url, flags}`), not a string, so `z.unknown()` is deliberate. Only
  // `cli`/`test`/`expect` are actually typed.
  npm_package: z.unknown().optional(),
  npm_version: z.unknown().optional(),
  install: z.unknown().optional(),
  expect: z.strictObject({
    version_cmd: z.array(nonEmptyStr(), { error: () => "'version_cmd' must be a non-empty command list" })
      .min(1, { error: () => "'version_cmd' must be a non-empty command list" }),
  }, { error: objectError("smoke 'expect'") }).optional(),
}, { error: objectError("'smoke'") });

const MODULE_ENTRY = nonEmptyStr().check((ctx) => {
  if (ctx.value.includes('/')) {
    ctx.issues.push({ code: 'custom', input: ctx.value, message: `entries are module filenames (no '/'), got ${show(ctx.value)}` });
  }
});

const DescriptorSchema = z.strictObject({
  schema: z.literal(1, { error: (issue) => `must be 1, got ${show(issue.input)}` }),
  name: z.string({ error: (issue) => `must be a string, got ${show(issue.input)}` }),
  vars: z.record(
    z.string(),
    z.string({ error: (issue) => `must be a string, got ${show(issue.input)}` }),
    { error: () => "'vars' must be a non-empty object" },
  ).refine((v) => Object.keys(v).length > 0, { error: () => "'vars' must be a non-empty object" }),
  models: ModelsSchema,
  smoke: SmokeSchema,
  dispatch: oneOf(DISPATCH_MODES),
  roles: z.strictObject({
    agent: RoleSchema, command: RoleSchema, persona: RoleSchema, default: RoleSchema,
  }, { error: objectError("'roles'") }),
  // No `.default([])`, unlike the genuinely optional array sections below: `routes` is a REQUIRED
  // top-level key, so an absent one must fail exactly as a wrong-typed one does rather than falling
  // through to an empty list.
  routes: z.array(RouteSchema, { error: () => "'routes' must be a list" }),
  artifacts: z.array(ArtifactSchema, { error: () => "'artifacts' must be a list" }).default([]),
  guard: z.array(MODULE_ENTRY, { error: () => "'guard' must be a list" }).default([]),
  tools: z.array(MODULE_ENTRY, { error: () => "'tools' must be a list" }).default([]),
  // `.optional()`, never `.nullable()` — unlike the OUTPUT type (`gate: … | null`, coalesced below):
  // only an ABSENT key means "no gate". An explicit `"gate": null` is a malformed descriptor and must
  // be rejected, not silently treated as omission.
  gate: GateSchema.optional(),
  templates: z.array(TemplateSchema, { error: () => "'templates' must be a list" }).default([]),
}, {
  error: (issue) => {
    if (issue.code === 'unrecognized_keys') {
      const keys = (issue as { keys?: string[] }).keys ?? [];
      return `descriptor has unknown key(s) ${show([...keys].sort())}`;
    }
    // Constructs its own message from the real `issue.input` value so it can keep the
    // integer-vs-number distinction (see jsonType), which Zod's own default `received` field lacks.
    return `descriptor must be a JSON object, got ${jsonType(issue.input)}`;
  },
});

/** Validate `raw` (a decoded `<name>.json`) against the closed vocabulary; return the shape. */
export function parseDescriptor(descriptorName: string, raw: unknown): EcosystemDescriptor {
  const result = DescriptorSchema.safeParse(raw);
  if (!result.success) throw new DescriptorError(formatError(descriptorName, result.error));
  if (result.data.name !== descriptorName) {
    throw new DescriptorError(
      `ecosystem descriptor ${show(descriptorName)}: 'name' must equal the filename stem, got ${show(result.data.name)}`,
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
    tools: result.data.tools,
    gate: result.data.gate ?? null,
    templates: result.data.templates,
  };
}

// ── Filesystem boundary ─────────────────────────────────────────────────────

// The process working directory, not an `import.meta.dirname` relative hop: this module runs BOTH
// as source (Vitest, under src/builder/) and as compiled output (`.ts-out/builder/descriptor.mjs`),
// which sit at different depths, so a fixed relative-hop count cannot be correct in both. Every real
// entry point (the Makefile's targets, the npm scripts, Stryker's sandboxed runner — see
// src/commons/support/repo.ts's own repoRoot for the fuller reasoning) already runs from the repo
// root, so `process.cwd()` resolves correctly in both execution modes without tracking directory depth.
const REPO_ROOT = process.cwd();
// Exported (unlike REPO_ROOT) so genExtras.mts resolves a template's own `.src` sibling against the
// SAME default directory `discover`/`distFiles` use.
export const TARGETS_DIR = join(REPO_ROOT, 'src', 'targets');

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
        `ecosystems/${entryName}: every sibling file must be named ` +
          `'<ecosystem>${DIST_MARKER}<dest>' or '<ecosystem>${TEMPLATE_MARKER}<dest>' ` +
          `for a known ecosystem ${show([...names].sort())}`,
      );
    }
  }
}

/**
 * The shipped sibling files for ecosystem `name`: `{destFilename: sourcePath}`, derived purely from
 * the filename schema (`<name>.dist.<dest>` → plugin-root `<dest>`) — the deterministic
 * input→output contract the build and its tests both read.
 */
export function distFiles(name: string, root: string = TARGETS_DIR): Record<string, string> {
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
export function discover(root: string = TARGETS_DIR): Readonly<Record<string, EcosystemDescriptor>> {
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
export function names(root: string = TARGETS_DIR): string[] {
  return Object.keys(discover(root)).sort();
}
