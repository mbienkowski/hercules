import { describe, expect, it } from 'vitest';

import { parseDescriptor } from '../../descriptor.mjs';
import { expectMessage, minimal } from '../../../commons/support/descriptorFixtures';

// Malformed template values and both gate protocols' full positive-path parse. Rejections use the
// shared `expectMessage` helper, not `expect(fn).toThrow(string)` — that is a SUBSTRING check in
// Vitest and would let a message-suffix mutation pass undetected.

describe('rejecting malformed template values directly', () => {
  it('a template value that is not an object is rejected', () => {
    // A discriminatedUnion's `invalid_type` ("not an object") is distinct from `invalid_union`
    // ("discriminant didn't match"); both report through discriminantError and must name the value.
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { __X__: 'not-an-object' } }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor \"eco\": templates[0].values.__X__: 'from' must be one of " +
        "[\"js_root_joins\",\"js_string\",\"js_string_list\",\"role_entries_js\"], got \"not-an-object\"",
    );
  });

  it('js_string_list requires a non-empty values array', () => {
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __X__: { from: 'js_string_list', values: [] } },
    }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor \"eco\": templates[0].values.__X__.values: 'values' must be a non-empty list",
    );
  });

  it("js_string_list's values must be a list at all, not merely have entries", () => {
    // One z.array().min(1) has two error sources: the empty-array test above exercises .min(1),
    // this exercises the array's own type check.
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __X__: { from: 'js_string_list', values: 'not-an-array' } },
    }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor \"eco\": templates[0].values.__X__.values: 'values' must be a non-empty list",
    );
  });

  it('js_root_joins requires a non-empty paths array', () => {
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __X__: { from: 'js_root_joins', paths: [] } },
    }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor \"eco\": templates[0].values.__X__.paths: 'paths' must be a non-empty list",
    );
  });

  it("js_root_joins's paths must be a list at all, not merely have entries", () => {
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __X__: { from: 'js_root_joins', paths: 'not-an-array' } },
    }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor \"eco\": templates[0].values.__X__.paths: 'paths' must be a non-empty list",
    );
  });

  it("role_entries_js defaults 'drop' to an empty list when the key is entirely absent", () => {
    // The "requires 'body_key'" test omits 'drop' too but throws before returning, so this is the
    // only SUCCESSFUL parse proving the resulting `.drop` is actually `[]`.
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __X__: { from: 'role_entries_js', role: 'agent', body_key: 'b' } },
    }];
    const { templates } = parseDescriptor('eco', minimal({ templates: tpl }));
    expect(templates[0]?.values['__X__']?.drop).toEqual([]);
  });

  it("role_entries_js 'drop' must be a list, not merely have string entries", () => {
    // Every other 'drop' test supplies a real array (empty, or with a bad entry); this covers
    // 'drop' being present but not an array at all.
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __X__: { from: 'role_entries_js', role: 'agent', drop: 'not-a-list', body_key: 'b' } },
    }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor \"eco\": templates[0].values.__X__.drop: 'drop' must be a list",
    );
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
