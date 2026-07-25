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
 * `ecosystems/<name>.json` file.
 *
 * Unlike the Python original, `targets()`/`buildTarget()`/`checkTarget()` are plain functions, not
 * module-scope constants — `cli.py:35`'s `TARGETS = tuple(descriptor.names())` runs a filesystem
 * scan as a side effect of `import cli`, which the migration spec's few-shot catalogue (#5) names
 * directly as a pattern NOT to replicate. A bare `import` of this module performs ZERO fs syscalls
 * (pinned by `builder/tests/cli.spec.ts`); every scan happens inside a function call from `main()`,
 * the composition root.
 */

import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, sep } from 'node:path';

import { discover, TARGETS_DIR, names } from '../descriptor.mjs';
import { readSource, write } from '../emit.mjs';
import { emitExtras } from '../genExtras.mjs';
import type { ExtrasContext } from '../genExtras.mjs';
import { dest } from '../genSerialize.mjs';
import { comparePathParts, discoverSources } from '../layout.mjs';
import type { ModelsMap, TierMap } from '../modelMap.mjs';
import { buildRegistry } from '../serialize.mjs';
import { readCanonicalVersion } from '../versionTargets.mjs';

// process.cwd(), not an `import.meta.dirname` relative hop — this module runs BOTH as source
// (Vitest, under src/builder/bin/) and as compiled output (`.ts-out/builder/bin/cli.mjs`), which sit
// at different depths, so a fixed relative-hop count cannot be correct in both. See descriptor.mts's
// own REPO_ROOT for the fuller reasoning — every real entry point already runs from the repo root.
const REPO_ROOT = process.cwd();
const SRC_CONTENT = join(REPO_ROOT, 'src', 'content');
const DIST = join(REPO_ROOT, 'dist');
// The canonical frozen-test guard + the one generic write-gate adapter live in the NEUTRAL
// src/hooks/ tree; every ecosystem ships byte-copies, so the write-gate logic has one source of truth.
const SHARED_HOOKS_SRC = join(REPO_ROOT, 'src', 'hooks');

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

/**
 * Parses `--target {<name>|all} [--check]`, matching the Python original's `argparse` contract:
 * both `--target foo` and `--target=foo` are accepted, and an unrecognized argument is a loud
 * error rather than a silent no-op. Without this, `--target=cursor` (a reasonable, common CLI
 * convention argparse also accepts) would fall through unmatched and silently default `target` to
 * `'all'` — a correct-looking but wrong outcome, not something a typo should produce.
 */
function parseArgs(argv: readonly string[]): { target: string; check: boolean } {
  let target = 'all';
  let check = false;
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i] as string;
    if (arg === '--target') {
      const value = argv[i + 1];
      if (value === undefined) throw new Error('--target requires a value');
      target = value;
      i += 1;
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
