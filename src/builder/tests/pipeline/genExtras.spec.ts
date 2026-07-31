import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { discover } from '../../descriptor.mjs';
import type { EcosystemDescriptor } from '../../descriptor.mjs';
import type { ExtrasContext } from '../../genExtras.mjs';
import { emitExtras, GenExtrasError, jsObjectLiteral, jsString, roleEntries } from '../../genExtras.mjs';
import { ECOSYSTEMS } from '../../../commons/support/descriptorFixtures';
import { repoRoot } from '../../../commons/support/repo';

// Tests genExtras.mts's own exported surface — including emitExtras' artifacts/siblings/guard/gate
// branches — directly, against the real shipped descriptors.

const DESCRIPTORS = discover(ECOSYSTEMS);
const SRC_CONTENT = join(repoRoot, 'src', 'content');
const SHARED_HOOKS_SRC = join(repoRoot, 'src', 'hooks');
const SHARED_TOOLS_SRC = join(repoRoot, 'src', 'tools');

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
    // order; the plain-object branch exists for API parity and is reached only from this test.
    expect(jsObjectLiteral({ ok_key: 1, 'needs:quote': 2 })).toContain('"needs:quote": 2,');
  });

  it('separates multiple plain-object entries with a real newline, not a bare concatenation', () => {
    // Same distinction as the Map branch's own join test above, but for the plain-object branch's
    // separate recursive call site.
    const out = jsObjectLiteral({ a: '1', b: '2' });
    expect(out).toContain('"1",\n');
    expect(out.split('\n')).toHaveLength(4); // "{", "  a: ...,", "  b: ...,", "}"
  });

  it('indents a nested plain-object value one level deeper, not shallower', () => {
    // Same distinction as the Map branch's own nesting test above, but for the plain-object
    // branch's separate recursive call site (a separate mutant site from the Map branch's).
    const out = jsObjectLiteral({ outer: { inner: 'v' } }, 4);
    expect(out).toContain('\n        inner: "v",\n');
    expect(out).toContain('\n      },\n');
  });

  it('a plain object with an integer-like key is reordered first by V8', () => {
    // V8 hoists integer-like keys ahead of the rest, so this input can never render byte-identically
    // across engines — which is why it is pinned here rather than as a tests/testdata/parity/
    // fixture (those require byte-identical output). Latent for every real caller: the Map branch,
    // used by every actual template value, is unaffected.
    const obj = { b: 1, '1': 'one', a: 2, '0': 'zero' };
    const out = jsObjectLiteral(obj);
    const keyOrder = [...out.matchAll(/"?([\w:]+)"?: /g)].map((m) => m[1]);
    expect(keyOrder).toEqual(['0', '1', 'b', 'a']);
  });

  it('separates multiple entries with a real newline, not a bare concatenation', () => {
    // Content alone doesn't distinguish items.join('\n') from items.join('') UNLESS there are at
    // least two entries and the assertion checks for the newline explicitly.
    const out = jsObjectLiteral(new Map([['a', '1'], ['b', '2']]));
    expect(out).toContain('"1",\n');
    expect(out.split('\n')).toHaveLength(4); // "{", "  a: ...,", "  b: ...,", "}"
  });

  it('indents a nested map one level deeper inside an array element, not shallower', () => {
    // Distinguishes indent + 2 from indent - 2 in the array branch's recursive call: at this
    // non-default starting indent, decrementing still yields valid (non-negative) spacing, so only
    // an exact space count proves which direction indent moved.
    const out = jsObjectLiteral([new Map([['k', 'v']])], 4);
    // Outer array item is rendered at indent 4+2=6; its own nested entry line is prefixed with
    // that nested "spaces" (6) plus the literal "  " the entry-line template always adds = 8.
    expect(out).toContain('\n        k: "v",\n');
    expect(out).toContain('\n      }]');
  });

  it('indents a nested map one level deeper inside a map value, not shallower', () => {
    // Same proof as above for the map/object branch's own recursive call (a separate mutant site).
    const out = jsObjectLiteral(new Map([['outer', new Map([['inner', 'v']])]]), 4);
    expect(out).toContain('\n        inner: "v",\n');
    expect(out).toContain('\n      },\n');
  });
});

