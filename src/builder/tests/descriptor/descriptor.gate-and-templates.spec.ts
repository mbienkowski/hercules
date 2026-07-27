import { describe, expect, it } from 'vitest';

import { parseDescriptor } from '../../descriptor.mjs';
import { expectMessage, minimal } from '../../../commons/support/descriptorFixtures';

// Split out of descriptor.spec.ts (CODE_OF_CONDUCT.md's 500-line test-file cap) — see that file's
// header comment for the full split rationale. This file owns the two smallest cohesive shape
// groups: malformed template values (checked directly, not via a rejection-message table) and both
// gate protocols' full positive-path parse.
//
// Every rejection below goes through the shared `expectMessage` helper (try/catch + `toBe`), not
// bare `expect(fn).toThrow(string)` — `.toThrow(string)` is a SUBSTRING/containment check in
// Vitest, not exact equality, so it does not back the "exact message, not a substring" claim these
// tests make about themselves. Caught by review: an earlier draft of this file used `.toThrow(
// string)` throughout, and a live mutation experiment (appending a suffix to every message in
// `formatError`) sailed through every one of those assertions undetected while the SAME mutant
// failed 45 tests elsewhere in this suite that already used `expectMessage`.

describe('rejecting malformed template values directly', () => {
  it('a template value that is not an object is rejected', () => {
    // Unlike `objectError`'s strictObject case, a discriminatedUnion DOES have a separate "not an
    // object at all" issue code (`invalid_type`) distinct from "the discriminant didn't match"
    // (`invalid_union`) — see discriminantError's own doc comment. This reports through the SAME
    // discriminantError('from', [...]) path either way, but now names the actual rejected value
    // ('not-an-object') rather than misreporting it as None the way a code-blind version once did.
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
    // Same "two error sources on one z.array().min(1)" gap as flag_if_name_in's 'names' — the empty-
    // array test above only exercises .min(1); this exercises the array's own type check.
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
