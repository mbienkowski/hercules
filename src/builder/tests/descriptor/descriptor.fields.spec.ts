import { describe, expect, it } from 'vitest';

import { type RoleSpec, parseDescriptor } from '../../descriptor.mjs';
import { expectMessage, minimal, withAgentRole } from '../../../commons/support/descriptorFixtures';

// Split out of descriptor.spec.ts (CODE_OF_CONDUCT.md's 500-line test-file cap) — see that file's
// header comment for the full split rationale. This file owns: every remaining checkStr/
// checkRelPath call site not already covered by descriptor.malformed.spec.ts/descriptor.axes.spec.ts,
// boolean-field defaults, and the two cross-field rules (empty-fields-required, wrap-mode-all-
// literal). The "checkKeys per-shape what label" cases moved to descriptor.axes.spec.ts once this
// file's OWN growth (a 14-variant it.each table) pushed it over the 500-line cap in turn.

describe('every remaining checkStr/checkRelPath call site, one failure each', () => {
  it("checkStr rejects an explicit empty string, not only an absent value", () => {
    // `typeof value !== 'string' || value === ''` — every other checkStr test in this suite passes
    // an ABSENT value (undefined), which the first clause alone already rejects. This is the only
    // test exercising the SECOND clause: an explicit empty string is itself a distinct, real string
    // value that must still be rejected.
    expectMessage(
      () => withAgentRole({ mode: 'fields', fields: [{ key: '', from: 'stem' }] }),
      "ecosystem descriptor \"eco\": roles.agent.fields[0].key: must be a non-empty string, got \"\"",
    );
  });

  it("a guard entry must be a string", () => {
    expectMessage(
      () => minimal({ guard: [5] }),
      "ecosystem descriptor \"eco\": guard[0]: must be a non-empty string, got 5",
    );
  });

  it("a template requires 'dest'", () => {
    // No existing test exercised a TEMPLATE's own 'dest' at all — route 'dest' and artifact 'dest'
    // are covered separately, but templates have their own checkRelPath call site.
    expectMessage(
      () => minimal({ templates: [{ src: 'eco.template.x.js', values: {} }] }),
      "ecosystem descriptor \"eco\": templates[0].dest: must be a non-empty string, got undefined",
    );
  });

  it("field 'field' is required for a frontmatter generator", () => {
    expectMessage(
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'd', from: 'frontmatter' }] }),
      "ecosystem descriptor \"eco\": roles.agent.fields[0].field: must be a non-empty string, got undefined",
    );
  });

  it("field 'value' is required for a literal generator", () => {
    expectMessage(
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'k', from: 'literal' }] }),
      "ecosystem descriptor \"eco\": roles.agent.fields[0].value: must be a non-empty string, got undefined",
    );
  });

  it("field 'primary' is required for a primary_mode generator", () => {
    expectMessage(
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'k', from: 'primary_mode' }] }),
      "ecosystem descriptor \"eco\": roles.agent.fields[0].primary: must be a non-empty string, got undefined",
    );
  });

  it("field 'value' is required for a flag_if_name_in generator", () => {
    expectMessage(() => withAgentRole({
        mode: 'fields', fields: [{ key: 'k', from: 'flag_if_name_in', names: ['x'] }],
      }), "ecosystem descriptor \"eco\": roles.agent.fields[0].value: must be a non-empty string, got undefined");
  });

  it("a flag_if_name_in 'names' entry must be a string", () => {
    expectMessage(() => withAgentRole({
        mode: 'fields',
        fields: [{ key: 'k', from: 'flag_if_name_in', names: [5], value: 'v' }],
      }), "ecosystem descriptor \"eco\": roles.agent.fields[0].names[0]: must be a non-empty string, got 5");
  });

  it("a flag_if_name_in 'names' must be a list, not merely have string entries", () => {
    // `z.array(nonEmptyStr()).min(1)` has TWO error sources: the array's own type check (names
    // isn't an array at all) and .min(1) (names is an empty array). Every existing 'names' test
    // supplies an actual array (with a bad entry, or none), so the array-type check itself was
    // never exercised.
    expectMessage(() => withAgentRole({
        mode: 'fields',
        fields: [{ key: 'k', from: 'flag_if_name_in', names: 'not-an-array', value: 'v' }],
      }), "ecosystem descriptor \"eco\": roles.agent.fields[0].names: must be a non-empty list");
  });

  it("a 'required' entry must be a string", () => {
    expectMessage(
      () => withAgentRole({ mode: 'preserve', required: [5] }),
      "ecosystem descriptor \"eco\": roles.agent.required[0]: must be a non-empty string, got 5",
    );
  });

  it("an exact route requires 'src'", () => {
    expectMessage(
      () => minimal({ routes: [{ kind: 'exact', dest: 'x.md' }] }),
      "ecosystem descriptor \"eco\": routes[0].src: must be a non-empty string, got undefined",
    );
  });

  it("an omit route requires 'src'", () => {
    expectMessage(() => minimal({ routes: [{ kind: 'omit' }] }), "ecosystem descriptor \"eco\": routes[0].src: must be a non-empty string, got undefined");
  });

  it("a suffix_swap route requires 'prefix'", () => {
    expectMessage(() => minimal({
        routes: [{ kind: 'suffix_swap', from_suffix: '.md', to_suffix: '.toml' }],
      }), "ecosystem descriptor \"eco\": routes[0].prefix: must be a non-empty string, got undefined");
  });

  it("a suffix_swap route requires 'from_suffix'", () => {
    expectMessage(() => minimal({
        routes: [{ kind: 'suffix_swap', prefix: 'x/', to_suffix: '.toml' }],
      }), "ecosystem descriptor \"eco\": routes[0].from_suffix: must be a non-empty string, got undefined");
  });

  it("an artifact requires 'dest'", () => {
    expectMessage(() => minimal({ artifacts: [{ content: {} }] }), "ecosystem descriptor \"eco\": artifacts[0].dest: must be a non-empty string, got undefined");
  });

  it("a pre_tool gate tools value must be a string", () => {
    expectMessage(() => minimal({
        gate: { protocol: 'pre_tool', tools: { edit: 5 }, path_keys: ['p'], deny: { d: 1 }, reason_key: 'r' },
      }), "ecosystem descriptor \"eco\": gate.tools.edit: must be a non-empty string, got 5");
  });

  it('pins the CURRENT key-reporting order for gate.tools with multiple bad entries (documented TS/Python divergence)', () => {
    // The same Object.entries() integer-like-key reordering as the 'vars' divergence test in
    // descriptor.malformed.spec.ts, at gate.tools' own separate call site (descriptor.mts's
    // parseGate, not parseDescriptor). Python would report 'zeta' first; this pins the TS-current
    // '42'-first order rather than claiming parity.
    expectMessage(() => minimal({
        gate: {
          protocol: 'pre_tool', tools: { zeta: 1, '42': 2 }, path_keys: ['p'], deny: {}, reason_key: 'r',
        },
      }), "ecosystem descriptor \"eco\": gate.tools.42: must be a non-empty string, got 2; gate.tools.zeta: must be a non-empty string, got 1");
  });

  it("a pre_tool gate requires 'reason_key'", () => {
    expectMessage(() => minimal({
        gate: { protocol: 'pre_tool', tools: { edit: 'Edit' }, path_keys: ['p'], deny: { d: 1 } },
      }), "ecosystem descriptor \"eco\": gate.reason_key: must be a non-empty string, got undefined");
  });

  it("an event_guards gate requires 'user_key'", () => {
    expectMessage(() => minimal({
        gate: { protocol: 'event_guards', allow: { a: 1 }, deny: { d: 1 }, agent_key: 'a' },
      }), "ecosystem descriptor \"eco\": gate.user_key: must be a non-empty string, got undefined");
  });

  it("an event_guards gate requires 'agent_key'", () => {
    expectMessage(() => minimal({
        gate: { protocol: 'event_guards', allow: { a: 1 }, deny: { d: 1 }, user_key: 'u' },
      }), "ecosystem descriptor \"eco\": gate.agent_key: must be a non-empty string, got undefined");
  });

  it("an event_guards gate's 'allow' must be an object", () => {
    // Mirrors the pre_tool 'allow'/'deny' shape checks in descriptor.malformed.spec.ts, but for the
    // OTHER protocol branch (descriptor.mts line ~406-412), which loops ['allow', 'deny']
    // independently of pre_tool's checks. Proven against Python via tests/testdata/parity/
    // descriptor-malformed-gate-eventguards-allow-not-object.in.json.
    expectMessage(() => minimal({
        gate: { protocol: 'event_guards', allow: 'nope', deny: { d: 1 }, user_key: 'u', agent_key: 'a' },
      }), "ecosystem descriptor \"eco\": gate.allow: must be an object (the host's decision shape)");
  });

  it("an event_guards gate's 'deny' must be an object", () => {
    // Proven against Python via tests/testdata/parity/descriptor-malformed-gate-eventguards-
    // deny-not-object.in.json.
    expectMessage(() => minimal({
        gate: { protocol: 'event_guards', allow: { a: 1 }, deny: ['nope'], user_key: 'u', agent_key: 'a' },
      }), "ecosystem descriptor \"eco\": gate.deny: must be an object (the host's decision shape)");
  });

  it("js_string requires 'value'", () => {
    expectMessage(() => minimal({
        templates: [{ src: 'eco.template.x.js', dest: 'x.js', values: { __X__: { from: 'js_string' } } }],
      }), "ecosystem descriptor \"eco\": templates[0].values.__X__.value: must be a non-empty string, got undefined");
  });

  it("a js_string_list entry must be a string", () => {
    expectMessage(() => minimal({
        templates: [{
          src: 'eco.template.x.js', dest: 'x.js',
          values: { __X__: { from: 'js_string_list', values: [5] } },
        }],
      }), "ecosystem descriptor \"eco\": templates[0].values.__X__.values[0]: must be a non-empty string, got 5");
  });

  it("a js_root_joins entry must be a string", () => {
    expectMessage(() => minimal({
        templates: [{
          src: 'eco.template.x.js', dest: 'x.js',
          values: { __X__: { from: 'js_root_joins', paths: [5] } },
        }],
      }), "ecosystem descriptor \"eco\": templates[0].values.__X__.paths[0]: must be a non-empty string, got 5");
  });

  it("a role_entries_js 'drop' entry must be a string", () => {
    expectMessage(() => minimal({
        templates: [{
          src: 'eco.template.x.js', dest: 'x.js',
          values: { __X__: { from: 'role_entries_js', role: 'agent', drop: [5], body_key: 'b' } },
        }],
      }), "ecosystem descriptor \"eco\": templates[0].values.__X__.drop[0]: must be a non-empty string, got 5");
  });

  it("role_entries_js requires 'body_key'", () => {
    expectMessage(() => minimal({
        templates: [{
          src: 'eco.template.x.js', dest: 'x.js',
          values: { __X__: { from: 'role_entries_js', role: 'agent' } },
        }],
      }), "ecosystem descriptor \"eco\": templates[0].values.__X__.body_key: must be a non-empty string, got undefined");
  });

  it("a template 'src' must be a string before it is checked for the sibling shape", () => {
    expectMessage(
      () => minimal({ templates: [{ src: 5, dest: 'x.js', values: {} }] }),
      "ecosystem descriptor \"eco\": templates[0].src: must be a non-empty string, got 5",
    );
  });

  it("a smoke expect version_cmd entry must be a string", () => {
    expectMessage(
      () => minimal({ smoke: { cli: 'eco', test: 't', expect: { version_cmd: [5] } } }),
      "ecosystem descriptor \"eco\": smoke.expect.version_cmd[0]: must be a non-empty string, got 5",
    );
  });

  it('a smoke expect version_cmd must be a list, not merely present', () => {
    // The guard is `!Array.isArray(cmd) || cmd.length === 0` — one condition, two branches. The
    // entry-not-a-string test above only exercises code reached AFTER this guard passes; neither
    // branch of the guard itself had a test. Proven against Python via tests/testdata/parity/
    // descriptor-smoke-expect-versioncmd-not-a-list.in.json.
    expectMessage(
      () => minimal({ smoke: { cli: 'eco', test: 't', expect: { version_cmd: 'not-a-list' } } }),
      "ecosystem descriptor \"eco\": smoke.expect.version_cmd: 'version_cmd' must be a non-empty command list",
    );
  });

  it('a smoke expect version_cmd must not be empty', () => {
    // The other branch of the same guard. Proven against Python via tests/testdata/parity/
    // descriptor-smoke-expect-versioncmd-empty.in.json.
    expectMessage(
      () => minimal({ smoke: { cli: 'eco', test: 't', expect: { version_cmd: [] } } }),
      "ecosystem descriptor \"eco\": smoke.expect.version_cmd: 'version_cmd' must be a non-empty command list",
    );
  });
});

