import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, sep } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { parseDescriptor } from '../../descriptor.mjs';
import { readSource, write } from '../../emit.mjs';
import type { ExtrasContext } from '../../genExtras.mjs';
import { emitExtras } from '../../genExtras.mjs';
import { dest } from '../../genSerialize.mjs';
import { discoverSources } from '../../layout.mjs';
import { buildRegistry } from '../../serialize.mjs';
import { repoRoot } from '../../../commons/support/repo';

// The code-of-conduct keystone: "a target is one ecosystems/<name>.json file, never new TypeScript." A synthetic
// 7th ecosystem built only from vocabulary the closed descriptor schema accepts must compile end to end with zero
// changes to any .mts file. It hand-composes buildTarget's steps, so the checked-out repo is never mutated.

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
    agent: { mode: 'preserve', resolve_model_tier: true, required: ['name', 'description'] },
    command: { mode: 'preserve', resolve_model_tier: true },
    persona: { mode: 'preserve', resolve_model_tier: true },
    default: { mode: 'preserve', resolve_model_tier: true },
  },
  routes: [
    { kind: 'exact', src: 'capabilities.md', dest: 'CAPABILITIES.md' },
    { kind: 'exact', src: 'persona.md', dest: 'CLAUDE.md' },
  ],
  artifacts: [
    { dest: 'settings.json', content: { agent: 'hercules' } },
  ],
  guard: ['hercules_state.py', 'frozen_tests.py'],
};

const dirs: string[] = [];

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('a synthetic 7th ecosystem, built from existing vocabulary only', () => {
  it('parses, routes, serializes, and emits extras with zero .mts changes', () => {
    const descriptor = parseDescriptor('synthetic-ci', SYNTHETIC_RAW);
    const registry = buildRegistry([descriptor]);
    const srcContent = join(repoRoot, 'src', 'content');
    const sharedHooksSrc = join(repoRoot, 'src', 'hooks');
    const outRoot = mkdtempSync(join(tmpdir(), 'hercules-synthetic-'));
    dirs.push(outRoot);
    const tokens = new Map(Object.entries(descriptor.vars));
    const models = { 'synthetic-ci': descriptor.models };

    const written: string[] = [];
    for (const src of discoverSources(srcContent)) {
      const rel = relative(srcContent, src).split(sep).join('/');
      const d = dest(descriptor, rel);
      if (d === null) continue;
      write(join(outRoot, d), registry.serializeFile('synthetic-ci', readSource(src), tokens, models, rel));
      written.push(d);
    }
    const ctx: ExtrasContext = {
      outRoot, sharedHooksSrc, srcContent, tokens, version: '9.9.9',
    };
    written.push(...emitExtras(ctx, descriptor));

    // The two exact routes fired. Everything else falls through unrouted and still ships, under
    // its own content-relative name.
    expect(written).toContain('CAPABILITIES.md');
    expect(written).toContain('CLAUDE.md');
    expect(readFileSync(join(outRoot, 'CLAUDE.md'), 'utf-8')).toContain('Hercules');
    // The generic emitter fired too: the artifact and both guard modules.
    expect(written).toContain('settings.json');
    expect(written).toContain('hooks/hercules_state.py');
    expect(written).toContain('hooks/frozen_tests.py');
  });
});
