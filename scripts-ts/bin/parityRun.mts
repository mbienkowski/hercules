/**
 * Parity fixture runner, TypeScript side. Speaks the identical protocol to
 * scripts/ci/parity_run.py, so `make parity` byte-diffs the two without knowing anything about the
 * functions involved. See that file for the fixture and result shapes.
 *
 * Fixtures name functions in the Python original's snake_case; the FUNCTIONS map below is the one
 * place that translation lives, so a fixture is engine-neutral and neither side can quietly run a
 * different function than the other.
 *
 * ONE exception to the message-text rule, starting with `descriptor` (commit 5 of the migration):
 * once descriptor.mts moved to Zod, byte-identical Python error TEXT stopped being a goal — see
 * both that module's own top-of-file comment and parity_run.py's module docstring for why. For that
 * module only, an error's message is replaced with the SAME fixed placeholder both runners use, so
 * the harness still proves both engines reach the same accept/reject decision without asserting
 * they explain it identically.
 *
 * Usage: node .ts-out/bin/parityRun.mjs < fixture.json
 */

import { createHash } from 'node:crypto';
import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  statSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';

import * as descriptorMod from '../build/descriptor.mjs';
import * as emit from '../build/emit.mjs';
import * as genExtras from '../build/genExtras.mjs';
import * as genSerialize from '../build/genSerialize.mjs';
import * as layout from '../build/layout.mjs';
import * as modelMap from '../build/modelMap.mjs';
import * as parse from '../build/parse.mjs';
import * as render from '../build/render.mjs';
import * as versionTargets from '../build/versionTargets.mjs';

// Must match parity_run.py's _DESCRIPTOR_ERROR_PLACEHOLDER byte-for-byte — the byte-diff harness
// only proves accept/reject agreement for descriptor if both sides substitute the SAME string.
const DESCRIPTOR_ERROR_PLACEHOLDER = '<descriptor: message text not compared since commit 5 (Zod)>';

type FileSpec = string | { text: string; mode?: string };

interface Fixture {
  module: string;
  fn: string;
  files?: Record<string, FileSpec>;
  symlinks?: Record<string, string>;
  args?: unknown[];
  pathArgs?: number[];
  capture?: string[];
}

/**
 * snake_case fixture name -> the TypeScript function, with arguments adapted where the two
 * signatures legitimately differ (Python dicts become Maps; Python tuples become objects).
 * Every adaptation is here rather than in the modules, so the ported code stays idiomatic.
 */
const FUNCTIONS: Record<string, (args: unknown[]) => unknown> = {
  // The Python original returns a positional tuple; the port returns a named object, which is the
  // better API. The runner unpacks it back to tuple ORDER so the comparison is about VALUES rather
  // than about which language's calling convention was chosen.
  'parse.parse_frontmatter': ([text]) => {
    const { metadata, body } = parse.parseFrontmatter(text as string);
    return [metadata, body];
  },
  'parse.render_frontmatter': ([pairs]) =>
    parse.renderFrontmatter(new Map(pairs as [string, string][])),
  'parse.split_document': ([text]) => {
    const { block, body } = parse.splitDocument(text as string);
    return [block, body];
  },

  'render.render_body': ([text, target, tokens]) =>
    render.renderBody(
      text as string,
      target as string,
      new Map(Object.entries(tokens as Record<string, string>)),
    ),

  'model_map.resolve': ([models, target, tier]) =>
    modelMap.resolve(models as modelMap.ModelsMap, target as string, tier as string),

  'layout.discover_sources': ([root]) => layout.discoverSources(root as string),

  'emit.write': ([dest, text]) => emit.write(dest as string, text as string),
  'emit.copy_versioned': ([src, dest, version]) =>
    emit.copyVersioned(src as string, dest as string, version as string),
  'emit.copy_map': ([srcDir, outRoot, mapping]) =>
    emit.copyMap(
      srcDir as string,
      outRoot as string,
      new Map(Object.entries(mapping as Record<string, string>)),
    ),

  'version_targets.read_versions': ([root]) => versionTargets.readVersions(root as string),
  'version_targets.read_canonical_version': ([root]) =>
    versionTargets.readCanonicalVersion(root as string),
  'version_targets.write_version': ([version, root]) =>
    versionTargets.writeVersion(version as string, root as string),
  // JSON has no `undefined`, so the fixture carries an absent `expected` as null; the port's
  // signature uses `undefined`, which is the TypeScript convention for "not supplied".
  'version_targets.check_in_sync': ([root, expected]) =>
    versionTargets.checkInSync(root as string, (expected as string | null) ?? undefined),

  'descriptor.parse_descriptor': ([name, raw]) => descriptorMod.parseDescriptor(name as string, raw),
  'descriptor.load': ([path]) => descriptorMod.load(path as string),
  'descriptor.discover': ([root]) => descriptorMod.discover(root as string),
  'descriptor.dist_files': ([name, root]) =>
    descriptorMod.distFiles(name as string, root as string | undefined),
  'descriptor.names': ([root]) => descriptorMod.names(root as string | undefined),

  'genserialize.serialize_file_for_fixture': ([descriptorRaw, text, tokens, models, rel]) =>
    genSerialize.serializeFileForFixture(
      descriptorRaw,
      text as string,
      new Map(Object.entries(tokens as Record<string, string>)),
      models as modelMap.ModelsMap | null,
      rel as string | null,
    ),

  'genextras.emit_extras_for_fixture': ([descriptorRaw, tokens, version, outRoot]) =>
    genExtras.emitExtrasForFixture(
      descriptorRaw,
      new Map(Object.entries(tokens as Record<string, string>)),
      version as string,
      outRoot as string,
    ),
  'genextras.js_object_literal': ([obj]) => genExtras.jsObjectLiteral(obj as genExtras.JsLiteralValue),
};