describe('the opencode.json artifact', () => {
  it('has the required top-level fields', () => {
    // The config is plain descriptor data (an inline artifact); this pins it reader-side.
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
  it('lives as a data file under ecosystems/ and carries the JS write-gate wiring', () => {
    const template = join(repoRoot, 'src', 'targets', 'opencode.template.plugin.js');
    expect(existsSync(template)).toBe(true);
    const text = readFileSync(template, 'utf-8');
    expect(text).toContain('__AGENT_ENTRIES__');
    expect(text).toContain('__COMMAND_ENTRIES__');
    expect(text).toContain('tool.execute.before');
  });
});

describe('roleEntries', () => {
  const dirs: string[] = [];

  afterEach(() => {
    while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
  });

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

  it('only collects .md files, ignoring any other file the directory happens to hold', () => {
    // Every real content/agents entry is already a .md file, so this can only be proven with a
    // synthetic directory that deliberately mixes in a non-.md sibling.
    const root = mkdtempSync(join(tmpdir(), 'hercules-role-entries-'));
    dirs.push(root);
    const agentsDir = join(root, 'agents');
    mkdirSync(agentsDir, { recursive: true });
    writeFileSync(
      join(agentsDir, 'real.md'),
      '---\nname: real\ndescription: d\nmodel_tier: medium\ntools: Read\n---\nbody\n',
      'utf-8',
    );
    writeFileSync(join(agentsDir, 'README.txt'), 'not a role file', 'utf-8');
    const opencode = DESCRIPTORS['opencode'];
    if (opencode === undefined) throw new Error('opencode descriptor missing');
    const entries = roleEntries(opencode, root, new Map(Object.entries(opencode.vars)), 'agent');
    expect(entries.map((e) => e.stem)).toEqual(['real']);
  });

  it('does not crash when a role has no field spec at all, falling back to no computed fields', () => {
    // Every real descriptor defines every role roleEntries is called with, so only a descriptor that
    // deliberately omits one reaches this. Proves the `?.` on `descriptor.roles[role]` is
    // load-bearing: without it, reading `.fields` off the missing roleSpec throws.
    const opencode = DESCRIPTORS['opencode'];
    if (opencode === undefined) throw new Error('opencode descriptor missing');
    const withNoRoles: EcosystemDescriptor = { ...opencode, roles: {} };
    expect(() =>
      roleEntries(withNoRoles, SRC_CONTENT, new Map(Object.entries(opencode.vars)), 'agent'),
    ).not.toThrow();
    const entries = roleEntries(withNoRoles, SRC_CONTENT, new Map(Object.entries(opencode.vars)), 'agent');
    expect(entries.length).toBeGreaterThan(0); // files are still enumerated
    expect([...(entries[0]?.fields.keys() ?? ['not empty'])]).toEqual([]); // but no fields computed
  });

  it('throws a role-naming error for a role with no source subdirectory, not a bare TypeError', () => {
    // The schema admits role names (persona/default) that ROLE_SUBDIRS does not map to a directory;
    // reaching roleEntries with one must fail naming the role, not crash in join() with a TypeError.
    const opencode = DESCRIPTORS['opencode'];
    if (opencode === undefined) throw new Error('opencode descriptor missing');
    expect(() =>
      roleEntries(opencode, SRC_CONTENT, new Map(Object.entries(opencode.vars)), 'persona'),
    ).toThrow(/role 'persona' has no source subdirectory/);
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
      sharedToolsSrc: SHARED_TOOLS_SRC,
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

  it('names its own failures as such', () => {
    const zero = DESCRIPTORS['claude-code'];
    if (zero === undefined) throw new Error('claude-code descriptor missing');
    const withBadArtifact = {
      ...zero,
      artifacts: [{ dest: 'bad.json', content: { v: 'no token here' }, versioned: true }],
    };
    const ctx = ctxFor('claude-code');
    try {
      emitExtras(ctx, withBadArtifact);
      expect.unreachable('should have thrown');
    } catch (error) {
      expect((error as Error).name).toBe('GenExtrasError');
    }
  });

  it('falls back to no key prefix when a template value leaves it unset (null), not a filler string', () => {
    // Every real descriptor's role_entries_js key_prefix is a defined string ("" or "hercules:"), so
    // forcing `null` here is the only way to reach the `spec.keyPrefix ?? ''` fallback the nullable
    // schema type requires.
    const opencode = DESCRIPTORS['opencode'];
    if (opencode === undefined) throw new Error('opencode descriptor missing');
    const template = opencode.templates[0];
    if (template === undefined) throw new Error('opencode template missing');
    const agentEntries = template.values['__AGENT_ENTRIES__'];
    if (agentEntries === undefined) throw new Error('__AGENT_ENTRIES__ value missing');
    const withNullPrefix = {
      ...opencode,
      templates: [
        { ...template, values: { ...template.values, __AGENT_ENTRIES__: { ...agentEntries, keyPrefix: null } } },
      ],
    };
    const ctx = ctxFor('opencode');
    emitExtras(ctx, withNullPrefix);
    const js = readFileSync(join(ctx.outRoot, 'plugin.js'), 'utf-8');
    // "backend-engineer" is not a bare-identifier-safe key (hyphen), so it renders quoted; a filler
    // prefix would land INSIDE that same quoted string, ahead of the stem, breaking this exact match.
    expect(js).toContain('"backend-engineer":');
  });
});
