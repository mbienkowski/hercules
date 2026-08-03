/**
 * The live-CLI smoke declarations: which real binary each distribution is proved against.
 *
 * A recipe answers what a distribution CONTAINS; this answers how CI proves it loads in the real
 * tool. `smokeMatrix.mts` pins the two together — an entry here naming no distribution fails loud.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Ajv, type SchemaObject } from 'ajv';

const REPO_ROOT = process.cwd();
const CONFIG_PATH = join(REPO_ROOT, 'internal', 'release', 'smoke-targets.json');
const SCHEMA_PATH = join(REPO_ROOT, 'internal', 'release', 'smoke-targets.schema.json');

/** How a host CLI is installed for a smoke leg; absent means "already on PATH". */
export type SmokeInstall =
  | { readonly method: 'package'; readonly name: string; readonly version: string }
  | { readonly method: 'script'; readonly url: string; readonly flags?: string };

/** One distribution's live check. */
export interface SmokeTarget {
  readonly cli: string;
  readonly test: string;
  readonly install?: SmokeInstall;
  /** Required: `tests/dist/universalSmoke.spec.ts` fails closed without it, so the schema says so. */
  readonly expect: { readonly version_cmd: readonly string[] };
}

export class SmokeTargetsError extends Error {
  override readonly name = 'SmokeTargetsError';
}

let cached: Readonly<Record<string, SmokeTarget>> | null = null;

/** Every declared smoke target, keyed by distribution name. Validated against its own schema. */
export function smokeTargets(path: string = CONFIG_PATH): Readonly<Record<string, SmokeTarget>> {
  if (cached !== null && path === CONFIG_PATH) return cached;
  const schema = JSON.parse(readFileSync(SCHEMA_PATH, 'utf-8')) as SchemaObject;
  const parsed = JSON.parse(readFileSync(path, 'utf-8')) as { targets: Record<string, SmokeTarget> };
  const validate = new Ajv({ allErrors: true, discriminator: true, useDefaults: true, strict: false })
    .compile(schema);
  if (!validate(parsed)) {
    // `params` carries the offending key name — without it, "must NOT have additional properties"
    // makes the reader hunt for which one, which is the whole job of the message.
    const detail = (validate.errors ?? [])
      .map((e) => {
        const extra = Object.keys(e.params ?? {}).length > 0 ? ` ${JSON.stringify(e.params)}` : '';
        return `  ${e.instancePath || '(root)'} ${e.message ?? 'is invalid'}${extra}`;
      })
      .join('\n');
    throw new SmokeTargetsError(`${path}: does not match smoke-targets.schema.json\n${detail}`);
  }
  const targets = parsed.targets;
  if (path === CONFIG_PATH) cached = targets;
  return targets;
}
