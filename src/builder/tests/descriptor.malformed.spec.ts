import { describe, expect, it } from 'vitest';

import { parseDescriptor } from '../descriptor.mjs';
import { expectMessage, minimal, withAgentRole } from '../../commons/support/descriptorFixtures';

// Split out of descriptor.spec.ts (CODE_OF_CONDUCT.md's 500-line test-file cap) — see that file's
// header comment for the full split rationale. This file owns: what a descriptor with MULTIPLE
// simultaneous problems reports, and every shape the closed vocabulary forbids at the top level.
// descriptor.axes.spec.ts owns the sibling "one rejection per closed-vocabulary axis" cases —
// split out of THIS file once commit 5's Zod rewrite pushed it over the same 500-line cap.

describe('a descriptor with MULTIPLE simultaneous problems reports every one, not just the first', () => {
  // Commit 4's hand-written checks failed fast — the first broken section short-circuited the
  // rest, and this describe block used to pin a specific fail-fast ORDER (guard before roles,
  // artifacts before gate, gate before templates). Zod validates the WHOLE shape and collects every
  // issue instead of stopping at the first one, so that specific guarantee no longer holds — what
  // replaces it, and what these three tests now pin, is the NEW guarantee: nothing is hidden behind
  // an earlier problem. Each issue keeps its own path-prefixed message, semicolon-joined.
  it('a broken guard AND a broken role are both named, not just whichever the old code checked first', () => {
    const raw = minimal({ guard: ['bad/path.py'] });
    (raw['roles'] as Record<string, unknown>)['agent'] = { mode: 'improvise' };
    let message = '<did not throw>';
    try {
      parseDescriptor('eco', raw);
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe(
      "ecosystem descriptor 'eco': roles.agent.mode: 'mode' must be one of " +
        "['fields', 'plain', 'preserve', 'toml_command', 'wrap'], got 'improvise'; " +
        "guard[0]: entries are module filenames (no '/'), got 'bad/path.py'",
    );
  });

  it('a broken artifact AND a broken gate are both named', () => {
    const raw = minimal({
      artifacts: ['not-an-object'],
      gate: { protocol: 'magic' },
    });
    let message = '<did not throw>';
    try {
      parseDescriptor('eco', raw);
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe(
      "ecosystem descriptor 'eco': artifacts[0]: an artifact must be an object, got 'not-an-object'; " +
        "gate.protocol: 'protocol' must be one of ['event_guards', 'pre_tool'], got 'magic'",
    );
  });

  it('a broken gate AND a broken template are both named', () => {
    const raw = minimal({
      gate: { protocol: 'magic' },
      templates: [{ src: 'not-a-sibling.js', dest: 'x.js', values: {} }],
    });
    let message = '<did not throw>';
    try {
      parseDescriptor('eco', raw);
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe(
      "ecosystem descriptor 'eco': gate.protocol: 'protocol' must be one of ['event_guards', 'pre_tool'], got 'magic'; " +
        "templates[0].src: 'src' must be a flat '<eco>.template.<dest>' sibling, got 'not-a-sibling.js'",
    );
  });
});

describe('rejecting every shape the closed vocabulary forbids', () => {
  const GATE_OK = {
    protocol: 'pre_tool', tools: { edit: 'Edit' }, path_keys: ['path'],
    deny: { d: 'deny' }, reason_key: 'r',
  };

  it.each([
    ["descriptor is not an object (a list)", () => [], "ecosystem descriptor 'eco': descriptor must be a JSON object, got list"],
    // The four cases below pin the OTHER branches of the same type-name ternary as the list case
    // above — each is its own Stryker mutant (ConditionalExpression/StringLiteral per branch) that
    // was previously NoCoverage: nothing exercised descriptor being null, a string, a boolean, or a
    // number, so a mutated 'NoneType'/'str'/'bool'/'int'/'float' label would have gone unnoticed.
    ["descriptor is not an object (null)", () => null, "ecosystem descriptor 'eco': descriptor must be a JSON object, got NoneType"],
    ["descriptor is not an object (a string)", () => 'nope', "ecosystem descriptor 'eco': descriptor must be a JSON object, got str"],
    ["descriptor is not an object (a boolean)", () => true, "ecosystem descriptor 'eco': descriptor must be a JSON object, got bool"],
    ["descriptor is not an object (an int)", () => 5, "ecosystem descriptor 'eco': descriptor must be a JSON object, got int"],
    ["descriptor is not an object (a float)", () => 5.5, "ecosystem descriptor 'eco': descriptor must be a JSON object, got float"],
    // Pins a documented TS/Python divergence, not parity: JSON.parse('5.0') and JSON.parse('5') both
    // produce the identical JS number 5 — JS has one numeric type, so the literal's float-ness is
    // gone by the time this code sees it. Python's json.loads preserves it (type(json.loads('5.0'))
    // is float), so Python reports 'got float' for this exact input while this port reports 'got
    // int'. A JS *literal* `5.0` can't express this case at all (it's just the number 5 in source
    // code too) — JSON.parse is required to construct an integer-VALUED float the way a real
    // descriptor file's raw bytes would. See the divergence documented at the top of descriptor.mts.
    [
      "descriptor is not an object (an integer-valued float via JSON.parse)",
      () => JSON.parse('5.0') as unknown,
      "ecosystem descriptor 'eco': descriptor must be a JSON object, got int",
    ],
    // `undefined` can never come from JSON.parse, but parseDescriptor's signature accepts `unknown`
    // — and it is the only value that reaches the ternary's FINAL `: typeof raw` fallback, since
    // every JSON-representable non-object shape (null/list/str/bool/number) is handled by an
    // earlier branch. Without this, a mutant that widens the 'number' branch to match anything
    // (Number.isInteger(undefined) is false, so it would misreport 'float') goes unnoticed.
    ["descriptor is not an object (undefined)", () => undefined, "ecosystem descriptor 'eco': descriptor must be a JSON object, got undefined"],
    [
      "vars is not an object at all",
      // `vars`'s own record-type `error` (descriptor.mts's DescriptorSchema, the "not an object at
      // all" branch) is a DIFFERENT Zod check from the ".refine() empty" one "vars is empty" below
      // exercises — both currently produce the same TEXT, but they're two separate schema nodes; a
      // mutant deleting either one independently needs its own input to catch.
      () => minimal({ vars: [] }),
      "ecosystem descriptor 'eco': vars: 'vars' must be a non-empty object",
    ],
    ["vars is empty", () => minimal({ vars: {} }), "ecosystem descriptor 'eco': vars: 'vars' must be a non-empty object"],
    ["models is not an object", () => minimal({ models: [] }), "ecosystem descriptor 'eco': models: 'models' must be a non-empty object"],
    [
      "models is an empty object",
      // Mirrors "vars is empty" above: the invalid_type check and the refine's non-empty check are
      // TWO SEPARATE Zod checks — this exercises the refine independently of the type check, the
      // same way "models is not an object" above only exercises the type check.
      () => minimal({ models: {} }),
      "ecosystem descriptor 'eco': models: 'models' must be a non-empty object",
    ],
    [
      "a model value is not a string or null",
      () => minimal({ models: { high: 5 } }),
      "ecosystem descriptor 'eco': models.high: must be a string or null, got 5",
    ],
    ["smoke is not an object", () => minimal({ smoke: [] }), "ecosystem descriptor 'eco': smoke: 'smoke' must be an object, got []"],
    [
      "smoke expect is not an object",
      () => minimal({ smoke: { cli: 'eco', test: 't', expect: 'not-an-object' } }),
      "ecosystem descriptor 'eco': smoke.expect: smoke 'expect' must be an object, got 'not-an-object'",
    ],
    ["roles is not an object", () => minimal({ roles: [] }), "ecosystem descriptor 'eco': roles: 'roles' must be an object, got []"],
    [
      "roles has exactly four keys but one is wrong (not merely the wrong COUNT)",
      // `roleKeysSorted.every((k, i) => k === roleNamesSorted[i])` vs a `.some(...)` mutant: both
      // agree whenever the key COUNT is wrong (caught by the length check first) or whenever EVERY
      // key is wrong. They can only be told apart with the right COUNT (4) and a MIX of matching and
      // non-matching keys — 'wizard' replacing 'persona' leaves the other three aligned.
      () => {
        const raw = minimal();
        raw['roles'] = {
          agent: { mode: 'preserve' }, command: { mode: 'preserve' },
          default: { mode: 'preserve' }, wizard: { mode: 'preserve' },
        };
        return raw;
      },
      "ecosystem descriptor 'eco': roles.persona: 'mode' must be one of " +
        "['fields', 'plain', 'preserve', 'toml_command', 'wrap'], got None; " +
        "roles: 'roles' has unknown key(s) ['wizard']",
    ],
    ["routes is not a list", () => minimal({ routes: {} }), "ecosystem descriptor 'eco': routes: 'routes' must be a list"],
    ["artifacts is not a list", () => minimal({ artifacts: {} }), "ecosystem descriptor 'eco': artifacts: 'artifacts' must be a list"],
    ["guard is not a list", () => minimal({ guard: {} }), "ecosystem descriptor 'eco': guard: 'guard' must be a list"],
    ["templates is not a list", () => minimal({ templates: {} }), "ecosystem descriptor 'eco': templates: 'templates' must be a list"],
    [
      "a route is not an object",
      () => minimal({ routes: ['x'] }),
      "ecosystem descriptor 'eco': routes[0]: 'kind' must be one of ['exact', 'omit', 'suffix_swap'], got 'x'",
    ],
    ["an artifact is not an object", () => minimal({ artifacts: ['x'] }), "ecosystem descriptor 'eco': artifacts[0]: an artifact must be an object, got 'x'"],
    [
      "artifact versioned is not a boolean",
      () => minimal({
      artifacts: [{ dest: 'p.json', content: {}, versioned: 'yes' }],
    }),
      "ecosystem descriptor 'eco': artifacts[0].versioned: 'versioned' must be a boolean",
    ],
    ["a template is not an object", () => minimal({ templates: ['x'] }), "ecosystem descriptor 'eco': templates[0]: a template must be an object, got 'x'"],
    [
      "template values is not an object",
      () => minimal({
      templates: [{ src: 'eco.template.x', dest: 'x', values: [] }],
    }),
      "ecosystem descriptor 'eco': templates[0].values: 'values' must be an object",
    ],
    [
      "a role is not an object",
      () => withAgentRole('preserve'),
      "ecosystem descriptor 'eco': roles.agent: 'mode' must be one of " +
        "['fields', 'plain', 'preserve', 'toml_command', 'wrap'], got 'preserve'",
    ],
    [
      "role body is unknown",
      () => withAgentRole({
      mode: 'fields', body: 'trim', fields: [{ key: 'k', from: 'stem' }],
    }),
      "ecosystem descriptor 'eco': roles.agent.body: must be one of ['keep', 'lstrip_newlines', 'strip_newlines'], got 'trim'",
    ],
    [
      "role fields is empty",
      () => withAgentRole({ mode: 'fields', fields: [] }),
      "ecosystem descriptor 'eco': roles.agent.fields: requires a non-empty 'fields' list",
    ],
    [
      "role resolve_model_tier is not a boolean",
      () => withAgentRole({
      mode: 'preserve', resolve_model_tier: 'yes',
    }),
      "ecosystem descriptor 'eco': roles.agent.resolve_model_tier: must be a boolean",
    ],
    [
      "role required is not a list",
      () => withAgentRole({ mode: 'preserve', required: 'name' }),
      "ecosystem descriptor 'eco': roles.agent.required: must be a list",
    ],
    [
      "a field is not an object",
      () => withAgentRole({ mode: 'fields', fields: ['k'] }),
      "ecosystem descriptor 'eco': roles.agent.fields[0]: 'from' must be one of " +
        "['flag_if_name_in', 'frontmatter', 'literal', 'primary_mode', 'stem'], got 'k'",
    ],
    [
      "field render is not a boolean",
      () => withAgentRole({
      mode: 'fields', fields: [{ key: 'd', from: 'frontmatter', field: 'd', render: 'yes' }],
    }),
      "ecosystem descriptor 'eco': roles.agent.fields[0].render: must be a boolean",
    ],
    [
      "field names is empty",
      () => withAgentRole({
      mode: 'fields', fields: [{ key: 'r', from: 'flag_if_name_in', names: [], value: 'true' }],
    }),
      "ecosystem descriptor 'eco': roles.agent.fields[0].names: must be a non-empty list",
    ],
    [
      "gate is not an object",
      () => minimal({ gate: 'x' }),
      "ecosystem descriptor 'eco': gate: 'protocol' must be one of ['event_guards', 'pre_tool'], got 'x'",
    ],
    [
      "gate protocol is unknown",
      () => minimal({ gate: { protocol: 'magic' } }),
      "ecosystem descriptor 'eco': gate.protocol: 'protocol' must be one of ['event_guards', 'pre_tool'], got 'magic'",
    ],
    [
      "gate tools is not an object at all",
      // The record-type `error` (not-an-object) and the `.refine()` (empty) below are two SEPARATE
      // Zod checks on gate.tools that currently produce the same text — same reasoning as "vars is
      // not an object at all" in the same table.
      () => minimal({ gate: { ...GATE_OK, tools: 'not-an-object' } }),
      "ecosystem descriptor 'eco': gate.tools: 'tools' must be a non-empty object mapping host tool → canonical tool",
    ],
    [
      "gate tools is empty",
      () => minimal({ gate: { ...GATE_OK, tools: {} } }),
      "ecosystem descriptor 'eco': gate.tools: 'tools' must be a non-empty object mapping host tool → canonical tool",
    ],
    [
      "gate path_keys is empty",
      () => minimal({ gate: { ...GATE_OK, path_keys: [] } }),
      "ecosystem descriptor 'eco': gate.path_keys: 'path_keys' must be a non-empty list",
    ],
    [
      "gate deny is not an object",
      () => minimal({ gate: { ...GATE_OK, deny: 'deny' } }),
      "ecosystem descriptor 'eco': gate.deny: 'deny' must be an object (the host's decision shape)",
    ],
    [
      "gate allow is not an object",
      () => minimal({ gate: { ...GATE_OK, allow: 'allow' } }),
      "ecosystem descriptor 'eco': gate.allow: 'allow' must be an object when present",
    ],
    [
      "gate nested_keys is not a list",
      () => minimal({ gate: { ...GATE_OK, nested_keys: 'edits' } }),
      "ecosystem descriptor 'eco': gate.nested_keys: 'nested_keys' must be a list",
    ],
  ])('rejects: %s', (_label, build, expected) => {
    // Exact message equality, not a substring check: a substring check lets an unrelated
    // literal in the SAME message mutate freely and still pass, which is exactly the class of
    // Stryker survivor a loose assertion leaves behind. Every one of these is independently
    // proven correct against the Python original by the parity fixture of the same name
    // under tests/testdata/parity/descriptor-malformed-*.in.json.
    let message = '<did not throw>';
    try {
      parseDescriptor('eco', build());
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe(expected);
  });
});

