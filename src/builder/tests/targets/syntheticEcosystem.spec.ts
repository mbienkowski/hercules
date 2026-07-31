import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, sep } from 'node:path';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { discover, parseDescriptor } from '../../descriptor.mjs';
import type { EcosystemDescriptor } from '../../descriptor.mjs';
import { readSource, write } from '../../emit.mjs';
import type { ExtrasContext } from '../../genExtras.mjs';
import { emitExtras } from '../../genExtras.mjs';
import { dest } from '../../genSerialize.mjs';
import { discoverSources } from '../../layout.mjs';
import { buildRegistry } from '../../serialize.mjs';
import { filesUnder } from '../../../commons/support/buildTree';
import { repoRoot } from '../../../commons/support/repo';

// The code-of-conduct keystone: "a target is one ecosystems/<name>.json file, never new TypeScript." This is
// the generic-engine contract test: a synthetic 7th ecosystem, hand-composed from the closed descriptor
// vocabulary, exercises every role mode, field source, route kind, artifact form, gate protocol and template
// value kind AT LEAST ONCE. A real ecosystem's own conformance test only proves ITS OWN descriptor's choices;
// this file proves the ENGINE handles every choice the schema allows, independent of any one ecosystem. Real
// per-ecosystem specs then only need to cover facts the engine can't know (host-specific rendering contracts) —
// see CODE_OF_CONDUCT.md § Testing.
//
// `preserve` mode is the one role mode NOT exercised here: it is already dense in every one of the six real
// ecosystems' own conformance tests, so this file's marginal value there is near zero.
//
// It hand-composes buildTarget's steps directly (never `discover()`), so the checked-out repo's src/targets/
// directory is never touched — 'synthetic-ci' is never registered as a real target, build leg, or smoke leg.
// The one exception is `templates[0].src`, which deliberately points at the REAL, already-committed
// `opencode.template.plugin.js` (the only sibling file already exercising all four template value kinds) —
// safe because `renderTemplate` reads it by a literal path, never through the directory-layout scan that
// would otherwise reject an unregistered ecosystem name.

const SYNTHETIC_RAW = {
  schema: 1,
  name: 'synthetic-ci',
  vars: {
    product: 'Synthetic CI', host: 'Synthetic', ns: '/hercules:', instructions_file: 'CLAUDE.md',
    agent_ns: 'hercules:', plugin_root: '${SYNTHETIC_PLUGIN_ROOT}/', plan_enter: 'plan mode', plan_exit: 'approval',
  },
  models: { high: null, medium: null, low: null },
  smoke: { cli: 'synthetic', test: 'builder/tests/smoke/syntheticSmoke.spec.ts' },
  dispatch: 'path',
  roles: {
    // 'fields' mode, exercising all five field sources at once: frontmatter, stem, primary_mode
    // (true only for the one agent named 'hercules'), flag_if_name_in (same), literal.
    agent: {
      mode: 'fields',
      body: 'strip_newlines',
      fields: [
        { key: 'name', from: 'frontmatter', field: 'name' },
        { key: 'slug', from: 'stem' },
        { key: 'kind', from: 'primary_mode', primary: 'hercules' },
        { key: 'flagged', from: 'flag_if_name_in', names: ['hercules'], value: 'true' },
        { key: 'label', from: 'literal', value: 'agent' },
      ],
    },
    // 'toml_command' mode: exactly one field, 'description', sourced deterministically.
    command: {
      mode: 'toml_command',
      fields: [{ key: 'description', from: 'frontmatter', field: 'description' }],
    },
    // 'wrap' mode: an all-literal generated frontmatter block, the source's own frontmatter ignored.
    persona: {
      mode: 'wrap',
      fields: [{ key: 'title', from: 'literal', value: 'Synthetic' }],
    },
    // 'plain' mode: body only, no frontmatter at all — covers every file with no dedicated role
    // (protocols/*, skills/*), none of which carry frontmatter in the real content tree.
    default: { mode: 'plain' },
  },
  routes: [
    { kind: 'exact', src: 'capabilities.md', dest: 'CAPABILITIES.md' },
    { kind: 'exact', src: 'persona.md', dest: 'CLAUDE.md' },
    { kind: 'omit', src: 'protocols/debate-consensus-protocol.md' },
    { kind: 'suffix_swap', prefix: 'skills/', from_suffix: '.md', to_suffix: '.txt' },
    // Everything else (agents/*, commands/*, the remaining protocols) falls through unrouted and
    // still ships, under its own content-relative name — the identity fallback.
  ],
  artifacts: [
    { dest: 'settings.json', content: { agent: 'hercules' } },
    { dest: 'manifest.json', content: { version: '${version}' }, versioned: true },
  ],
  guard: ['hercules_state.py', 'frozen_tests.py'],
  gate: {
    protocol: 'event_guards',
    allow: { decision: 'allow' },
    deny: { decision: 'deny' },
    user_key: 'permission_decision',
    agent_key: 'permission_decision',
  },
  templates: [
    {
      src: 'opencode.template.plugin.js',
      dest: 'plugin.js',
      values: {
        '__DEFAULT_AGENT__': { from: 'js_string', value: 'hercules' },
        '__SKILLS_PATH__': { from: 'js_string', value: 'skills' },
        '__ASSET_LIST__': { from: 'js_string_list', values: ['CLAUDE.md'] },
        '__INSTRUCTION_JOINS__': { from: 'js_root_joins', paths: ['CLAUDE.md'] },
        '__AGENT_ENTRIES__': { from: 'role_entries_js', role: 'agent', body_key: 'body' },
        '__COMMAND_ENTRIES__': { from: 'role_entries_js', role: 'command', body_key: 'body' },
      },
    },
  ],
};