/**
 * Normalise a return value so both runtimes serialise it identically.
 *
 * Maps and plain objects become [key, value] PAIR LISTS SORTED BY KEY, never JSON objects. Two
 * reasons: (1) JavaScript hoists integer-like keys to the front of a plain object regardless of
 * insertion order while Python's dict never does, so a frontmatter block whose first key is "1"
 * would otherwise round-trip differently on the two sides; (2) sorting decouples the comparison
 * from which order each engine's code happens to construct an object's properties in — the Python
 * side sorts identically (see parity_run.py), so neither side has to match the other's
 * construction order, only its final key/value set. Semantic order lives in ARRAYS, which are never
 * sorted here, not in object keys.
 */
function canonical(value: unknown): unknown {
  if (value === undefined) return null;
  if (value instanceof Map) {
    return [...value].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(([k, v]) => [k, canonical(v)]);
  }
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    return Object.keys(obj).sort().map((k) => [k, canonical(obj[k])]);
  }
  return value;
}

function tree(root: string, capture: string[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const rel of [...capture].sort()) {
    const path = join(root, rel);
    try {
      const data = readFileSync(path);
      out[rel] = {
        sha256: createHash('sha256').update(data).digest('hex'),
        // Mode is captured because a content comparison cannot see it — see the Python runner.
        mode: (statSync(path).mode & 0o777).toString(8),
      };
    } catch {
      out[rel] = null;
    }
  }
  return out;
}

/** Mirrors Python's json.dumps(..., indent=1, ensure_ascii=False, sort_keys=True). */
function dumps(value: unknown): string {
  const sortKeys = (input: unknown): unknown => {
    if (Array.isArray(input)) return input.map(sortKeys);
    if (input !== null && typeof input === 'object') {
      return Object.fromEntries(
        Object.keys(input as Record<string, unknown>)
          .sort()
          .map((k) => [k, sortKeys((input as Record<string, unknown>)[k])]),
      );
    }
    return input;
  };
  return `${JSON.stringify(sortKeys(value), null, 1)}\n`;
}

const fixture = JSON.parse(readFileSync(0, 'utf-8')) as Fixture;
const key = `${fixture.module}.${fixture.fn}`;
const fn = FUNCTIONS[key];
if (fn === undefined) {
  process.stderr.write(`parityRun: no binding for ${key}\n`);
  process.exit(2);
}

const root = realpathSync(mkdtempSync(join(tmpdir(), 'hercules-parity-')));
let payload: Record<string, unknown>;
try {
  for (const [rel, spec] of Object.entries(fixture.files ?? {})) {
    mkdirSync(dirname(join(root, rel)), { recursive: true });
    // A value is either the file's text, or {text, mode} when the fixture needs a specific source
    // mode — which is how the copy-mode divergence is exercised.
    const text = typeof spec === 'string' ? spec : spec.text;
    writeFileSync(join(root, rel), text, 'utf-8');
    if (typeof spec !== 'string' && spec.mode !== undefined) {
      chmodSync(join(root, rel), Number.parseInt(spec.mode, 8));
    }
  }
  for (const [linkRel, targetRel] of Object.entries(fixture.symlinks ?? {})) {
    mkdirSync(dirname(join(root, linkRel)), { recursive: true });
    symlinkSync(join(root, targetRel), join(root, linkRel));
  }

  const args = [...(fixture.args ?? [])];
  for (const index of fixture.pathArgs ?? []) args[index] = join(root, args[index] as string);

  try {
    const result = fn(args);
    payload = { ok: true, result: canonical(result) };
    if (fixture.capture !== undefined && fixture.capture.length > 0) {
      payload['files'] = tree(root, fixture.capture);
    }
  } catch (error) {
    // Only the MESSAGE is compared, never the exception class — see the Python runner for why.
    // descriptor: message text is no longer compared post-Zod — see the file header comment.
    payload = {
      ok: false,
      error: fixture.module === 'descriptor' ? DESCRIPTOR_ERROR_PLACEHOLDER : (error as Error).message,
    };
  }
} finally {
  rmSync(root, { recursive: true, force: true });
}

// The workspace is a fresh mkdtemp on each side, so its path differs between the two runners and
// would show up as a false divergence in any result that echoes a path. Normalising it keeps the
// comparison about behaviour. Applied to the serialised form so it reaches nested values too.
process.stdout.write(dumps(payload).split(root).join('<workspace>'));
