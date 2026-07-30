import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { discover, names } from '../../descriptor.mjs';
import type { ExtrasContext } from '../../genExtras.mjs';
import { buildTarget, checkTarget, classifyDiff, main, targets } from '../../bin/cli.mjs';
import { buildRegistry } from '../../serialize.mjs';
import { ECOSYSTEMS } from '../../../commons/support/descriptorFixtures';
import { repoRoot } from '../../../commons/support/repo';

// buildTarget/checkTarget/targets are plain functions, not module-scope constants (see cli.mts's own
// top comment), so every test here calls them explicitly rather than relying on an import-time
// bootstrap.

const dirs: string[] = [];

function tmpDir(prefix: string): string {
  const root = mkdtempSync(join(tmpdir(), prefix));
  dirs.push(root);
  return root;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('targets', () => {
  it('derives the accepted --target values from the descriptor files themselves', () => {
    expect(targets()).toEqual(names());
    expect(targets()).toEqual([
      'claude-code', 'copilot-cli', 'cursor', 'gemini-cli', 'grok-build', 'opencode',
    ]);
  });
});

describe('buildTarget', () => {
  it('has no per-ecosystem branches: every real target renders without throwing', () => {
    // A full build of all 6 real targets — same central-processing-unit (CPU) contention reasoning
    // as checkTarget's and main's own explicit timeouts elsewhere in this file.
    for (const t of targets()) {
      const out = tmpDir(`hercules-cli-build-${t}-`);
      expect(() => buildTarget(t, out)).not.toThrow();
    }
  }, 20_000);

  it('returns the sorted list of written relative paths', () => {
    const out = tmpDir('hercules-cli-build-');
    const written = buildTarget('claude-code', out);
    expect(written).toEqual([...written].sort());
    expect(written).toContain('settings.json');
    expect(written.length).toBeGreaterThan(0);
  });

  it('throws on an unknown target', () => {
    const out = tmpDir('hercules-cli-build-');
    expect(() => buildTarget('does-not-exist', out)).toThrow(/does-not-exist/);
  });

  it('renders opencode plugin.js with entries embedded and no leftover placeholders', () => {
    // Exercised through buildTarget rather than emitExtras plus a hand-built context.
    const out = tmpDir('hercules-cli-build-opencode-');
    buildTarget('opencode', out);
    const js = readFileSync(join(out, 'plugin.js'), 'utf-8');
    expect(js).toContain('PLUGIN_ROOT = path.resolve(__dirname)');
    expect(js).toContain('cfg.default_agent = "hercules"');
    expect(js).toContain('"hercules:discover"');
    expect(js).not.toContain('__AGENT_ENTRIES__');
    expect(js).not.toContain('__COMMAND_ENTRIES__');
  });

  it('binds every standalone opencode command file to its owning agent', () => {
    // No existsSync guard around the directory read, deliberately: a missing or empty commands/ must
    // fail the length assertion below, not silently skip every assertion in the loop.
    const out = tmpDir('hercules-cli-build-opencode-');
    buildTarget('opencode', out);
    const commandsDir = join(out, 'commands');
    const files = readdirSync(commandsDir).filter((name) => name.endsWith('.md'));
    expect(files.length, 'expected standalone command files').toBeGreaterThan(0);
    for (const name of files) {
      const text = readFileSync(join(commandsDir, name), 'utf-8');
      expect(text, `${name}: Claude-only key kept`).not.toContain('disable-model-invocation');
      expect(text, `${name}: missing OpenCode agent binding`).toContain('\nagent: hercules\n');
    }
  });

  it('the generated opencode plugin bundle has no leftover Claude-only command settings', () => {
    const out = tmpDir('hercules-cli-build-opencode-');
    buildTarget('opencode', out);
    const js = readFileSync(join(out, 'plugin.js'), 'utf-8');
    expect(js, 'Claude-only command key leaked into plugin.js').not.toContain('disable-model-invocation');
    expect(js, 'command template still opens with a YAML fence').not.toContain('template: "---');
  });
});

describe('checkTarget', () => {
  it('reports 0 for every real target against the committed dist/ tree', () => {
    // The strongest available proof of correctness: the build reproduces the committed dist/ tree
    // byte-for-byte, not merely "renders without throwing".
    for (const t of targets()) {
      const tmp = tmpDir(`hercules-cli-check-${t}-`);
      expect(checkTarget(t, tmp)).toBe(0);
    }
    // A full build+diff of all 6 real targets, sequentially. CPU contention under full-suite
    // parallelism can push this past Vitest's default 5000ms, hence the explicit, generous timeout.
  }, 20_000);

  it('reports 1 when the rendered tree diverges from a corrupted comparison root, 0 once fixed', () => {
    // checkTarget's `distRoot` param points the comparison at a SCRATCH "committed" tree instead of
    // the real repo's dist/, so the divergence path is exercised directly rather than merely trusted.
    const distRoot = tmpDir('hercules-cli-check-dist-');
    buildTarget('claude-code', join(distRoot, 'claude-code'));
    const tmp1 = tmpDir('hercules-cli-check-scratch-');
    expect(checkTarget('claude-code', tmp1, distRoot)).toBe(0);

    writeFileSync(join(distRoot, 'claude-code', 'settings.json'), 'BROKEN', 'utf-8');
    const tmp2 = tmpDir('hercules-cli-check-scratch-');
    expect(checkTarget('claude-code', tmp2, distRoot)).toBe(1);
  });

  it('reports 1 when the comparison root does not exist and something was written', () => {
    const distRoot = tmpDir('hercules-cli-check-empty-dist-'); // exists but has no <target> subdir
    const tmp = tmpDir('hercules-cli-check-scratch-');
    expect(checkTarget('claude-code', tmp, distRoot)).toBe(1);
  });
});

describe('the built dist/ tree carries the mode every emitted file requires', () => {
  it('every rendered file is 0o644', () => {
    const out = tmpDir('hercules-cli-mode-');
    const written = buildTarget('claude-code', out);
    for (const rel of written) {
      const mode = statSync(join(out, rel)).mode & 0o777;
      expect(mode.toString(8)).toBe('644');
    }
  });
});

describe('main', () => {
  it('--check exits 0 for a target already in sync with committed dist/', () => {
    // main() writes real dist/ when --check is absent, so this test only ever passes --check.
    const rc = main(['--target', 'claude-code', '--check']);
    expect(rc).toBe(0);
  });

  it('--check exits 0 for "all"', () => {
    // A full build+diff of all 6 real targets via the "all" alias — same CPU-contention reasoning as
    // checkTarget's own explicit timeout above.
    expect(main(['--check'])).toBe(0);
  }, 20_000);

  it('silently skips an unknown target rather than throwing', () => {
    expect(() => main(['--target', 'does-not-exist', '--check'])).not.toThrow();
    expect(main(['--target', 'does-not-exist', '--check'])).toBe(0);
  });

  it('accepts --target=<name> as well as --target <name>', () => {
    // Without this, --target=cursor falls through unmatched and silently defaults target to 'all' —
    // a correct-looking but wrong outcome for a typo, not a thrown error.
    expect(main(['--target=claude-code', '--check'])).toBe(0);
  });

  it('throws loudly on an unrecognized argument, rather than silently ignoring it', () => {
    expect(() => main(['--targett', 'claude-code'])).toThrow(/unrecognized argument/);
  });

  it('reports a stale build with instructions to fix it', () => {
    // main()'s optional `distRoot` param points the --check comparison at a scratch "committed" tree
    // instead of the real repo's dist/, so the stderr hint is exercised directly, not merely trusted.
    const distRoot = tmpDir('hercules-cli-main-stale-dist-');
    buildTarget('claude-code', join(distRoot, 'claude-code'));
    writeFileSync(join(distRoot, 'claude-code', 'settings.json'), 'STALE', 'utf-8');

    let stderr = '';
    const original = process.stderr.write.bind(process.stderr);
    process.stderr.write = ((chunk: string) => {
      stderr += chunk;
      return true;
    }) as typeof process.stderr.write;
    try {
      const rc = main(['--target', 'claude-code', '--check'], distRoot);
      expect(rc).not.toBe(0);
    } finally {
      process.stderr.write = original;
    }
    expect(stderr).toContain('make build');
  });
});

describe('every ecosystem the descriptors declare has a working serializer', () => {
  it('discover() and targets() agree on the same ecosystem set', () => {
    expect(Object.keys(discover(ECOSYSTEMS)).sort()).toEqual(targets());
  });

  it('the ecosystem list is sorted, not filesystem order', () => {
    expect(targets()).toEqual([...targets()].sort());
  });
});

describe('the generic build seam', () => {
  it('every build target has a registered serializer', () => {
    const registry = buildRegistry(Object.values(discover(ECOSYSTEMS)));
    for (const t of names(ECOSYSTEMS)) expect(registry.registeredTargets()).toContain(t);
  });

  it('cli.mts has no per-ecosystem branches', () => {
    // The whole point of the generic engine: dispatch happens through the descriptor, never on the
    // target name — enforced here as a source-text smell check.
    const src = readFileSync(join(repoRoot, 'src', 'builder', 'bin', 'cli.mts'), 'utf-8');
    expect(src).not.toMatch(/target ===/);
    expect(src).not.toContain("'opencode'");
    expect(src).not.toContain("'cursor'");
  });

  it('ExtrasContext is immutable at compile time only, not at runtime', () => {
    // TypeScript's `readonly` (see genExtras.mts's ExtrasContext interface) is erased entirely at
    // runtime; only `tsc` rejects the assignment below, which is why this is a type-level pin
    // (checked by `npx tsc -p tsconfig.tests.json --noEmit`) rather than a throw-assertion. Every
    // interface here (EcosystemDescriptor, RoleSpec, ...) carries the same compile-time-only guarantee.
    const ctx: ExtrasContext = {
      outRoot: '/tmp', sharedHooksSrc: '/tmp', srcContent: '/tmp', tokens: new Map(), version: '0.0.0',
    };
    // @ts-expect-error — readonly rejects this assignment at compile time; it still executes at
    // runtime (readonly has no runtime effect), so the assertion below checks the NEW value.
    ctx.outRoot = '/other';
    expect(ctx.outRoot).toBe('/other');
  });
});

describe('classifyDiff', () => {
  /**
   * The three cases need three different fixes, and the old failure text offered only one: it said
   * "regenerate it with `make build`", but `make build` never prunes — so a contributor following that
   * advice on a stray file was left with the file in place, the gate still red, and no idea which path
   * was at fault.
   */
  const scratch: string[] = [];
  const dir = (files: Record<string, string>): string => {
    const root = mkdtempSync(join(tmpdir(), 'hercules-classify-'));
    scratch.push(root);
    for (const [rel, body] of Object.entries(files)) writeFileSync(join(root, rel), body);
    return root;
  };
  afterEach(() => {
    for (const d of scratch.splice(0)) rmSync(d, { recursive: true, force: true });
  });

  it('calls a file present in dist but rendered by nothing a STRAY, and says to delete it', () => {
    const committed = dir({ 'a.md': 'x', 'STRAY.md': 'x' });
    const rendered = dir({ 'a.md': 'x' });
    const [line] = classifyDiff(committed, rendered, ['STRAY.md']);
    expect(line, 'a stray file is the one case `make build` cannot fix, so the message must say so')
      .toBe('STRAY.md — STRAY: present in dist/ but declared by no target; delete it');
  });

  it('calls a rendered file absent from dist MISSING, and points at make build', () => {
    const committed = dir({ 'a.md': 'x' });
    const rendered = dir({ 'a.md': 'x', 'b.md': 'x' });
    expect(classifyDiff(committed, rendered, ['b.md'])[0])
      .toBe('b.md — MISSING from dist/; `make build` writes it');
  });

  it('calls a file present in both but differing STALE', () => {
    const committed = dir({ 'a.md': 'old' });
    const rendered = dir({ 'a.md': 'new' });
    expect(classifyDiff(committed, rendered, ['a.md'])[0])
      .toBe('a.md — STALE content; `make build` refreshes it');
  });

  it('classifies every path it is handed, in order', () => {
    const committed = dir({ 'a.md': 'old', 'STRAY.md': 'x' });
    const rendered = dir({ 'a.md': 'new', 'b.md': 'x' });
    const lines = classifyDiff(committed, rendered, ['STRAY.md', 'a.md', 'b.md']);
    expect(lines.map((l) => l.split(' — ')[1]?.split(':')[0]?.split(' ')[0]))
      .toEqual(['STRAY', 'STALE', 'MISSING']);
  });
});
