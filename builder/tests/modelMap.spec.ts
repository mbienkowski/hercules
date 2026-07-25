import { describe, expect, it } from 'vitest';

import { ModelMapError, resolve } from '../modelMap.mjs';

const FULL = { 'claude-code': { high: 'opus', medium: 'sonnet', low: 'haiku' } };

describe('choosing which model a target uses for a tier', () => {
  it('uses the model configured for that exact tier', () => {
    expect(resolve(FULL, 'claude-code', 'medium')).toBe('sonnet');
  });

  it('falls back to a MORE capable tier when the requested one is unset', () => {
    // Falling back downward would quietly run a demanding agent on a cheaper model. The direction
    // of this fallback is the whole safety property.
    expect(resolve({ 'claude-code': { high: 'opus' } }, 'claude-code', 'low')).toBe('opus');
    expect(resolve({ 'claude-code': { high: 'opus' } }, 'claude-code', 'medium')).toBe('opus');
  });

  it('prefers the nearest higher tier over the highest one', () => {
    expect(
      resolve({ t: { high: 'H', medium: 'M' } }, 't', 'low'),
    ).toBe('M');
  });

  it('never falls back DOWN to a lower tier that happens to be configured', () => {
    // Fallback only ever moves toward higher capability. Asking for 'high' when only a lower
    // 'low' tier is configured must not silently hand back the weaker model — it must report no
    // selection, the same as if nothing were configured at all.
    expect(resolve({ t: { low: 'L' } }, 't', 'high')).toBeNull();
  });

  it('treats a tier configured as null as "omit the field", not as unset', () => {
    // Presence, not truthiness. A null must STOP the fallback: it is a deliberate instruction to
    // emit no model field, and falling through to a higher tier would override that.
    expect(resolve({ 'claude-code': { high: 'opus', low: null } }, 'claude-code', 'low')).toBeNull();
  });

  it('returns nothing when the target configures no tier at all', () => {
    expect(resolve({ 'claude-code': {} }, 'claude-code', 'high')).toBeNull();
  });
});

describe('refusing a lookup that cannot be satisfied', () => {
  it('names the offending tier when it is not one of the three', () => {
    expect(() => resolve(FULL, 'claude-code', 'enormous')).toThrow(ModelMapError);
    expect(() => resolve(FULL, 'claude-code', 'enormous')).toThrow("unknown tier: 'enormous'");
  });

  it('names the offending target when it is configured nowhere', () => {
    // A silent null here would ship an agent with no model field and no explanation.
    expect(() => resolve(FULL, 'nope', 'high')).toThrow(
      "target not configured in any models map: 'nope'",
    );
  });
});

describe('identifying its own failures', () => {
  it('names model-map errors as such', () => {
    try {
      resolve(FULL, 'claude-code', 'nope');
      expect.unreachable('should have thrown');
    } catch (error) {
      expect((error as Error).name).toBe('ModelMapError');
    }
  });
});
