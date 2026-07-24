import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { discover } from '../../scripts-ts/build/descriptor.mjs';
import type { ExtrasContext } from '../../scripts-ts/build/genExtras.mjs';
import { emitExtras, GenExtrasError, jsObjectLiteral, jsString, roleEntries } from '../../scripts-ts/build/genExtras.mjs';
import { ECOSYSTEMS } from '../support/descriptorFixtures';
import { repoRoot } from '../support/repo';

// Ported from tests/build/test_manifests.py plus new coverage for emitExtras' own branches
// (artifacts/siblings/guard/gate) that the thin Python file leaves to test_target_registry.py /
// test_opencode_commands.py / test_opencode_mirror.py — those three depend on cli.build_target,
// which isn't ported until commit 8, so their TS equivalents land there too. This file tests
// genExtras.mts's own exported surface directly, against the real shipped descriptors.

const DESCRIPTORS = discover(ECOSYSTEMS);
const SRC_CONTENT = join(repoRoot, 'src', 'content');
const SHARED_HOOKS_SRC = join(repoRoot, 'src', 'hooks');

describe('jsString', () => {
  it('escapes a double quote so generated code stays valid', () => {
    expect(jsString('a"b')).toBe('"a\\"b"');
  });

  it('keeps non-ASCII characters literal', () => {
    expect(jsString('a→b')).toBe('"a→b"');
  });
});

describe('jsObjectLiteral', () => {
  it('renders simple values as their native JavaScript equivalents', () => {
    expect(jsObjectLiteral(true)).toBe('true');
    expect(jsObjectLiteral(false)).toBe('false');
    expect(jsObjectLiteral(null)).toBe('null');
    expect(jsObjectLiteral(42)).toBe('42');
    expect(jsObjectLiteral('x')).toBe('"x"');
  });

  it('renders an empty map/object and an empty list as empty JS collections', () => {
    expect(jsObjectLiteral(new Map())).toBe('{}');
    expect(jsObjectLiteral({})).toBe('{}');
    expect(jsObjectLiteral([])).toBe('[]');
  });

  it('renders a list of strings as a comma-separated JS array', () => {
    expect(jsObjectLiteral(['a', 'b'])).toBe('["a", "b"]');
  });

  it('only quotes a property name when JavaScript requires it', () => {
    const out = jsObjectLiteral(new Map<string, number>([['ok_key', 1], ['needs:quote', 2]]));
    expect(out).toContain('ok_key: 1,');
    expect(out).toContain('"needs:quote": 2,');
  });

  it('accepts a plain object the same way it accepts a Map', () => {
    // The real caller (templateValue's role_entries_js branch) always builds a Map, for insertion
    // order; this branch exists for API parity with the Python original (a plain dict) and this
    // test — not a real call site with an integer-like key, see the function's own comment.
    expect(jsObjectLiteral({ ok_key: 1, 'needs:quote': 2 })).toContain('"needs:quote": 2,');
  });

  it('a plain object with an integer-like key diverges from Python — V8 reorders it first (documented, not parity-fixtured)', () => {
    // Verified directly against the real Python engine (python3 -m scripts.ci.parity_run):
    // js_object_literal({"b": 1, "1": "one", "a": 2, "0": "zero"}) there renders key order
    // b, 1, a, 0 (dict.items() preserves insertion order) — genuinely different from V8's below.
    // This is why the case is NOT a tests/testdata/parity/ fixture: make parity requires
    // byte-identical output across engines, and this input never produces that. See this file's
    // top-of-file comment for the full divergence writeup and why it's latent for every real caller
    // (the Map branch, used by every actual template value, is unaffected).
    const obj = { b: 1, '1': 'one', a: 2, '0': 'zero' };
    const out = jsObjectLiteral(obj);
    const keyOrder = [...out.matchAll(/"?([\w:]+)"?: /g)].map((m) => m[1]);
    expect(keyOrder).toEqual(['0', '1', 'b', 'a']);
  });
});

describe('the opencode.json artifact', () => {
  it('has the required top-level fields', () => {
    // Plain descriptor DATA now (an inline artifact) — pinned here reader-side, same as Python's
    // test_opencode_config_artifact_has_the_required_top_level_fields.
    const opencode = DESCRIPTORS['opencode'];
    const artifact = opencode?.artifacts.find((a) => a.dest === 'opencode.json');
    const cfg = artifact?.content as Record<string, unknown>;
    expect(cfg['$schema']).toBe('https://opencode.ai/config.json');
    expect(cfg['default_agent']).toBe('hercules');
    expect(cfg['instructions']).toBeTruthy();
    expect((cfg['skills'] as Record<string, unknown>)['paths']).toBeTruthy();
  });
});

describe('the plugin.js template is sibling data, not TypeScript', () => {
  it('lives as a data file under src/ecosystems/ and carries the JS write-gate wiring', () => {
    const template = join(repoRoot, 'src', 'ecosystems', 'opencode.template.plugin.js');
    expect(existsSync(template)).toBe(true);
    const text = readFileSync(template, 'utf-8');
    expect(text).toContain('__AGENT_ENTRIES__');
    expect(text).toContain('__COMMAND_ENTRIES__');
    expect(text).toContain('tool.execute.before');
  });
});