describe('boolean fields fall back to their documented default when absent', () => {
  it('a frontmatter field defaults render to false, not merely "truthy false"', () => {
    const { fields } = parseDescriptor('eco', withAgentRole({
      mode: 'fields', fields: [{ key: 'd', from: 'frontmatter', field: 'd' }],
    })).roles['agent'] as RoleSpec;
    expect(fields[0]?.render).toBe(false);
  });

  it('an artifact defaults versioned to false', () => {
    const { artifacts } = parseDescriptor('eco', minimal({
      artifacts: [{ dest: 'p.json', content: {} }],
    }));
    expect(artifacts[0]?.versioned).toBe(false);
  });

  it('a preserve role defaults resolveModelTier to false and required to [] when both are absent', () => {
    // Every OTHER test using minimal()'s default 'preserve' roles relies on these defaults working
    // without ever asserting the RESULTING values — only the "wrong type is rejected" case was
    // pinned, never the "omitted key produces the documented default" case.
    const { resolveModelTier, required } = parseDescriptor('eco', withAgentRole({ mode: 'preserve' }))
      .roles['agent'] as RoleSpec;
    expect(resolveModelTier).toBe(false);
    expect(required).toEqual([]);
  });

  it("a fields-mode role defaults body to 'keep' when absent", () => {
    const { body } = parseDescriptor('eco', withAgentRole({
      mode: 'fields', fields: [{ key: 'k', from: 'stem' }],
    })).roles['agent'] as RoleSpec;
    expect(body).toBe('keep');
  });

  it("guard defaults to an empty list when the key is entirely absent", () => {
    // `minimal()` never sets 'guard' by default, so every other test in this suite already
    // exercises the omitted-key path — but none of them assert on the RESULTING value, only on
    // other fields. Without this, the `Array.isArray(raw['guard']) ? raw['guard'] : []` fallback's
    // `[]` literal has no test proving it's actually `[]` and not some other placeholder.
    expect(parseDescriptor('eco', minimal()).guard).toEqual([]);
  });
});

