#!/usr/bin/env node
/**
 * `hercules-build` entry point — the build's filesystem (FS) boundary.
 *
 * `--target {<name>|all} [--check]`: writes `dist/<target>/`, or with `--check` renders to a temp
 * dir and diffs against the committed `dist/`, exiting non-zero on drift. Dispatch is entirely
 * generic — a target is one `ecosystems/<name>.json` file, so the valid target names extend with
 * the descriptors on disk. Importing this module performs ZERO FS syscalls (pinned by
 * `builder/tests/cli/cli.spec.ts`): every scan happens inside a call from `main()`, the composition root.
 */

import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, sep } from 'node:path';
import { pathToFileURL } from 'node:url';

import { discover, TARGETS_DIR, names } from '../descriptor.mjs';
import { readSource, write } from '../emit.mjs';
import { emitExtras } from '../genExtras.mjs';
import type { ExtrasContext } from '../genExtras.mjs';
import { dest } from '../genSerialize.mjs';
import { comparePathParts, discoverSources } from '../layout.mjs';
import type { ModelsMap, TierMap } from '../modelMap.mjs';
import { buildRegistry } from '../serialize.mjs';
import { readCanonicalVersion } from '../versionTargets.mjs';

// `process.cwd()`, not an `import.meta.dirname` relative hop: this module runs BOTH as source
// (Vitest, under src/builder/bin/) and as compiled output (`.ts-out/builder/bin/cli.mjs`), which sit
// at different depths, so no fixed hop count is correct in both. Every real entry point runs from the repo root.
const REPO_ROOT = process.cwd();
const SRC_CONTENT = join(REPO_ROOT, 'src', 'content');
const DIST = join(REPO_ROOT, 'dist');
// The canonical frozen-test guard + the one generic write-gate adapter live in the NEUTRAL
// src/hooks/ tree; every ecosystem ships byte-copies, so the write-gate logic has one source of truth.
const SHARED_HOOKS_SRC = join(REPO_ROOT, 'src', 'hooks');
const SHARED_TOOLS_SRC = join(REPO_ROOT, 'src', 'tools');

/** The one authoritative ecosystem list, derived from the descriptor files themselves. */
export function targets(root: string = TARGETS_DIR): string[] {
  return names(root);
}

function targetsFor(name: string, root: string = TARGETS_DIR): string[] {
  return name === 'all' ? targets(root) : [name];
}

/** Every ecosystem's model-tier row, from the descriptors (the one per-ecosystem source). */
function loadModels(root: string = TARGETS_DIR): ModelsMap {
  const out: Record<string, TierMap> = {};
  for (const [name, d] of Object.entries(discover(root))) out[name] = d.models;
  return out;
}

/** The target's token `vars` from its descriptor; empty for an unknown target (test stubs). */
function loadTokens(target: string, root: string = TARGETS_DIR): ReadonlyMap<string, string> {
  const found = discover(root)[target];
  return found === undefined ? new Map() : new Map(Object.entries(found.vars));
}

/**
 * Render `target` into `outRoot`; return the sorted list of written relative paths.
 *
 * No per-ecosystem branches: each source is relocated by the generic route interpreter
 * (`genSerialize.dest`) and the non-content artifacts come from `genExtras.emitExtras`, both driven
 * wholly by the target's descriptor.
 */
export function buildTarget(target: string, outRoot: string): string[] {
  const descriptors = discover();
  const desc = descriptors[target];
  if (desc === undefined) throw new Error(`unknown target: '${target}'`);
  const registry = buildRegistry(Object.values(descriptors));
  const models = loadModels();
  const tokens = loadTokens(target);
  const written: string[] = [];
  for (const src of discoverSources(SRC_CONTENT)) {
    const rel = relative(SRC_CONTENT, src).split(sep).join('/');
    const d = dest(desc, rel);
    if (d === null) continue; // an `omit` route — this source ships nothing on this target
    const text = readSource(src);
    write(join(outRoot, d), registry.serializeFile(target, text, tokens, models, rel));
    written.push(d);
  }
  const ctx: ExtrasContext = {
    outRoot,
    sharedHooksSrc: SHARED_HOOKS_SRC,
    sharedToolsSrc: SHARED_TOOLS_SRC,
    srcContent: SRC_CONTENT,
    tokens,
    version: readCanonicalVersion(REPO_ROOT),
  };
  written.push(...emitExtras(ctx, desc));
  return written.slice().sort(comparePathParts);
}

function relFiles(root: string): Set<string> {
  const out = new Set<string>();
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === '__pycache__') continue;
        walk(full);
      } else if (entry.isFile() && !entry.name.endsWith('.pyc')) {
        out.add(relative(root, full).split(sep).join('/'));
      }
    }
  };
  try {
    walk(root);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return out;
    throw error;
  }
  return out;
}

