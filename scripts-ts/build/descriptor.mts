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
 * ── As-is port (commit 4 of the migration) ──────────────────────────────────
 * This is a structural 1:1 port of scripts/build/descriptor.py: the same closed vocabulary
 * constants, the same hand-written validation control flow, no Zod. Error messages are
 * byte-identical to the Python original via {@link pyRepr}/{@link pyReprValue}, including the
 * EXACT ORDER in which sections are validated when a descriptor has more than one problem at once
 * — guard is checked before roles/routes/artifacts; gate is checked after artifacts; templates are
 * checked last. That ordering is a real, load-bearing part of the contract (which error a
 * multiply-broken descriptor reports), not an accident of how the Python was written, so it is
 * preserved rather than reorganised. Zod replaces this in the very next commit; the parity harness
 * pins these messages so that swap is provably lossless on the failure paths that matter.
 *
 * Accepted, documented divergences:
 *
 * - Python treats `bool` as an `int` subclass, so `True == 1` makes `schema: true` ambiguously
 *   pass the `!= 1` check there. This port does not replicate that — `schema` must be exactly the
 *   JSON number 1. No legitimate descriptor depends on the distinction, so it is a deliberate
 *   non-goal rather than a port gap; no parity fixture exercises `schema: true` for this reason.
 *
 * - Every `x not in <enum>` check backed by a Python SET (`dispatch`, role `mode`, route `kind`,
 *   gate `protocol`, field `from`, template-value `from`) CRASHES with an unhandled
 *   `TypeError: unhashable type` if the offending value is a list or a dict, because Python must
 *   hash a value before it can test set membership. The checks backed by a TUPLE (model tier,
 *   `role_entries_js`'s `role`) do not share this quirk — tuple membership uses equality, not
 *   hashing. This port's `Set.has()` never crashes regardless of input type, which is strictly
 *   more robust, not a regression, and Zod (the very next commit) will not replicate the crash
 *   either. Parity fixtures for a list/dict-shaped enum value exercise the TUPLE-backed checks,
 *   which is the same repr-formatting code path without the crash.
 *
 * - `load`/`discover` guard the `*.json` glob with `statSync(path).isFile()` before reading it.
 *   Python's own `path.read_text()` / `Path.glob("*.json")` carry no such guard here: a DIRECTORY
 *   literally named `<name>.json` makes Python crash with an unhandled `IsADirectoryError`, while
 *   this port silently skips it — refusing to replicate a crash is strictly more robust, not a
 *   regression. NOTE this divergence is narrower than it might look: `validateLayout`'s own
 *   sibling-file walk and `distFiles` BOTH already carry an equivalent `is_file()` guard on the
 *   Python side too (`descriptor.py` lines 450 and 470), so a directory shaped like
 *   `<name>.dist.<dest>` is silently skipped by BOTH engines — that is faithful parity, not a
 *   divergence, despite an earlier draft of this comment claiming otherwise.
 *
 * - `load()`'s `JSON.parse` rejects the bare `NaN`/`Infinity`/`-Infinity` tokens that Python's
 *   `json.loads` accepts by default (a Python-specific, spec-violating extension — those tokens are
 *   not valid JSON per RFC 8259). A descriptor file containing one of them crashes this port with
 *   an uncaught `SyntaxError` before `parseDescriptor` ever runs, where Python would parse it into
 *   `float('nan')`/`float('inf')` and then reject it through the normal, non-crashing type-check
 *   path. This is the one divergence in this file where TS is LESS forgiving than Python, not
 *   more — accepted because no legitimate descriptor ever contains a non-standard JSON token, and
 *   because rejecting non-standard JSON outright is arguably more correct than silently accepting
 *   it. Not parity-fixture-able (the Python and TS outcomes are structurally different: a crash before
 *   validation runs at all vs. a normal `DescriptorError` afterwards), so `load()`'s own unit tests
 *   pin the TS-side behaviour directly instead.
 *
 * - `Object.entries()`/`Object.keys()` on a plain JS object reorder integer-like string keys (e.g.
 *   `"42"`) ahead of every other key, in ascending numeric order, regardless of the source JSON's
 *   actual key order — this is the JS object model's `[[OwnPropertyKeys]]` behaviour, not a bug in
 *   any one call site. Python's `dict` has no such special case; `dict.items()` always preserves
 *   the JSON source's literal key order. Two sites read multi-key raw JSON objects and iterate them
 *   to validate each entry — `vars` (`for (const [key, value] of Object.entries(varsRaw))`) and a
 *   `pre_tool` gate's `tools` (`for (const [hostTool, canonical] of Object.entries(tools))`) — so a
 *   descriptor with MULTIPLE invalid entries in either section, where at least one key looks like a
 *   non-negative integer, can report a DIFFERENT offending key than Python does for the exact same
 *   input. A single invalid entry is unaffected (the message names whichever key is wrong either
 *   way); only the *which-one-first* choice under multiple simultaneous failures can diverge, and
 *   only for the specific edge case of an integer-shaped key colliding with a non-integer-shaped
 *   one in the same object. Accepted rather than fixed: recovering true source order regardless of
 *   key shape needs a Map-producing JSON parse (or a hand-rolled tokenizer) rather than `JSON.parse`
 *   into a plain object, which is a materially bigger change than this as-is port's mandate — and
 *   Zod (the very next commit) does not change this either, since it validates the same parsed
 *   plain-object shape. `descriptor.spec.ts` pins the CURRENT (Python-diverging) TS ordering
 *   directly so this doesn't silently drift further un-noticed.
 *
 * - The hand-rolled type-name detector in `parseDescriptor`'s not-an-object branch cannot tell an
 *   integer-VALUED float apart from a true int: `JSON.parse('5.0')` and `JSON.parse('5')` both
 *   produce the identical JS number `5`, since JS has one numeric type — the literal's original
 *   float-ness is gone by the time this code ever sees it. Python's `json.loads` preserves it
 *   (`type(json.loads('5.0')).__name__ == 'float'`), so a descriptor file whose ENTIRE top-level
 *   content is an integer-valued float literal (e.g. bare `5.0`) is reported as `got int` here vs.
 *   `got float` in Python. Accepted as an extremely narrow edge case (a real descriptor is always a
 *   JSON object; this only bites a file that is a bare top-level number) rather than fixed, since a
 *   fix would need the same source-text-aware parsing as the key-reordering divergence above.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { pyRepr, pyReprValue } from './pyCompat.mjs';

const TOP_KEYS = new Set([
  'schema', 'name', 'vars', 'models', 'smoke', 'dispatch', 'roles',
  'routes', 'artifacts', 'guard', 'gate', 'templates',
]);
// Sibling filename markers: "<eco>.dist.<dest>" ships byte-identically at plugin-root <dest>;
// "<eco>.template.<dest>" is a text template the descriptor's `templates` section renders.
const DIST_MARKER = '.dist.';
const TEMPLATE_MARKER = '.template.';
// Computed-value kinds a template placeholder may use (closed; operands only).
const TEMPLATE_VALUE_KINDS: Readonly<Record<string, ReadonlySet<string>>> = {
  js_string: new Set(['from', 'value']),
  js_string_list: new Set(['from', 'values']),
  js_root_joins: new Set(['from', 'paths']),
  role_entries_js: new Set(['from', 'role', 'drop', 'body_key', 'key_prefix']),
};
const PLACEHOLDER = /^__[A-Z_]+__$/;
// The write-gate protocols the shared adapter implements — named by CAPABILITY, not by ecosystem.
const GATE_PROTOCOLS = new Set(['pre_tool', 'event_guards']);
const GATE_KEYS: Readonly<Record<string, ReadonlySet<string>>> = {
  pre_tool: new Set(['protocol', 'tools', 'path_keys', 'nested_keys', 'allow', 'deny', 'reason_key']),
  event_guards: new Set(['protocol', 'allow', 'deny', 'user_key', 'agent_key']),
};
const ROLE_NAMES = ['agent', 'command', 'persona', 'default'] as const;
const MODES = new Set(['preserve', 'fields', 'wrap', 'plain', 'toml_command']);
const BODY_POLICIES = new Set(['keep', 'lstrip_newlines', 'strip_newlines']);
const FIELD_FROMS = new Set(['frontmatter', 'stem', 'literal', 'primary_mode', 'flag_if_name_in']);
const ROUTE_KINDS = new Set(['exact', 'suffix_swap', 'omit']);
const DISPATCHES = new Set(['path', 'frontmatter']);
const MODEL_TIERS = new Set(['high', 'medium', 'low']);
const SMOKE_KEYS = new Set(['cli', 'test', 'npm_package', 'npm_version', 'install', 'expect']);
// Per-mode allowed role-spec keys — the schema's shape lives here, not in prose.
const ROLE_KEYS: Readonly<Record<string, ReadonlySet<string>>> = {
  preserve: new Set(['mode', 'resolve_model_tier', 'required']),
  fields: new Set(['mode', 'fields', 'body']),
  wrap: new Set(['mode', 'fields']),
  plain: new Set(['mode']),
  toml_command: new Set(['mode', 'fields', 'body']),
};
// Per-generator allowed field-spec keys.
const FIELD_KEYS: Readonly<Record<string, ReadonlySet<string>>> = {
  frontmatter: new Set(['key', 'from', 'field', 'render']),
  stem: new Set(['key', 'from']),
  literal: new Set(['key', 'from', 'value']),
  primary_mode: new Set(['key', 'from', 'primary']),
  flag_if_name_in: new Set(['key', 'from', 'names', 'value']),
};
const ROUTE_KEYS: Readonly<Record<string, ReadonlySet<string>>> = {
  exact: new Set(['kind', 'src', 'dest']),
  suffix_swap: new Set(['kind', 'prefix', 'from_suffix', 'to_suffix']),
  omit: new Set(['kind', 'src']),
};

export class DescriptorError extends Error {
  override readonly name = 'DescriptorError';
}

/**
 * Python's `dict.get(key, default)`: returns `default` only when `key` is ABSENT, never when it is
 * present with value `null`. The obvious `raw[key] ?? default` is NOT equivalent — `??` treats an
 * explicit `null` as nullish too, silently coercing it to the default instead of letting it reach
 * the isinstance/type check Python runs on it. That divergence is real, not theoretical: it was
 * caught by review, verified against a live `python3` run and the project's own parity harness for
 * `role.body`, `field.render`, `role.resolve_model_tier`, `role.required`, `artifact.versioned`,
 * `templateValue.drop`, `templateValue.key_prefix`, and `template.values` — an explicit `null` on
 * any of the first seven makes Python raise DescriptorError while `??` let it through silently.
 */
function pyGet<T>(raw: Record<string, unknown>, key: string, fallback: T): unknown {
  return key in raw ? raw[key] : fallback;
}

function fail(descriptorName: string, message: string): never {
  throw new DescriptorError(`ecosystem descriptor ${pyRepr(descriptorName)}: ${message}`);
}

/** Python's `isinstance(value, dict)`: a plain object, never an array or null. */
function isDict(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function checkKeys(
  descriptorName: string,
  what: string,
  obj: Record<string, unknown>,
  allowed: ReadonlySet<string>,
): void {
  const unknown = Object.keys(obj).filter((k) => !allowed.has(k)).sort();
  if (unknown.length > 0) {
    fail(
      descriptorName,
      `${what} has unknown key(s) ${pyReprValue(unknown)} — allowed: ${pyReprValue([...allowed].sort())}`,
    );
  }
}

function checkStr(descriptorName: string, what: string, value: unknown): string {
  if (typeof value !== 'string' || value === '') {
    fail(descriptorName, `${what} must be a non-empty string, got ${pyReprValue(value)}`);
  }
  return value;
}

/** A dest/src path inside the tree: relative, no parent escapes. */
function checkRelPath(descriptorName: string, what: string, value: unknown): string {
  const path = checkStr(descriptorName, what, value);
  if (path.startsWith('/') || path.split('/').includes('..')) {
    fail(descriptorName, `${what} must be a relative path without '..', got ${pyRepr(path)}`);
  }
  return path;
}

// ── Shapes ─────────────────────────────────────────────────────────────────

/** One emitted frontmatter field: its output `key` and the named generator producing it. */
export interface FieldSpec {
  readonly key: string;
  readonly source: string; // a FIELD_FROMS member ("from" in JSON)
  readonly field: string | null; // frontmatter: the source frontmatter key
  readonly render: boolean; // frontmatter: token-render the value
  readonly value: string | null; // literal / flag_if_name_in: the emitted value
  readonly primary: string | null; // primary_mode: the primary agent name
  readonly names: readonly string[]; // flag_if_name_in: names that receive the flag
}

/** How one role (agent/command/persona/default) serializes for this ecosystem. */
export interface RoleSpec {
  readonly mode: string; // a MODES member
  readonly fields: readonly FieldSpec[];
  readonly body: string; // a BODY_POLICIES member
  readonly resolveModelTier: boolean;
  readonly required: readonly string[];
}

/** One src→dest relocation rule (ordered, first match wins, identity fallback). */
export interface Route {
  readonly kind: string; // a ROUTE_KINDS member
  readonly src: string | null;
  readonly dest: string | null;
  readonly prefix: string | null;
  readonly fromSuffix: string | null;
  readonly toSuffix: string | null;
}

/** One inline-JSON file the build emits: `content` dumped canonically to `dest`. */
export interface Artifact {
  readonly dest: string;
  readonly content: Readonly<Record<string, unknown>>;
  readonly versioned: boolean;
}

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

/** One rendered template: a `<eco>.template.<dest>` sibling filled with computed values. */
export interface Template {
  readonly src: string;
  readonly dest: string;
  readonly values: Readonly<Record<string, TemplateValue>>;
}

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

// ── Per-shape parsers ──────────────────────────────────────────────────────

function parseField(descriptorName: string, raw: unknown): FieldSpec {
  if (!isDict(raw)) fail(descriptorName, `a field spec must be an object, got ${pyReprValue(raw)}`);
  const source = raw['from'];
  if (typeof source !== 'string' || !FIELD_FROMS.has(source)) {
    fail(descriptorName, `field 'from' must be one of ${pyReprValue([...FIELD_FROMS].sort())}, got ${pyReprValue(source)}`);
  }
  checkKeys(descriptorName, `field (from=${source})`, raw, FIELD_KEYS[source] as ReadonlySet<string>);
  const key = checkStr(descriptorName, "field 'key'", raw['key']);

  if (source === 'frontmatter') {
    const render = pyGet(raw, 'render', false);
    if (typeof render !== 'boolean') fail(descriptorName, "field 'render' must be a boolean");
    return {
      key, source, render,
      field: checkStr(descriptorName, "field 'field'", raw['field']),
      value: null, primary: null, names: [],
    };
  }
  if (source === 'literal') {
    return {
      key, source, field: null, render: false, primary: null, names: [],
      value: checkStr(descriptorName, "field 'value'", raw['value']),
    };
  }
  if (source === 'primary_mode') {
    return {
      key, source, field: null, render: false, value: null, names: [],
      primary: checkStr(descriptorName, "field 'primary'", raw['primary']),
    };
  }
  if (source === 'flag_if_name_in') {
    const names = raw['names'];
    if (!Array.isArray(names) || names.length === 0) {
      fail(descriptorName, "field 'names' must be a non-empty list");
    }
    return {
      key, source, field: null, render: false, primary: null,
      value: checkStr(descriptorName, "field 'value'", raw['value']),
      names: names.map((n) => checkStr(descriptorName, "field 'names' entry", n)),
    };
  }
  // stem
  return { key, source, field: null, render: false, value: null, primary: null, names: [] };
}

function parseRole(descriptorName: string, role: string, raw: unknown): RoleSpec {
  if (!isDict(raw)) fail(descriptorName, `role ${pyRepr(role)} must be an object, got ${pyReprValue(raw)}`);
  const mode = raw['mode'];
  if (typeof mode !== 'string' || !MODES.has(mode)) {
    fail(descriptorName, `role ${pyRepr(role)} 'mode' must be one of ${pyReprValue([...MODES].sort())}, got ${pyReprValue(mode)}`);
  }
  checkKeys(descriptorName, `role ${pyRepr(role)} (mode=${mode})`, raw, ROLE_KEYS[mode] as ReadonlySet<string>);

  const body = pyGet(raw, 'body', 'keep');
  if (typeof body !== 'string' || !BODY_POLICIES.has(body)) {
    fail(descriptorName, `role ${pyRepr(role)} 'body' must be one of ${pyReprValue([...BODY_POLICIES].sort())}, got ${pyReprValue(body)}`);
  }
  const fieldsRaw = raw['fields'] ?? [];
  if (mode === 'fields' || mode === 'wrap' || mode === 'toml_command') {
    if (!Array.isArray(fieldsRaw) || fieldsRaw.length === 0) {
      fail(descriptorName, `role ${pyRepr(role)} (mode=${mode}) requires a non-empty 'fields' list`);
    }
  }
  const fieldsArr: unknown[] = Array.isArray(fieldsRaw) ? fieldsRaw : [];
  const fields = fieldsArr.map((f) => parseField(descriptorName, f));
  if (mode === 'wrap' && fields.some((f) => f.source !== 'literal')) {
    fail(descriptorName, `role ${pyRepr(role)}: wrap-mode fields must all be literals (generated frontmatter)`);
  }
  if (mode === 'toml_command') {
    const keys = fields.map((f) => f.key);
    if (keys.length !== 1 || keys[0] !== 'description') {
      fail(descriptorName, `role ${pyRepr(role)}: toml_command emits exactly one field, 'description'`);
    }
  }
  const resolveModelTier = pyGet(raw, 'resolve_model_tier', false);
  if (typeof resolveModelTier !== 'boolean') {
    fail(descriptorName, `role ${pyRepr(role)} 'resolve_model_tier' must be a boolean`);
  }
  const requiredRaw = pyGet(raw, 'required', []);
  if (!Array.isArray(requiredRaw)) fail(descriptorName, `role ${pyRepr(role)} 'required' must be a list`);
  return {
    mode, fields, body, resolveModelTier,
    required: requiredRaw.map((r) => checkStr(descriptorName, "'required' entry", r)),
  };
}

function parseRoute(descriptorName: string, raw: unknown): Route {
  if (!isDict(raw)) fail(descriptorName, `a route must be an object, got ${pyReprValue(raw)}`);
  const kind = raw['kind'];
  if (typeof kind !== 'string' || !ROUTE_KINDS.has(kind)) {
    fail(descriptorName, `route 'kind' must be one of ${pyReprValue([...ROUTE_KINDS].sort())}, got ${pyReprValue(kind)}`);
  }
  checkKeys(descriptorName, `route (kind=${kind})`, raw, ROUTE_KEYS[kind] as ReadonlySet<string>);

  if (kind === 'exact') {
    return {
      kind, prefix: null, fromSuffix: null, toSuffix: null,
      src: checkRelPath(descriptorName, "route 'src'", raw['src']),
      dest: checkRelPath(descriptorName, "route 'dest'", raw['dest']),
    };
  }
  if (kind === 'omit') {
    return {
      kind, dest: null, prefix: null, fromSuffix: null, toSuffix: null,
      src: checkRelPath(descriptorName, "route 'src'", raw['src']),
    };
  }
  // suffix_swap builds its destination as `rel[:-len(from_suffix)] + to_suffix`; guard every
  // operand against a tree escape the SAME way exact-route dest is guarded, so a swapped
  // extension can never write outside the built plugin tree.
  return {
    kind, src: null, dest: null,
    prefix: checkRelPath(descriptorName, "route 'prefix'", raw['prefix']),
    fromSuffix: checkRelPath(descriptorName, "route 'from_suffix'", raw['from_suffix']),
    toSuffix: checkRelPath(descriptorName, "route 'to_suffix'", raw['to_suffix']),
  };
}

function parseArtifact(descriptorName: string, raw: unknown): Artifact {
  if (!isDict(raw)) fail(descriptorName, `an artifact must be an object, got ${pyReprValue(raw)}`);
  checkKeys(descriptorName, 'artifact', raw, new Set(['dest', 'content', 'versioned']));
  if (!isDict(raw['content'])) fail(descriptorName, "artifact 'content' must be a JSON object");
  const versioned = pyGet(raw, 'versioned', false);
  if (typeof versioned !== 'boolean') fail(descriptorName, "artifact 'versioned' must be a boolean");
  return {
    dest: checkRelPath(descriptorName, "artifact 'dest'", raw['dest']),
    content: raw['content'] as Record<string, unknown>,
    versioned,
  };
}

function parseGate(descriptorName: string, raw: unknown): Record<string, unknown> {
  if (!isDict(raw)) fail(descriptorName, `'gate' must be an object, got ${pyReprValue(raw)}`);
  const protocol = raw['protocol'];
  if (typeof protocol !== 'string' || !GATE_PROTOCOLS.has(protocol)) {
    fail(descriptorName, `gate 'protocol' must be one of ${pyReprValue([...GATE_PROTOCOLS].sort())}, got ${pyReprValue(protocol)}`);
  }
  checkKeys(descriptorName, `gate (protocol=${protocol})`, raw, GATE_KEYS[protocol] as ReadonlySet<string>);

  if (protocol === 'pre_tool') {
    const tools = raw['tools'];
    if (!isDict(tools) || Object.keys(tools).length === 0) {
      fail(descriptorName, "gate 'tools' must be a non-empty object mapping host tool → canonical tool");
    }
    for (const [hostTool, canonical] of Object.entries(tools)) {
      checkStr(descriptorName, `gate tools[${pyRepr(hostTool)}]`, canonical);
    }
    const pathKeys = raw['path_keys'];
    if (!Array.isArray(pathKeys) || pathKeys.length === 0) {
      fail(descriptorName, "gate 'path_keys' must be a non-empty list");
    }
    if (!isDict(raw['deny'])) fail(descriptorName, "gate 'deny' must be an object (the host's decision shape)");
    if ('allow' in raw && !isDict(raw['allow'])) {
      fail(descriptorName, "gate 'allow' must be an object when present");
    }
    checkStr(descriptorName, "gate 'reason_key'", raw['reason_key']);
    if ('nested_keys' in raw && !Array.isArray(raw['nested_keys'])) {
      fail(descriptorName, "gate 'nested_keys' must be a list");
    }
  }
  if (protocol === 'event_guards') {
    for (const key of ['allow', 'deny']) {
      if (!isDict(raw[key])) fail(descriptorName, `gate ${pyRepr(key)} must be an object (the host's decision shape)`);
    }
    checkStr(descriptorName, "gate 'user_key'", raw['user_key']);
    checkStr(descriptorName, "gate 'agent_key'", raw['agent_key']);
  }
  return { ...raw };
}

function parseTemplateValue(descriptorName: string, placeholder: string, raw: unknown): TemplateValue {
  if (!isDict(raw)) {
    fail(descriptorName, `template value ${pyRepr(placeholder)} must be an object, got ${pyReprValue(raw)}`);
  }
  const kind = raw['from'];
  if (typeof kind !== 'string' || !Object.hasOwn(TEMPLATE_VALUE_KINDS, kind)) {
    fail(
      descriptorName,
      `template value ${pyRepr(placeholder)} 'from' must be one of ` +
        `${pyReprValue(Object.keys(TEMPLATE_VALUE_KINDS).sort())}, got ${pyReprValue(kind)}`,
    );
  }
  checkKeys(descriptorName, `template value ${pyRepr(placeholder)} (from=${kind})`, raw, TEMPLATE_VALUE_KINDS[kind] as ReadonlySet<string>);

  // Python's TemplateValue dataclass defaults `key_prefix` to `""` at the FIELD level (line 170 of
  // descriptor.py); js_string/js_string_list/js_root_joins never pass key_prefix to the
  // constructor at all, so they always get that structural `""` default — never `None`, and never
  // influenced by a JSON `key_prefix` (which isn't even in those three kinds' allowed key set, so
  // checkKeys rejects it before construction). Only role_entries_js reads `raw.get("key_prefix", "")`
  // explicitly below, which is where the pyGet null-vs-absent distinction actually applies.
  const empty = { value: null, values: [], paths: [], role: null, drop: [], bodyKey: null, keyPrefix: '' };
  if (kind === 'js_string') {
    return { kind, ...empty, value: checkStr(descriptorName, `${pyRepr(placeholder)} 'value'`, raw['value']) };
  }
  if (kind === 'js_string_list') {
    const values = raw['values'];
    if (!Array.isArray(values) || values.length === 0) {
      fail(descriptorName, `template value ${pyRepr(placeholder)} 'values' must be a non-empty list`);
    }
    return { kind, ...empty, values: values.map((v) => checkStr(descriptorName, "'values' entry", v)) };
  }
  if (kind === 'js_root_joins') {
    const paths = raw['paths'];
    if (!Array.isArray(paths) || paths.length === 0) {
      fail(descriptorName, `template value ${pyRepr(placeholder)} 'paths' must be a non-empty list`);
    }
    return { kind, ...empty, paths: paths.map((p) => checkRelPath(descriptorName, "'paths' entry", p)) };
  }
  // role_entries_js
  const role = raw['role'];
  if (typeof role !== 'string' || !(ROLE_NAMES as readonly string[]).includes(role)) {
    fail(descriptorName, `template value ${pyRepr(placeholder)} 'role' must be one of ${pyReprValue([...ROLE_NAMES].sort())}, got ${pyReprValue(role)}`);
  }
  const drop = pyGet(raw, 'drop', []);
  if (!Array.isArray(drop)) fail(descriptorName, `template value ${pyRepr(placeholder)} 'drop' must be a list`);
  return {
    kind, ...empty, role,
    drop: drop.map((d: unknown) => checkStr(descriptorName, "'drop' entry", d)),
    bodyKey: checkStr(descriptorName, `${pyRepr(placeholder)} 'body_key'`, raw['body_key']),
    keyPrefix: pyGet(raw, 'key_prefix', '') as string | null,
  };
}

function parseTemplate(descriptorName: string, raw: unknown): Template {
  if (!isDict(raw)) fail(descriptorName, `a template must be an object, got ${pyReprValue(raw)}`);
  checkKeys(descriptorName, 'template', raw, new Set(['src', 'dest', 'values']));
  const src = checkStr(descriptorName, "template 'src'", raw['src']);
  if (src.includes('/') || !src.includes(TEMPLATE_MARKER)) {
    fail(descriptorName, `template 'src' must be a flat '<eco>${TEMPLATE_MARKER}<dest>' sibling, got ${pyRepr(src)}`);
  }
  const valuesRaw = pyGet(raw, 'values', {});
  if (!isDict(valuesRaw)) fail(descriptorName, "template 'values' must be an object");
  for (const placeholder of Object.keys(valuesRaw)) {
    if (!PLACEHOLDER.test(placeholder)) {
      fail(descriptorName, `template placeholder ${pyRepr(placeholder)} must match __UPPER_SNAKE__`);
    }
  }
  const values: Record<string, TemplateValue> = {};
  for (const [placeholder, v] of Object.entries(valuesRaw)) {
    values[placeholder] = parseTemplateValue(descriptorName, placeholder, v);
  }
  return { src, dest: checkRelPath(descriptorName, "template 'dest'", raw['dest']), values };
}

/** Validate `raw` (a decoded `<name>.json`) against the closed vocabulary; return the shape. */
export function parseDescriptor(descriptorName: string, raw: unknown): EcosystemDescriptor {
  if (!isDict(raw)) {
    const typeName = raw === null ? 'NoneType' : Array.isArray(raw) ? 'list'
      : typeof raw === 'string' ? 'str' : typeof raw === 'boolean' ? 'bool'
      : typeof raw === 'number' ? (Number.isInteger(raw) ? 'int' : 'float') : typeof raw;
    fail(descriptorName, `descriptor must be a JSON object, got ${typeName}`);
  }
  checkKeys(descriptorName, 'descriptor', raw, TOP_KEYS);
  for (const key of ['schema', 'name', 'vars', 'models', 'smoke', 'dispatch', 'roles', 'routes']) {
    if (!(key in raw)) fail(descriptorName, `missing required key ${pyRepr(key)}`);
  }
  if (raw['schema'] !== 1) fail(descriptorName, `'schema' must be 1, got ${pyReprValue(raw['schema'])}`);
  if (raw['name'] !== descriptorName) {
    fail(descriptorName, `'name' must equal the filename stem, got ${pyReprValue(raw['name'])}`);
  }
  const varsRaw = raw['vars'];
  if (!isDict(varsRaw) || Object.keys(varsRaw).length === 0) {
    fail(descriptorName, "'vars' must be a non-empty object");
  }
  for (const [key, value] of Object.entries(varsRaw)) {
    if (typeof value !== 'string') fail(descriptorName, `vars[${pyRepr(key)}] must be a string, got ${pyReprValue(value)}`);
  }
  const models = raw['models'];
  if (!isDict(models) || Object.keys(models).length === 0) fail(descriptorName, "'models' must be a non-empty object");
  checkKeys(descriptorName, "'models'", models, MODEL_TIERS);
  for (const [tier, value] of Object.entries(models)) {
    if (value !== null && typeof value !== 'string') {
      fail(descriptorName, `models[${pyRepr(tier)}] must be a string or null, got ${pyReprValue(value)}`);
    }
  }
  const smoke = raw['smoke'];
  if (!isDict(smoke)) fail(descriptorName, "'smoke' must be an object");
  checkKeys(descriptorName, "'smoke'", smoke, SMOKE_KEYS);
  for (const key of ['cli', 'test']) checkStr(descriptorName, `smoke[${pyRepr(key)}]`, smoke[key]);
  if ('expect' in smoke) {
    const expect = smoke['expect'];
    if (!isDict(expect)) fail(descriptorName, "smoke 'expect' must be an object");
    checkKeys(descriptorName, "smoke 'expect'", expect, new Set(['version_cmd']));
    const cmd = expect['version_cmd'];
    if (!Array.isArray(cmd) || cmd.length === 0) fail(descriptorName, "smoke expect 'version_cmd' must be a non-empty command list");
    for (const part of cmd) checkStr(descriptorName, "'version_cmd' entry", part);
  }
  if (typeof raw['dispatch'] !== 'string' || !DISPATCHES.has(raw['dispatch'])) {
    fail(descriptorName, `'dispatch' must be one of ${pyReprValue([...DISPATCHES].sort())}, got ${pyReprValue(raw['dispatch'])}`);
  }
  const rolesRaw = raw['roles'];
  if (!isDict(rolesRaw)) fail(descriptorName, "'roles' must be an object");
  const roleKeysSorted = Object.keys(rolesRaw).sort();
  const roleNamesSorted = [...ROLE_NAMES].sort();
  const rolesMatch =
    roleKeysSorted.length === roleNamesSorted.length &&
    roleKeysSorted.every((k, i) => k === roleNamesSorted[i]);
  if (!rolesMatch) {
    fail(descriptorName, `'roles' must define exactly ${pyReprValue(roleNamesSorted)}, got ${pyReprValue(roleKeysSorted)}`);
  }
  for (const key of ['routes', 'artifacts', 'guard', 'templates']) {
    if (key in raw && !Array.isArray(raw[key])) fail(descriptorName, `${pyRepr(key)} must be a list`);
  }
  const guardRaw: unknown[] = Array.isArray(raw['guard']) ? raw['guard'] : [];
  const guard = guardRaw.map((g) => checkStr(descriptorName, "'guard' entry", g));
  for (const module of guard) {
    if (module.includes('/')) fail(descriptorName, `'guard' entries are module filenames (no '/'), got ${pyRepr(module)}`);
  }

  // The remaining sections are validated in the SAME order as the Python original's return-call
  // argument evaluation: roles, then routes, then artifacts, then gate, then templates last. This
  // order is a real contract — which error a multiply-broken descriptor reports — not incidental.
  const roles: Record<string, RoleSpec> = {};
  for (const [role, spec] of Object.entries(rolesRaw)) roles[role] = parseRole(descriptorName, role, spec);

  const routesRaw: unknown[] = Array.isArray(raw['routes']) ? raw['routes'] : [];
  const routes = routesRaw.map((r) => parseRoute(descriptorName, r));

  const artifactsRaw: unknown[] = Array.isArray(raw['artifacts']) ? raw['artifacts'] : [];
  const artifacts = artifactsRaw.map((a) => parseArtifact(descriptorName, a));

  const gate = 'gate' in raw ? parseGate(descriptorName, raw['gate']) : null;

  const templatesRaw: unknown[] = Array.isArray(raw['templates']) ? raw['templates'] : [];
  const templates = templatesRaw.map((t) => parseTemplate(descriptorName, t));

  return {
    name: descriptorName,
    // Cast is safe: every value was validated to be a string (vars) / string-or-null (models) in
    // the loops above.
    vars: { ...varsRaw } as Record<string, string>,
    models: { ...models } as Record<string, string | null>,
    smoke: { ...smoke },
    dispatch: raw['dispatch'],
    roles, routes, artifacts, guard, gate, templates,
  };
}

// ── Filesystem boundary ────────────────────────────────────────────────────

const REPO_ROOT = join(import.meta.dirname, '..', '..');
const ECOSYSTEMS_DIR = join(REPO_ROOT, 'src', 'ecosystems');

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
