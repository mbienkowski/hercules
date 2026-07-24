#!/usr/bin/env node
/**
 * `hercules-build` entry point (thin FS boundary).
 *
 * `--target {<name>|all} [--check]`. Without `--check` it writes `dist/<target>/`; with `--check`
 * it renders to a temp dir and diffs against the committed `dist/` (exit non-zero on drift). One
 * code path for local dev and CI. The accepted target names derive from the ecosystem descriptors
 * on disk, so `all` and the valid values extend automatically when a descriptor is added.
 *
 * Dispatch is entirely generic: for every source the content loop calls `genSerialize.dest` (the
 * descriptor's route interpreter) and `genExtras.emitExtras` (the descriptor's non-content
 * emitter). There are **zero** per-ecosystem branches here — a target is one
 * `src/ecosystems/<name>.json` file.
 *
 * Unlike the Python original, `targets()`/`buildTarget()`/`checkTarget()` are plain functions, not
 * module-scope constants — `cli.py:35`'s `TARGETS = tuple(descriptor.names())` runs a filesystem
 * scan as a side effect of `import cli`, which the migration spec's few-shot catalogue (#5) names
 * directly as a pattern NOT to replicate. A bare `import` of this module performs ZERO fs syscalls
 * (pinned by `tests-ts/bin/cli.spec.ts`); every scan happens inside a function call from `main()`,
 * the composition root.
 */

import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, sep } from 'node:path';

import { discover, ECOSYSTEMS_DIR, names } from '../build/descriptor.mjs';
import { readSource, write } from '../build/emit.mjs';
import { emitExtras } from '../build/genExtras.mjs';
import type { ExtrasContext } from '../build/genExtras.mjs';
import { dest } from '../build/genSerialize.mjs';
import { discoverSources } from '../build/layout.mjs';
import type { ModelsMap, TierMap } from '../build/modelMap.mjs';
import { buildRegistry } from '../build/serialize.mjs';
import { readCanonicalVersion } from '../build/versionTargets.mjs';

const REPO_ROOT = join(import.meta.dirname, '..', '..');
const SRC = join(REPO_ROOT, 'src');
const SRC_CONTENT = join(SRC, 'content');
const DIST = join(REPO_ROOT, 'dist');
// The canonical frozen-test guard + the one generic write-gate adapter live in the NEUTRAL
// src/hooks/ tree; every ecosystem ships byte-copies, so the write-gate logic has one source of truth.
const SHARED_HOOKS_SRC = join(SRC, 'hooks');

/** The one authoritative ecosystem list, derived from the descriptor files themselves. */
export function targets(root: string = ECOSYSTEMS_DIR): string[] {
  return names(root);
}

function targetsFor(name: string, root: string = ECOSYSTEMS_DIR): string[] {
  return name === 'all' ? targets(root) : [name];
}

/** Every ecosystem's model-tier row, from the descriptors (the one per-ecosystem source). */
function loadModels(root: string = ECOSYSTEMS_DIR): ModelsMap {
  const out: Record<string, TierMap> = {};
  for (const [name, d] of Object.entries(discover(root))) out[name] = d.models;
  return out;
}

/** The target's token `vars` from its descriptor; empty for an unknown target (test stubs). */
function loadTokens(target: string, root: string = ECOSYSTEMS_DIR): ReadonlyMap<string, string> {
  const found = discover(root)[target];
  return found === undefined ? new Map() : new Map(Object.entries(found.vars));
}

/**
 * Render `target` into `outRoot`; return the sorted list of written relative paths.
 *
 * The body holds no per-ecosystem branches: the content loop relocates each source via the generic
 * route interpreter (`genSerialize.dest`) and the non-content artifacts come from the generic
 * emitter (`genExtras.emitExtras`), both driven wholly by the target's descriptor.
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
    srcContent: SRC_CONTENT,
    tokens,
    version: readCanonicalVersion(REPO_ROOT),
  };
  written.push(...emitExtras(ctx, desc));
  return written.slice().sort();
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
 * Always byte-compares (never relies on file size/mtime as a shortcut), matching Python's
 * `filecmp.cmp(..., shallow=False)` — a same-size, same-mtime hand-edit to a committed `dist/`
 * file must still be caught.
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
  return dirDiff(committed, out).length > 0 ? 1 : 0;
}

function parseArgs(argv: readonly string[]): { target: string; check: boolean } {
  let target = 'all';
  let check = false;
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--target') {
      target = argv[i + 1] as string;
      i += 1;
    } else if (argv[i] === '--check') {
      check = true;
    }
  }
  return { target, check };
}

// `distRoot` (an addition over the Python original's hardcoded DIST constant, purely for test
// benefit — same rationale as checkTarget's own `distRoot` param above) lets a test point the
// --check comparison at a scratch "committed" tree instead of the real repo's dist/, so the
// stale-output stderr message can be exercised directly rather than merely trusted.
export function main(argv: readonly string[], distRoot: string = DIST): number {
  const { target, check } = parseArgs(argv);
  let rc = 0;
  const known = new Set(names());
  for (const t of targetsFor(target)) {
    if (!known.has(t)) continue;
    if (check) {
      const tmp = mkdtempSync(join(tmpdir(), 'hercules-check-'));
      try {
        rc |= checkTarget(t, tmp, distRoot);
      } finally {
        rmSync(tmp, { recursive: true, force: true });
      }
    } else {
      buildTarget(t, join(distRoot, t));
    }
  }
  if (check && rc !== 0) {
    process.stderr.write('dist/ is stale — regenerate it with `make build` and commit the result.\n');
  }
  return rc;
}

// Only run when invoked directly (`node cli.mjs ...`), not when imported by a test — matching
// Python's `if __name__ == "__main__":` guard.
if (import.meta.url === `file://${process.argv[1]}`) {
  process.exitCode = main(process.argv.slice(2));
}