const dirs: string[] = [];
let descriptor: EcosystemDescriptor;
let outRoot: string;
let written: string[];

beforeAll(() => {
  descriptor = parseDescriptor('synthetic-ci', SYNTHETIC_RAW);
  const registry = buildRegistry([descriptor]);
  const srcContent = join(repoRoot, 'src', 'content');
  const sharedHooksSrc = join(repoRoot, 'src', 'hooks');
  const sharedToolsSrc = join(repoRoot, 'src', 'tools');
  outRoot = mkdtempSync(join(tmpdir(), 'hercules-synthetic-'));
  dirs.push(outRoot);
  const tokens = new Map(Object.entries(descriptor.vars));
  const models = { 'synthetic-ci': descriptor.models };

  written = [];
  for (const src of discoverSources(srcContent)) {
    const rel = relative(srcContent, src).split(sep).join('/');
    const d = dest(descriptor, rel);
    if (d === null) continue; // an `omit` route — this source ships nothing
    const text = readSource(src);
    write(join(outRoot, d), registry.serializeFile('synthetic-ci', text, tokens, models, rel));
    written.push(d);
  }
  const ctx: ExtrasContext = { outRoot, sharedHooksSrc, sharedToolsSrc, srcContent, tokens, version: '9.9.9' };
  written.push(...emitExtras(ctx, descriptor));
});

