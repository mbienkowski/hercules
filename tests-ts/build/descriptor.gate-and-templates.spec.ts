import { describe, expect, it } from 'vitest';

import { parseDescriptor } from '../../scripts-ts/build/descriptor.mjs';
import { minimal } from '../support/descriptorFixtures';

// Split out of descriptor.spec.ts (CODE_OF_CONDUCT.md's 500-line test-file cap) — see that file's
// header comment for the full split rationale. This file owns the two smallest cohesive shape
// groups: malformed template values (checked directly, not via a rejection-message table) and both
// gate protocols' full positive-path parse.

describe('rejecting malformed template values directly', () => {
  it('a template value that is not an object is rejected', () => {
    // Exact message (not a substring): "must be an object" alone is shared by several other,
    // unrelated fail() sites in this file (role/artifact/gate/'a template'/'a field spec' all use
    // it too) — a substring check here can't tell a mutant that drops or corrupts the placeholder
    // name apart from one that leaves it intact.
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { __X__: 'not-an-object' } }];
    expect(() => parseDescriptor('eco', minimal({ templates: tpl })))
      .toThrow("ecosystem descriptor 'eco': template value '__X__' must be an object, got 'not-an-object'");
  });

  it('js_string_list requires a non-empty values array', () => {
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __X__: { from: 'js_string_list', values: [] } },
    }];
    expect(() => parseDescriptor('eco', minimal({ templates: tpl })))
      .toThrow("ecosystem descriptor 'eco': template value '__X__' 'values' must be a non-empty list");
  });

  it('js_root_joins requires a non-empty paths array', () => {
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __X__: { from: 'js_root_joins', paths: [] } },
    }];
    expect(() => parseDescriptor('eco', minimal({ templates: tpl })))
      .toThrow("ecosystem descriptor 'eco': template value '__X__' 'paths' must be a non-empty list");
  });

  it("role_entries_js defaults 'drop' to an empty list when the key is entirely absent", () => {
    // The "requires 'body_key'" test elsewhere always omits 'drop' too, but it throws before
    // returning — no test constructs a SUCCESSFUL role_entries_js parse with 'drop' omitted to
    // prove the resulting `.drop` is actually `[]` and not some other placeholder.
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __X__: { from: 'role_entries_js', role: 'agent', body_key: 'b' } },
    }];
    const { templates } = parseDescriptor('eco', minimal({ templates: tpl }));
    expect(templates[0]?.values['__X__']?.drop).toEqual([]);
  });

  it("role_entries_js 'drop' must be a list, not merely have string entries", () => {
    // Every existing 'drop' test supplies an actual array (empty, or with a bad entry) — none
    // exercised `drop` being present but not an array at all (e.g. a bare string).
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __X__: { from: 'role_entries_js', role: 'agent', drop: 'not-a-list', body_key: 'b' } },
    }];
    expect(() => parseDescriptor('eco', minimal({ templates: tpl })))
      .toThrow("ecosystem descriptor 'eco': template value '__X__' 'drop' must be a list");
  });
});

describe('parsing the gate section exactly, for both protocols', () => {
  it('pre_tool: returns every field verbatim, including the optional ones', () => {
    const gate = {
      protocol: 'pre_tool',
      tools: { edit: 'Edit', write: 'Write' },
      path_keys: ['path', 'file_path'],
      nested_keys: ['edits'],
      deny: { decision: 'block' },
      allow: { decision: 'approve' },
      reason_key: 'reason',
    };
    expect(parseDescriptor('eco', minimal({ gate })).gate).toEqual({
      protocol: 'pre_tool',
      tools: { edit: 'Edit', write: 'Write' },
      path_keys: ['path', 'file_path'],
      nested_keys: ['edits'],
      deny: { decision: 'block' },
      allow: { decision: 'approve' },
      reason_key: 'reason',
    });
  });

  it('pre_tool: still returns a valid gate when the optional fields are absent', () => {
    const gate = {
      protocol: 'pre_tool', tools: { edit: 'Edit' }, path_keys: ['path'],
      deny: { decision: 'block' }, reason_key: 'reason',
    };
    expect(parseDescriptor('eco', minimal({ gate })).gate).toEqual({
      protocol: 'pre_tool', tools: { edit: 'Edit' }, path_keys: ['path'],
      deny: { decision: 'block' }, reason_key: 'reason',
    });
  });

  it('event_guards: returns every field verbatim', () => {
    const gate = {
      protocol: 'event_guards',
      allow: { permission: 'allow' },
      deny: { permission: 'deny' },
      user_key: 'command',
      agent_key: 'agent',
    };
    expect(parseDescriptor('eco', minimal({ gate })).gate).toEqual({
      protocol: 'event_guards',
      allow: { permission: 'allow' },
      deny: { permission: 'deny' },
      user_key: 'command',
      agent_key: 'agent',
    });
  });

  it('returns null when no gate is configured at all', () => {
    expect(parseDescriptor('eco', minimal()).gate).toBeNull();
  });
});
