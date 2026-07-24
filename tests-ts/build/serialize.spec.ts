import { describe, expect, it } from 'vitest';

import { discover } from '../../scripts-ts/build/descriptor.mjs';
import { buildRegistry, SerializeError } from '../../scripts-ts/build/serialize.mjs';
import { ECOSYSTEMS } from '../support/descriptorFixtures';

// Ported from tests/build/test_serialize.py. Unlike Python's serialize.py (whose _REGISTRY is a
// module-scope singleton, bootstrapped by a plain `import`), buildRegistry() is an explicit
// factory — see serialize.mts's own top comment — so each test builds its OWN registry rather than
// mutating a shared global. That also means the extensibility test doesn't need to worry about
// polluting state for tests that run after it.

const MODELS = { 'claude-code': { high: 'opus', medium: 'sonnet', low: 'haiku' } };

function registry() {
  return buildRegistry(Object.values(discover(ECOSYSTEMS)));
}

describe('the claude-code serializer, via the registry', () => {
  it('translates model_tier to a concrete model name and writes fields in a fixed order', () => {
    const fm = new Map(Object.entries({
      name: 'challenger', description: 'd', model_tier: 'medium', tools: 'Read, Grep',
    }));
    const out = registry().get('claude-code').serializeAgent(fm, '# Challenger\n', new Map(), MODELS);
    expect(out).toBe(
      '---\nname: challenger\ndescription: d\nmodel: sonnet\ntools: Read, Grep\n---\n\n# Challenger\n',
    );
  });

  it('omits the tools field entirely when no tools list is given', () => {
    const fm = new Map(Object.entries({ name: 'hercules', description: 'd', model_tier: 'high' }));
    const out = registry().get('claude-code').serializeAgent(fm, '# Hercules\n', new Map(), MODELS);
    expect(out).not.toContain('\ntools:');
    expect(out).toContain('model: opus\n');
  });
});

describe('registry extensibility', () => {
  it('registers a new output format under its name and finds it again by that name', () => {
    const reg = registry();
    const stub = { target: 'stub-target', serializeAgent: () => '', serializeFile: () => '' };
    reg.register(stub);
    expect(reg.get('stub-target').target).toBe('stub-target');
    expect(reg.registeredTargets()).toContain('stub-target');
  });

  it('fails clearly when asking for an unregistered output format', () => {
    expect(() => registry().get('does-not-exist')).toThrow(SerializeError);
    expect(() => registry().get('does-not-exist')).toThrow(/does-not-exist/);
  });
});

describe('a missing required field fails with a helpful error', () => {
  it('names the missing field for claude-code', () => {
    const fm = new Map(Object.entries({ name: 'challenger' }));
    expect(() => registry().get('claude-code').serializeAgent(fm, '# Challenger\n', new Map(), MODELS))
      .toThrow(/description/);
  });

  it('names the missing field for opencode', () => {
    const fm = new Map(Object.entries({ description: 'd' }));
    expect(() => registry().get('opencode').serializeAgent(fm, '# X\n', new Map(), MODELS))
      .toThrow(/name/);
  });
});
