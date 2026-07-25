import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, sep } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { parseDescriptor } from '../descriptor.mjs';
import { readSource, write } from '../emit.mjs';
import type { ExtrasContext } from '../genExtras.mjs';
import { emitExtras } from '../genExtras.mjs';
import { dest } from '../genSerialize.mjs';
import { discoverSources } from '../layout.mjs';
import { buildRegistry } from '../serialize.mjs';
import { repoRoot } from '../../commons/support/repo';

// The CoC keystone under test, and the plan's own verification step 7 for this migration: "a
// target is one ecosystems/<name>.json file, never new TypeScript." A synthetic 7th ecosystem,
// built ONLY from vocabulary the closed descriptor schema already accepts, must compile end to end
// with ZERO changes to any .mts file. This hand-composes the same steps buildTarget performs
// (rather than writing a real file into ecosystems/, which would mutate the checked-out repo)
// so the proof needs no filesystem write outside a scratch temp dir.

const SYNTHETIC_RAW = {
  schema: 1,
  name: 'synthetic-ci',
  vars: {
    product: 'Synthetic CI', host: 'Synthetic', ns: '/hercules:', instructions_file: 'CLAUDE.md',
    agent_ns: 'hercules:', plugin_root: '${SYNTHETIC_PLUGIN_ROOT}/', plan_enter: 'plan mode', plan_exit: 'approval',
  },
  models: { high: null, medium: null, low: null },
  smoke: { cli: 'synthetic', test: 'tests/build/test_synthetic_smoke.py' },
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

    // The two exact routes actually fired (only capabilities.md/persona.md are routed; everything
    // else identity-falls-through and is never claimed by an `exact`/`omit` route in this synthetic
    // descriptor, so it still ships, just under its own content-relative name).
    expect(written).toContain('CAPABILITIES.md');
    expect(written).toContain('CLAUDE.md');
    expect(readFileSync(join(outRoot, 'CLAUDE.md'), 'utf-8')).toContain('Hercules');
    // The generic emitter fired too: the artifact and both guard modules.
    expect(written).toContain('settings.json');
    expect(written).toContain('hooks/hercules_state.py');
    expect(written).toContain('hooks/frozen_tests.py');
  });
});