afterAll(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('a synthetic 7th ecosystem, built from existing vocabulary only', () => {
  it('parses, routes, serializes, and emits extras with zero .mts changes', () => {
    expect(written).toContain('CAPABILITIES.md');
    expect(written).toContain('CLAUDE.md');
    expect(readFileSync(join(outRoot, 'CLAUDE.md'), 'utf-8')).toContain('Hercules');
    expect(written).toContain('settings.json');
    expect(written).toContain('hooks/hercules_state.py');
    expect(written).toContain('hooks/frozen_tests.py');
  });

  it("'fields' mode computes every field source: frontmatter, stem, primary_mode, flag_if_name_in, literal", () => {
    const files = filesUnder(outRoot);
    const hercules = files['agents/hercules.md'] as string;
    expect(hercules, 'frontmatter field').toContain('name: hercules');
    expect(hercules, 'stem field').toContain('slug: hercules');
    expect(hercules, 'primary_mode true for the named primary').toContain('kind: primary');
    expect(hercules, 'flag_if_name_in true for a listed name').toContain('flagged: true');
    expect(hercules, 'literal field').toContain('label: agent');

    const other = files['agents/backend-engineer.md'] as string;
    expect(other, 'primary_mode false for every other agent').toContain('kind: subagent');
    expect(other, 'flag_if_name_in omits its key for an unlisted name').not.toContain('flagged:');
  });

  it("'toml_command' mode emits exactly the one deterministic field as TOML", () => {
    const files = filesUnder(outRoot);
    const build = files['commands/build.md'] as string;
    expect(build).toMatch(/^description = ".+"$/m);
  });

  it("'wrap' mode generates frontmatter from literals alone, ignoring the source's own", () => {
    const claude = readFileSync(join(outRoot, 'CLAUDE.md'), 'utf-8');
    expect(claude.startsWith('---\ntitle: Synthetic\n---\n\n')).toBe(true);
  });

  it("'plain' mode ships body only, no frontmatter, for every file with no dedicated role", () => {
    const files = filesUnder(outRoot);
    const protocol = files['protocols/a2a-communication-protocol.md'] as string;
    expect(protocol.startsWith('---')).toBe(false);
  });

  it("an 'omit' route drops its source entirely", () => {
    expect(written).not.toContain('protocols/debate-consensus-protocol.md');
    const files = filesUnder(outRoot);
    expect(files['protocols/debate-consensus-protocol.md']).toBeUndefined();
  });

  it("a 'suffix_swap' route renames the destination, content still flows through its role", () => {
    expect(written).toContain('skills/hercules-reference/SKILL.txt');
    expect(written).not.toContain('skills/hercules-reference/SKILL.md');
  });

  it('a non-versioned artifact ships its content verbatim', () => {
    const settings = JSON.parse(readFileSync(join(outRoot, 'settings.json'), 'utf-8')) as Record<string, unknown>;
    expect(settings).toEqual({ agent: 'hercules' });
  });

  it('a versioned artifact substitutes the single ${version} token', () => {
    const manifest = JSON.parse(readFileSync(join(outRoot, 'manifest.json'), 'utf-8')) as Record<string, unknown>;
    expect(manifest['version']).toBe('9.9.9');
  });

  it('the gate protocol ships verbatim as hooks/gate.json', () => {
    expect(written).toContain('hooks/gate.json');
    const gate = JSON.parse(readFileSync(join(outRoot, 'hooks', 'gate.json'), 'utf-8'));
    expect(gate).toEqual(descriptor.gate);
  });

  it('every template value kind renders: js_string, js_string_list, js_root_joins, role_entries_js', () => {
    expect(written).toContain('plugin.js');
    const plugin = readFileSync(join(outRoot, 'plugin.js'), 'utf-8');
    expect(plugin, 'js_string').toContain('cfg.default_agent = "hercules";');
    expect(plugin, 'js_string_list').toContain('for (const asset of ["CLAUDE.md"])');
    expect(plugin, 'js_root_joins').toContain('path.join(PLUGIN_ROOT, "CLAUDE.md")');
    // Bare identifier-safe keys render unquoted (see genExtras.mts's BARE_KEY test).
    expect(plugin, 'role_entries_js for the agent role').toContain('hercules: {');
    expect(plugin, 'role_entries_js for the command role').toContain('build: {');
  });

  it('reuses the real opencode template sibling without registering a fake ecosystem', () => {
    // The whole point of this route: no `src/targets/synthetic-ci.*` file exists, so `discover()`'s
    // directory-layout scan never sees 'synthetic-ci' and the real build, CI matrix and smoke suite
    // stay exactly six targets.
    expect(Object.keys(discover())).not.toContain('synthetic-ci');
  });
});