describe('the empty-fields-required check applies to wrap and toml_command, not only fields', () => {
  it('rejects an empty fields list on a wrap role', () => {
    const raw = minimal();
    (raw['roles'] as Record<string, unknown>)['persona'] = { mode: 'wrap', fields: [] };
    expectMessage(
      () => raw,
      "ecosystem descriptor \"eco\": roles.persona.fields: requires a non-empty 'fields' list",
    );
  });

  it('rejects an empty fields list on a toml_command role', () => {
    const raw = minimal();
    (raw['roles'] as Record<string, unknown>)['command'] = { mode: 'toml_command', fields: [] };
    expectMessage(
      () => raw,
      "ecosystem descriptor \"eco\": roles.command.fields: requires a non-empty 'fields' list",
    );
  });

  it('does not require fields at all for plain or preserve modes', () => {
    expect(() => parseDescriptor('eco', minimal())).not.toThrow();
  });
});

describe('wrap mode checks that ALL fields are literal, not merely that one is', () => {
  it('rejects when only the second of several fields is non-literal', () => {
    // A `some(f => f.source !== 'literal')` and an `every(...)` mutant agree whenever a single-field
    // role is tested; they can only be told apart with a MIX of literal and non-literal fields.
    const raw = minimal();
    (raw['roles'] as Record<string, unknown>)['persona'] = {
      mode: 'wrap',
      fields: [
        { key: 'a', from: 'literal', value: 'x' },
        { key: 'b', from: 'stem' },
      ],
    };
    expectMessage(
      () => raw,
      "ecosystem descriptor \"eco\": roles.persona: wrap-mode fields must all be literals (generated frontmatter)",
    );
  });

  it('accepts several literal fields together', () => {
    const raw = minimal();
    (raw['roles'] as Record<string, unknown>)['persona'] = {
      mode: 'wrap',
      fields: [
        { key: 'a', from: 'literal', value: 'x' },
        { key: 'b', from: 'literal', value: 'y' },
      ],
    };
    expect(() => parseDescriptor('eco', raw)).not.toThrow();
  });
});
