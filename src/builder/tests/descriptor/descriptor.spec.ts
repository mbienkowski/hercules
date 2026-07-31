import { describe, expect, it } from 'vitest';

import { DescriptorError, discover, names, parseDescriptor } from '../../descriptor.mjs';
import { ECOSYSTEMS, expectMessage, minimal } from '../../../commons/support/descriptorFixtures';
import { readRepoJson } from '../../../commons/support/repo';

// The smoke-level contract: the error class's shape, the seven shipped ecosystems loading cleanly,
// two deliberate strictness choices, and one deep LOCK of every construction branch. Rejection
// messages are asserted in the sibling descriptor.*.spec.ts files.

describe('DescriptorError', () => {
  it("carries the name 'DescriptorError', not the generic 'Error'", () => {
    // `toThrow(DescriptorError)` asserts `instanceof`, which never consults `.name`. Code that
    // branches on `err.name` instead (e.g. across a serialization boundary) needs this explicit pin.
    expect(new DescriptorError('x').name).toBe('DescriptorError');
  });
});

describe('the seven real, shipped ecosystem descriptors', () => {
  it('all seven load and the registry keys them by filename stem', () => {
    const found = discover(ECOSYSTEMS);
    expect(Object.keys(found).sort()).toEqual([
      'claude-code', 'codex', 'copilot-cli', 'cursor', 'gemini-cli', 'grok-build', 'opencode',
    ]);
    for (const [name, desc] of Object.entries(found)) expect(desc.name).toBe(name);
  });

  it('pins the model tier map: claude-code carries real models, the rest inherit', () => {
    const found = discover(ECOSYSTEMS);
    expect(found['claude-code']?.models).toEqual({ high: 'opus', medium: 'sonnet', low: 'haiku' });
    for (const name of ['opencode', 'cursor', 'grok-build', 'gemini-cli', 'copilot-cli', 'codex']) {
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
      'claude-code', 'codex', 'copilot-cli', 'cursor', 'gemini-cli', 'grok-build', 'opencode',
    ]);
  });
});

describe('two decoded-JSON quirks this schema deliberately rejects', () => {
  it('requires schema to be exactly the number 1, rejecting boolean true', () => {
    // `schema` must be the literal number 1; a boolean is not accepted. The exact-message match
    // (Vitest's `.toThrow(string)` is only a substring check) pins show()'s lowercase `true`.
    expectMessage(() => minimal({ schema: true }), "ecosystem descriptor \"eco\": schema: must be 1, got true");
  });

  it('rejects a list-shaped enum value cleanly instead of crashing on it', () => {
    // Zod's enum matching rejects a list-shaped value cleanly instead of crashing. The assertions
    // are deliberately separate: the first pins the ERROR CLASS, the second the full message.
    expect(() => parseDescriptor('eco', minimal({ dispatch: ['a', 'b'] }))).toThrow(DescriptorError);
    expectMessage(
      () => minimal({ dispatch: ['a', 'b'] }),
      "ecosystem descriptor \"eco\": dispatch: must be one of [\"frontmatter\",\"path\"], got [\"a\",\"b\"]",
    );
  });
});

describe('accepting the maximal valid shape', () => {
  it('parses every field generator, route kind, and template value kind into the EXACT expected shape', () => {
    // An exhaustive equality check rather than a spot check: it pins every generator's returned
    // object, every default value, and both gate protocols. Input and expected output live in
    // builder/tests/testdata/descriptor/maximal-valid-shape.*.json to respect the test-size caps.
    const overrides = readRepoJson<Record<string, unknown>>('src/builder/tests/testdata/descriptor/maximal-valid-shape.overrides.json');
    const expected = readRepoJson('src/builder/tests/testdata/descriptor/maximal-valid-shape.expected.json');
    expect(parseDescriptor('eco', minimal(overrides))).toEqual(expected);
  });
});
