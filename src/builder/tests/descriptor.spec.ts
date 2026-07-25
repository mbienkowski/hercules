import { describe, expect, it } from 'vitest';

import { DescriptorError, discover, names, parseDescriptor } from '../descriptor.mjs';
import { ECOSYSTEMS, expectMessage, minimal } from '../../tests/support/descriptorFixtures';
import { readRepoJson } from '../../tests/support/repo';

// Covers the smoke-level contract only: the error class's own shape, the six real shipped
// ecosystems loading cleanly, the two Python-quirk divergences this port deliberately keeps, and
// one deep LOCK of every construction branch via a fixture pair. Every rejection-message assertion
// lives in a sibling file — split out of what was one 1200+ line file, per CODE_OF_CONDUCT.md's
// 500-line test-file cap:
//   - descriptor.malformed.spec.ts          multi-problem reporting, closed-vocabulary shapes
//   - descriptor.axes.spec.ts                one rejection per axis, checkKeys per-shape "what" label
//   - descriptor.fields.spec.ts              checkStr/checkRelPath sites, defaults, cross-field rules
//   - descriptor.gate-and-templates.spec.ts  malformed template values, both gate protocols' full parse
//   - descriptor.filesystem.spec.ts          discover/load/distFiles against real temp directories
//   - descriptorSort.spec.ts                 the vi.mock('node:fs')-based sort-order proof (pre-existing)
// All six import their shared fixtures (minimal/withAgentRole/expectMessage/ECOSYSTEMS) from
// tests/support/descriptorFixtures.ts rather than redefining them. Since commit 5, error message
// TEXT is no longer required to be byte-identical to the Python original (see descriptor.mts's own
// top-of-file comment) — these files pin Zod's own path-aware messages instead.

describe('DescriptorError', () => {
  it("carries the name 'DescriptorError', not the generic 'Error'", () => {
    // `toThrow(DescriptorError)` elsewhere in this suite only asserts `instanceof` — it would still
    // pass even if the `override readonly name = 'DescriptorError'` class field were deleted or its
    // string mutated, since `instanceof` doesn't consult `.name` at all. Code that branches on
    // `err.name` (rather than `instanceof`, e.g. across a serialization boundary) depends on this
    // directly, so it gets its own explicit assertion.
    expect(new DescriptorError('x').name).toBe('DescriptorError');
  });
});

describe('the six real, shipped ecosystem descriptors', () => {
  it('all six load and the registry keys them by filename stem', () => {
    const found = discover(ECOSYSTEMS);
    expect(Object.keys(found).sort()).toEqual([
      'claude-code', 'copilot-cli', 'cursor', 'gemini-cli', 'grok-build', 'opencode',
    ]);
    for (const [name, desc] of Object.entries(found)) expect(desc.name).toBe(name);
  });

  it('pins the model tier map: claude-code carries real models, the rest inherit', () => {
    const found = discover(ECOSYSTEMS);
    expect(found['claude-code']?.models).toEqual({ high: 'opus', medium: 'sonnet', low: 'haiku' });
    for (const name of ['opencode', 'cursor', 'grok-build', 'gemini-cli', 'copilot-cli']) {
      expect(found[name]?.models).toEqual({ high: null, medium: null, low: null });
    }
  });

  it('pins the load-bearing token vars the content render depends on', () => {
    const found = discover(ECOSYSTEMS);
    expect(found['claude-code']?.vars['plan_exit']).toBe('ExitPlanMode');
    expect(found['gemini-cli']?.vars['instructions_file']).toBe('GEMINI.md');
    expect(found['opencode']?.vars['plugin_root']).toBe('');
  });

  it('names is the sorted list discover() produces, deriving the CLI target set', () => {
    expect(names(ECOSYSTEMS)).toEqual([
      'claude-code', 'copilot-cli', 'cursor', 'gemini-cli', 'grok-build', 'opencode',
    ]);
  });
});

describe('the two Python quirks this port deliberately does not replicate', () => {
  it('requires schema to be exactly the number 1, not Python’s bool-is-int true', () => {
    // Python's `True != 1` is False (bool is an int subclass there), so `schema: true` would
    // ambiguously pass Python's check. This port does not special-case it: schema must be the
    // literal number 1. Exact message (not a substring, via expectMessage's try/catch + toBe —
    // `.toThrow(string)` is a substring/containment check in Vitest and would not catch a mutant
    // that merely appends content after this text): pins that a rejected boolean still renders as
    // Python's `True`/`False` via pyReprValue, not JS's lowercase `true`/`false`.
    expectMessage(() => minimal({ schema: true }), "ecosystem descriptor 'eco': schema: must be 1, got True");
  });

  it('rejects a list-shaped enum value cleanly instead of crashing on it', () => {
    // The Python original's `x not in <set>` check raises an unhandled TypeError for an unhashable
    // value (list/dict) rather than a DescriptorError. Zod's own enum/literal matching never has
    // that failure mode regardless of input type. The instanceof check and the exact-message check
    // are deliberately separate assertions: the first pins the ERROR CLASS this port throws instead
    // of crashing, the second (via expectMessage, not `.toThrow(string)` — see the sibling test's
    // comment) pins the full message.
    expect(() => parseDescriptor('eco', minimal({ dispatch: ['a', 'b'] }))).toThrow(DescriptorError);
    expectMessage(
      () => minimal({ dispatch: ['a', 'b'] }),
      "ecosystem descriptor 'eco': dispatch: must be one of ['frontmatter', 'path'], got ['a', 'b']",
    );
  });
});

describe('accepting the maximal valid shape', () => {
  it('parses every field generator, route kind, and template value kind into the EXACT expected shape', () => {
    // A deep, exhaustive equality check, not a spot check on a few fields: this is what actually
    // pins every construction branch (every generator's returned object, every default value, both
    // gate protocols) rather than leaving most of them free to drift unnoticed. Input and expected
    // output live in builder/tests/testdata/descriptor/maximal-valid-shape.*.json (CoC's 20-line
    // test / 500-line file caps — this fixture inline was 250+ lines by itself) and were
    // independently proven correct against the Python original by the 137 parity fixtures under
    // tests/testdata/parity/ (long since deleted with the Python compiler) — this test's job is to
    // LOCK the shape, not to (re-)establish it.
    const overrides = readRepoJson<Record<string, unknown>>('src/builder/tests/testdata/descriptor/maximal-valid-shape.overrides.json');
    const expected = readRepoJson('src/builder/tests/testdata/descriptor/maximal-valid-shape.expected.json');
    expect(parseDescriptor('eco', minimal(overrides))).toEqual(expected);
  });
});