describe('roleEntries', () => {
  it('drops the name key and strips the rendered body', () => {
    const opencode = DESCRIPTORS['opencode'];
    if (opencode === undefined) throw new Error('opencode descriptor missing');
    const entries = roleEntries(opencode, SRC_CONTENT, new Map(Object.entries(opencode.vars)), 'agent');
    const backend = entries.find((e) => e.stem === 'backend-engineer');
    expect(backend).toBeDefined();
    expect(backend?.fields.has('name')).toBe(false);
    expect(backend?.body.startsWith('\n')).toBe(false);
    expect(backend?.body.endsWith('\n')).toBe(false);
  });
});

describe('emitExtras', () => {
  const dirs: string[] = [];

  function outDir(): string {
    const root = mkdtempSync(join(tmpdir(), 'hercules-genextras-'));
    dirs.push(root);
    return root;
  }

  afterEach(() => {
    while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
  });

  function ctxFor(name: string): ExtrasContext {
    const d = DESCRIPTORS[name];
    if (d === undefined) throw new Error(`${name} descriptor missing`);
    return {
      outRoot: outDir(),
      sharedHooksSrc: SHARED_HOOKS_SRC,
      srcContent: SRC_CONTENT,
      tokens: new Map(Object.entries(d.vars)),
      version: '9.9.9',
    };
  }

  it('emits a versioned artifact with the token substituted and a non-versioned one verbatim', () => {
    const d = DESCRIPTORS['claude-code'];
    if (d === undefined) throw new Error('claude-code descriptor missing');
    const ctx = ctxFor('claude-code');
    const written = emitExtras(ctx, d);
    expect(written).toContain('.claude-plugin/plugin.json');
    expect(written).toContain('settings.json');
    const plugin = readFileSync(join(ctx.outRoot, '.claude-plugin', 'plugin.json'), 'utf-8');
    expect(plugin).toContain('"9.9.9"');
    expect(plugin).not.toContain('${version}');
    const settings = readFileSync(join(ctx.outRoot, 'settings.json'), 'utf-8');
    expect(settings.endsWith('\n')).toBe(true);
  });

  it('copies the guard modules and emits hooks/gate.json for a gated ecosystem', () => {
    const d = DESCRIPTORS['cursor'];
    if (d === undefined) throw new Error('cursor descriptor missing');
    const ctx = ctxFor('cursor');
    const written = emitExtras(ctx, d);
    for (const module of d.guard) expect(written).toContain(`hooks/${module}`);
    expect(written).toContain('hooks/gate.json');
    const gate = JSON.parse(readFileSync(join(ctx.outRoot, 'hooks', 'gate.json'), 'utf-8')) as Record<string, unknown>;
    expect(gate).toEqual(d.gate);
  });

  it('copies the dist sibling files named after the ecosystem', () => {
    const d = DESCRIPTORS['cursor'];
    if (d === undefined) throw new Error('cursor descriptor missing');
    const ctx = ctxFor('cursor');
    const written = emitExtras(ctx, d);
    expect(written).toContain('README.md');
    expect(written).toContain('logo.svg');
    expect(existsSync(join(ctx.outRoot, 'README.md'))).toBe(true);
  });

  it('renders the opencode plugin template, embedding entries and resolving its own root', () => {
    const d = DESCRIPTORS['opencode'];
    if (d === undefined) throw new Error('opencode descriptor missing');
    const ctx = ctxFor('opencode');
    const written = emitExtras(ctx, d);
    expect(written).toContain('plugin.js');
    const js = readFileSync(join(ctx.outRoot, 'plugin.js'), 'utf-8');
    expect(js).toContain('PLUGIN_ROOT = path.resolve(__dirname)');
    expect(js).toContain('cfg.default_agent = "hercules"');
    expect(js).toContain('"hercules:discover"');
    expect(js).toContain('\n            mode: ');
    expect(js).toContain('\n            prompt: ');
    expect(js).toContain('\n            agent: "hercules",');
    expect(js).toContain('\n            template: ');
    expect(js).not.toContain('__AGENT_ENTRIES__');
    expect(js).not.toContain('__COMMAND_ENTRIES__');
  });

  it('fails loud when a versioned artifact carries zero or more than one ${version} token', () => {
    const zero = DESCRIPTORS['claude-code'];
    if (zero === undefined) throw new Error('claude-code descriptor missing');
    const withBadArtifact = {
      ...zero,
      artifacts: [{ dest: 'bad.json', content: { v: 'no token here' }, versioned: true }],
    };
    const ctx = ctxFor('claude-code');
    expect(() => emitExtras(ctx, withBadArtifact)).toThrow(GenExtrasError);
    expect(() => emitExtras(ctx, withBadArtifact)).toThrow(/expected exactly one \$\{version\} token/);
  });
});