/**
 * Relative paths that differ between `a` and `b`, compared by CONTENT.
 *
 * Always byte-compares, never taking file size or mtime as a shortcut — a same-size, same-mtime
 * hand-edit to a committed `dist/` file must still be caught.
 */
function dirDiff(a: string, b: string): string[] {
  const aFiles = relFiles(a);
  const bFiles = relFiles(b);
  const diffs = new Set<string>();
  for (const rel of aFiles) if (!bFiles.has(rel)) diffs.add(rel);
  for (const rel of bFiles) if (!aFiles.has(rel)) diffs.add(rel);
  for (const rel of aFiles) {
    if (!bFiles.has(rel)) continue;
    if (!readFileSync(join(a, rel)).equals(readFileSync(join(b, rel)))) diffs.add(rel);
  }
  return [...diffs].sort();
}

/**
 * Classify how a committed `dist/` file differs from a fresh render, so the failure names the remedy.
 *
 * "stale" and "stray" need different fixes and the old message only offered one: it said "regenerate it
 * with `make build`", but `make build` does not prune, so following that advice on a stray file leaves
 * the file in place and the gate still red with no hint which file is at fault.
 */
export function classifyDiff(committed: string, rendered: string, paths: readonly string[]): string[] {
  const inRendered = relFiles(rendered);
  const inCommitted = relFiles(committed);
  return paths.map((rel) => {
    if (!inRendered.has(rel)) return `${rel} — STRAY: present in dist/ but declared by no target; delete it`;
    if (!inCommitted.has(rel)) return `${rel} — MISSING from dist/; \`make build\` writes it`;
    return `${rel} — STALE content; \`make build\` refreshes it`;
  });
}

/** Render `target` to a temp dir and diff vs committed `dist/<target>`; 0 == in sync. */
export function checkTarget(target: string, tmpRoot: string, distRoot: string = DIST): number {
  const out = join(tmpRoot, target);
  buildTarget(target, out);
  const committed = join(distRoot, target);
  try {
    statSync(committed);
  } catch {
    return relFiles(out).size === 0 ? 0 : 1;
  }
  const diffs = dirDiff(committed, out);
  if (diffs.length === 0) return 0;
  for (const line of classifyDiff(committed, out, diffs)) {
    process.stderr.write(`  ${target}/${line}\n`);
  }
  return 1;
}

/**
 * Parse `--target {<name>|all} [--check]`; both `--target foo` and `--target=foo` are accepted.
 *
 * An unrecognized argument is a loud error, never a silent no-op: otherwise `--target=cursor` would
 * fall through unmatched and silently default `target` to `'all'` — a correct-looking wrong build.
 */
function parseArgs(argv: readonly string[]): { target: string; check: boolean } {
  let target = 'all';
  let check = false;
  for (let argIndex = 0; argIndex < argv.length; argIndex += 1) {
    const arg = argv[argIndex] as string;
    if (arg === '--target') {
      const value = argv[argIndex + 1];
      if (value === undefined) throw new Error('--target requires a value');
      target = value;
      argIndex += 1; // consume the separate value token
    } else if (arg.startsWith('--target=')) {
      target = arg.slice('--target='.length);
    } else if (arg === '--check') {
      check = true;
    } else {
      throw new Error(`unrecognized argument: ${arg}`);
    }
  }
  return { target, check };
}

// `distRoot` is a test seam (as on `checkTarget` above): it points the `--check` comparison at a
// scratch "committed" tree instead of the real `dist/`, so the stale-output stderr message can be
// exercised directly rather than merely trusted.
export function main(argv: readonly string[], distRoot: string = DIST): number {
  const { target, check } = parseArgs(argv);
  let anyStale = false;
  const known = new Set(names());
  for (const t of targetsFor(target)) {
    if (!known.has(t)) continue;
    if (check) {
      const tmp = mkdtempSync(join(tmpdir(), 'hercules-check-'));
      try {
        // checkTarget returns 0 (in sync) or 1 (stale); one stale target makes the whole run stale.
        if (checkTarget(t, tmp, distRoot) !== 0) anyStale = true;
      } finally {
        rmSync(tmp, { recursive: true, force: true });
      }
    } else {
      buildTarget(t, join(distRoot, t));
    }
  }
  if (check && anyStale) {
    process.stderr.write('dist/ does not match a fresh render. Each path above says which fix applies '
      + '— `make build` refreshes stale and missing files but never prunes, so a STRAY file has to be '
      + 'deleted by hand. Commit the result.\n');
  }
  return anyStale ? 1 : 0;
}

// Only run when invoked directly (`node cli.mjs ...`), not when imported by a test. `pathToFileURL`
// percent-encodes spaces and non-ASCII exactly the way `import.meta.url` does, so a checkout under
// e.g. `My Work/` still matches — a raw `file://${argv[1]}` would not, silently making `make build` a no-op.
if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  process.exitCode = main(process.argv.slice(2));
}
