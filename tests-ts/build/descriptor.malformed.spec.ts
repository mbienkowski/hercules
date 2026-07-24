import { describe, expect, it } from 'vitest';

import { parseDescriptor } from '../../scripts-ts/build/descriptor.mjs';
import { expectMessage, minimal, withAgentRole } from '../support/descriptorFixtures';

// Split out of descriptor.spec.ts (CODE_OF_CONDUCT.md's 500-line test-file cap) — see that file's
// header comment for the full split rationale. This file owns: cross-section validation ORDER, and
// every shape the closed vocabulary forbids at the top level plus each of its enum axes.

describe('rejecting a descriptor with more than one problem, in the documented order', () => {
  it('reports guard before roles, even when both are broken', () => {
    // guard is validated as a local step BEFORE the roles/routes/artifacts section in both the
    // Python original and this port — a real, load-bearing ordering, not an accident of how the
    // code happens to be written.
    const raw = minimal({ guard: ['bad/path.py'] });
    (raw['roles'] as Record<string, unknown>)['agent'] = { mode: 'improvise' };
    let message = '<did not throw>';
    try {
      parseDescriptor('eco', raw);
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe("ecosystem descriptor 'eco': 'guard' entries are module filenames (no '/'), got 'bad/path.py'");
  });

  it('reports artifacts before gate, even when both are broken', () => {
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
    expect(message).toBe("ecosystem descriptor 'eco': an artifact must be an object, got 'not-an-object'");
  });

  it('reports gate before templates, even when both are broken', () => {
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
    expect(message).toBe("ecosystem descriptor 'eco': gate 'protocol' must be one of ['event_guards', 'pre_tool'], got 'magic'");
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
    ["vars is empty", () => minimal({ vars: {} }), "ecosystem descriptor 'eco': 'vars' must be a non-empty object"],
    ["models is not an object", () => minimal({ models: [] }), "ecosystem descriptor 'eco': 'models' must be a non-empty object"],
    [
      "models is an empty object",
      // Mirrors "vars is empty" above: `!isDict(models) || Object.keys(models).length === 0` needs
      // a case where models IS a dict (isDict true) but empty, to exercise the RIGHT side of the
      // `||` independently of the left — "models is not an object" above only exercises the left.
      () => minimal({ models: {} }),
      "ecosystem descriptor 'eco': 'models' must be a non-empty object",
    ],
    [
      "a model value is not a string or null",
      () => minimal({ models: { high: 5 } }),
      "ecosystem descriptor 'eco': models['high'] must be a string or null, got 5",
    ],
    ["smoke is not an object", () => minimal({ smoke: [] }), "ecosystem descriptor 'eco': 'smoke' must be an object"],
    [
      "smoke expect is not an object",
      () => minimal({ smoke: { cli: 'eco', test: 't', expect: 'not-an-object' } }),
      "ecosystem descriptor 'eco': smoke 'expect' must be an object",
    ],
    ["roles is not an object", () => minimal({ roles: [] }), "ecosystem descriptor 'eco': 'roles' must be an object"],
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
      "ecosystem descriptor 'eco': 'roles' must define exactly ['agent', 'command', 'default', 'persona'], got ['agent', 'command', 'default', 'wizard']",
    ],
    ["routes is not a list", () => minimal({ routes: {} }), "ecosystem descriptor 'eco': 'routes' must be a list"],
    ["artifacts is not a list", () => minimal({ artifacts: {} }), "ecosystem descriptor 'eco': 'artifacts' must be a list"],
    ["guard is not a list", () => minimal({ guard: {} }), "ecosystem descriptor 'eco': 'guard' must be a list"],
    ["templates is not a list", () => minimal({ templates: {} }), "ecosystem descriptor 'eco': 'templates' must be a list"],
    ["a route is not an object", () => minimal({ routes: ['x'] }), "ecosystem descriptor 'eco': a route must be an object, got 'x'"],
    ["an artifact is not an object", () => minimal({ artifacts: ['x'] }), "ecosystem descriptor 'eco': an artifact must be an object, got 'x'"],
    [
      "artifact versioned is not a boolean",
      () => minimal({
      artifacts: [{ dest: 'p.json', content: {}, versioned: 'yes' }],
    }),
      "ecosystem descriptor 'eco': artifact 'versioned' must be a boolean",
    ],
    ["a template is not an object", () => minimal({ templates: ['x'] }), "ecosystem descriptor 'eco': a template must be an object, got 'x'"],
    [
      "template values is not an object",
      () => minimal({
      templates: [{ src: 'eco.template.x', dest: 'x', values: [] }],
    }),
      "ecosystem descriptor 'eco': template 'values' must be an object",
    ],
    ["a role is not an object", () => withAgentRole('preserve'), "ecosystem descriptor 'eco': role 'agent' must be an object, got 'preserve'"],
    [
      "role body is unknown",
      () => withAgentRole({
      mode: 'fields', body: 'trim', fields: [{ key: 'k', from: 'stem' }],
    }),
      "ecosystem descriptor 'eco': role 'agent' 'body' must be one of ['keep', 'lstrip_newlines', 'strip_newlines'], got 'trim'",
    ],
    [
      "role fields is empty",
      () => withAgentRole({ mode: 'fields', fields: [] }),
      "ecosystem descriptor 'eco': role 'agent' (mode=fields) requires a non-empty 'fields' list",
    ],
    [
      "role resolve_model_tier is not a boolean",
      () => withAgentRole({
      mode: 'preserve', resolve_model_tier: 'yes',
    }),
      "ecosystem descriptor 'eco': role 'agent' 'resolve_model_tier' must be a boolean",
    ],
    [
      "role required is not a list",
      () => withAgentRole({ mode: 'preserve', required: 'name' }),
      "ecosystem descriptor 'eco': role 'agent' 'required' must be a list",
    ],
    ["a field is not an object", () => withAgentRole({ mode: 'fields', fields: ['k'] }), "ecosystem descriptor 'eco': a field spec must be an object, got 'k'"],
    [
      "field render is not a boolean",
      () => withAgentRole({
      mode: 'fields', fields: [{ key: 'd', from: 'frontmatter', field: 'd', render: 'yes' }],
    }),
      "ecosystem descriptor 'eco': field 'render' must be a boolean",
    ],
    [
      "field names is empty",
      () => withAgentRole({
      mode: 'fields', fields: [{ key: 'r', from: 'flag_if_name_in', names: [], value: 'true' }],
    }),
      "ecosystem descriptor 'eco': field 'names' must be a non-empty list",
    ],
    ["gate is not an object", () => minimal({ gate: 'x' }), "ecosystem descriptor 'eco': 'gate' must be an object, got 'x'"],
    [
      "gate protocol is unknown",
      () => minimal({ gate: { protocol: 'magic' } }),
      "ecosystem descriptor 'eco': gate 'protocol' must be one of ['event_guards', 'pre_tool'], got 'magic'",
    ],
    [
      "gate tools is empty",
      () => minimal({ gate: { ...GATE_OK, tools: {} } }),
      "ecosystem descriptor 'eco': gate 'tools' must be a non-empty object mapping host tool → canonical tool",
    ],
    [
      "gate path_keys is empty",
      () => minimal({ gate: { ...GATE_OK, path_keys: [] } }),
      "ecosystem descriptor 'eco': gate 'path_keys' must be a non-empty list",
    ],
    [
      "gate deny is not an object",
      () => minimal({ gate: { ...GATE_OK, deny: 'deny' } }),
      "ecosystem descriptor 'eco': gate 'deny' must be an object (the host's decision shape)",
    ],
    [
      "gate allow is not an object",
      () => minimal({ gate: { ...GATE_OK, allow: 'allow' } }),
      "ecosystem descriptor 'eco': gate 'allow' must be an object when present",
    ],
    [
      "gate nested_keys is not a list",
      () => minimal({ gate: { ...GATE_OK, nested_keys: 'edits' } }),
      "ecosystem descriptor 'eco': gate 'nested_keys' must be a list",
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

describe('one rejection per closed-vocabulary axis, with a message naming the allowed set', () => {
  it('an unknown top-level key names itself and the allowed set', () => {
    expectMessage(
      () => minimal({ surprises: [] }),
      "ecosystem descriptor 'eco': descriptor has unknown key(s) ['surprises'] — allowed: " +
        "['artifacts', 'dispatch', 'gate', 'guard', 'models', 'name', 'roles', 'routes', 'schema', 'smoke', 'templates', 'vars']",
    );
  });

  it('a missing required key is named', () => {
    const raw = minimal();
    delete raw['roles'];
    expectMessage(() => raw, "ecosystem descriptor 'eco': missing required key 'roles'");
  });

  it('the wrong schema version is rejected', () => {
    expectMessage(() => minimal({ schema: 2 }), "ecosystem descriptor 'eco': 'schema' must be 1, got 2");
  });

  it('name must equal the filename stem', () => {
    let message = '<did not throw>';
    try {
      parseDescriptor('other', minimal());
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe("ecosystem descriptor 'other': 'name' must equal the filename stem, got 'eco'");
  });

  it('a non-string var is rejected, naming the offending key and value', () => {
    expectMessage(
      () => minimal({ vars: { product: 7 } }),
      "ecosystem descriptor 'eco': vars['product'] must be a string, got 7",
    );
  });

  it('pins the CURRENT key-reporting order for vars with multiple bad entries (documented TS/Python divergence)', () => {
    // `Object.entries()` reorders integer-LIKE string keys ('42') ahead of every other key,
    // regardless of source order — a JS object-model behavior Python's dict.items() does not share.
    // Python would report 'zeta' first (source order); this port reports '42' first. See the
    // "Object.entries()/Object.keys() ... reorder integer-like string keys" divergence documented
    // at the top of descriptor.mts. This test exists to PIN the current TS-side behavior, not to
    // claim it matches Python — a regression here is a silent further drift, not a fix.
    expectMessage(
      () => minimal({ vars: { zeta: 1, '42': 2 } }),
      "ecosystem descriptor 'eco': vars['42'] must be a string, got 2",
    );
  });

  it('an unknown model tier is rejected', () => {
    expectMessage(
      () => minimal({ models: { high: null, turbo: 'x' } }),
      "ecosystem descriptor 'eco': 'models' has unknown key(s) ['turbo'] — allowed: ['high', 'low', 'medium']",
    );
  });

  it('an unknown dispatch value is rejected', () => {
    expectMessage(
      () => minimal({ dispatch: 'magic' }),
      "ecosystem descriptor 'eco': 'dispatch' must be one of ['frontmatter', 'path'], got 'magic'",
    );
  });

  it('roles must define exactly the four role names', () => {
    const raw = minimal();
    raw['roles'] = { agent: { mode: 'preserve' } };
    expectMessage(
      () => raw,
      "ecosystem descriptor 'eco': 'roles' must define exactly ['agent', 'command', 'default', 'persona'], got ['agent']",
    );
  });

  it('an unknown role mode names itself and a known mode', () => {
    expectMessage(
      () => withAgentRole({ mode: 'improvise' }),
      "ecosystem descriptor 'eco': role 'agent' 'mode' must be one of " +
        "['fields', 'plain', 'preserve', 'toml_command', 'wrap'], got 'improvise'",
    );
  });

  it('a key outside the current mode’s vocabulary is rejected', () => {
    // `fields` is meaningless on a preserve role — the per-mode key set is closed.
    expectMessage(
      () => withAgentRole({ mode: 'preserve', fields: [] }),
      "ecosystem descriptor 'eco': role 'agent' (mode=preserve) has unknown key(s) ['fields'] — " +
        "allowed: ['mode', 'required', 'resolve_model_tier']",
    );
  });

  it('an unknown field generator names itself and a known one', () => {
    expectMessage(
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'x', from: 'conditional' }] }),
      "ecosystem descriptor 'eco': field 'from' must be one of " +
        "['flag_if_name_in', 'frontmatter', 'literal', 'primary_mode', 'stem'], got 'conditional'",
    );
  });

  it('wrap mode rejects a non-literal field', () => {
    // wrap frontmatter is generated statics only — no source-dependent generators sneak in.
    const raw = minimal();
    (raw['roles'] as Record<string, unknown>)['persona'] = {
      mode: 'wrap', fields: [{ key: 'name', from: 'frontmatter', field: 'name' }],
    };
    expectMessage(
      () => raw,
      "ecosystem descriptor 'eco': role 'persona': wrap-mode fields must all be literals (generated frontmatter)",
    );
  });

  it('toml_command requires exactly the description field', () => {
    const raw = minimal();
    (raw['roles'] as Record<string, unknown>)['command'] = {
      mode: 'toml_command', fields: [{ key: 'name', from: 'stem' }],
    };
    expectMessage(
      () => raw,
      "ecosystem descriptor 'eco': role 'command': toml_command emits exactly one field, 'description'",
    );
  });

  it('toml_command rejects a SECOND field even when the first is description', () => {
    // `keys.length !== 1 || keys[0] !== 'description'` — the test above only exercises the RIGHT
    // clause (wrong single field). This exercises the LEFT clause independently: the right field
    // name, but a wrong COUNT.
    const raw = minimal();
    (raw['roles'] as Record<string, unknown>)['command'] = {
      mode: 'toml_command',
      fields: [{ key: 'description', from: 'stem' }, { key: 'extra', from: 'stem' }],
    };
    expectMessage(
      () => raw,
      "ecosystem descriptor 'eco': role 'command': toml_command emits exactly one field, 'description'",
    );
  });

  it('an unknown route kind names itself and a known one', () => {
    expectMessage(
      () => minimal({ routes: [{ kind: 'regex', pattern: '.*' }] }),
      "ecosystem descriptor 'eco': route 'kind' must be one of ['exact', 'omit', 'suffix_swap'], got 'regex'",
    );
  });

  it('a route dest may not escape the tree', () => {
    const routes = [{ kind: 'exact', src: 'persona.md', dest: '../evil.md' }];
    expectMessage(
      () => minimal({ routes }),
      "ecosystem descriptor 'eco': route 'dest' must be a relative path without '..', got '../evil.md'",
    );
  });

  it('a suffix_swap to_suffix may not escape the tree either', () => {
    // The same tree-escape guard as an exact route's dest — a '..' here must not silently write
    // outside the plugin tree.
    const routes = [{
      kind: 'suffix_swap', prefix: 'commands/', from_suffix: '.md', to_suffix: '../../../etc/x',
    }];
    expectMessage(
      () => minimal({ routes }),
      "ecosystem descriptor 'eco': route 'to_suffix' must be a relative path without '..', got '../../../etc/x'",
    );
  });

  it('artifact content must be a JSON object', () => {
    const artifacts = [{ dest: 'plugin.json', content: 'raw text' }];
    expectMessage(
      () => minimal({ artifacts }),
      "ecosystem descriptor 'eco': artifact 'content' must be a JSON object",
    );
  });

  it('an unknown template value kind names itself and a known one', () => {
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { __X__: { from: 'run_code' } } }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor 'eco': template value '__X__' 'from' must be one of " +
        "['js_root_joins', 'js_string', 'js_string_list', 'role_entries_js'], got 'run_code'",
    );
  });

  it('a template placeholder must be upper-snake dunder', () => {
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { '{{x}}': { from: 'js_string', value: 'v' } } }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor 'eco': template placeholder '{{x}}' must match __UPPER_SNAKE__",
    );
  });

  it('a template placeholder must match the WHOLE string, not just contain a valid dunder', () => {
    // PLACEHOLDER is /^__[A-Z_]+__$/ — anchored at both ends. '{{x}}' above proves the pattern
    // rejects something with no dunder shape at all; this proves the anchors themselves matter: a
    // dunder-shaped substring with extra characters BEFORE it must still be rejected, not accepted
    // because the tail happens to match `__[A-Z_]+__$`.
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { 'X__FOO__': { from: 'js_string', value: 'v' } } }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor 'eco': template placeholder 'X__FOO__' must match __UPPER_SNAKE__",
    );
  });

  it('a template placeholder with extra characters AFTER a valid dunder is also rejected', () => {
    // The other anchor: a dunder-shaped substring with extra characters trailing it must not be
    // accepted because the head happens to match `^__[A-Z_]+__`.
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { '__FOO__X': { from: 'js_string', value: 'v' } } }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor 'eco': template placeholder '__FOO__X' must match __UPPER_SNAKE__",
    );
  });

  it('a template src must be a template sibling', () => {
    const tpl = [{ src: 'plugin.js', dest: 'plugin.js', values: {} }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor 'eco': template 'src' must be a flat '<eco>.template.<dest>' sibling, got 'plugin.js'",
    );
  });

  it('role_entries_js requires a known role', () => {
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __E__: { from: 'role_entries_js', role: 'wizard', body_key: 'prompt' } },
    }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor 'eco': template value '__E__' 'role' must be one of " +
        "['agent', 'command', 'default', 'persona'], got 'wizard'",
    );
  });

  it('guard entries must be bare module filenames', () => {
    expectMessage(
      () => minimal({ guard: ['hooks/frozen_tests.py'] }),
      "ecosystem descriptor 'eco': 'guard' entries are module filenames (no '/'), got 'hooks/frozen_tests.py'",
    );
  });

  it('smoke requires both cli and test', () => {
    expectMessage(
      () => minimal({ smoke: { cli: 'eco' } }),
      "ecosystem descriptor 'eco': smoke['test'] must be a non-empty string, got None",
    );
  });
});
