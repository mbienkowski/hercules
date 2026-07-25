import { describe, expect, it } from 'vitest';

import { parseDescriptor } from '../descriptor.mjs';
import { expectMessage, minimal, withAgentRole } from '../../tests/support/descriptorFixtures';

// Split out of descriptor.malformed.spec.ts (CODE_OF_CONDUCT.md's 500-line test-file cap) once
// commit 5's Zod rewrite pushed that file over the cap — see descriptor.spec.ts's header comment
// for the full split rationale. This file owns: one rejection per closed-vocabulary enum/shape
// axis, each asserting the exact message naming the offending value and (where the schema still
// enumerates it) the allowed set.

describe('one rejection per closed-vocabulary axis, with a message naming the allowed set', () => {
  it('an unknown top-level key names itself and the allowed set', () => {
    expectMessage(
      () => minimal({ surprises: [] }),
      "ecosystem descriptor 'eco': descriptor has unknown key(s) ['surprises']",
    );
  });

  it('a missing required key is named', () => {
    const raw = minimal();
    delete raw['roles'];
    expectMessage(() => raw, "ecosystem descriptor 'eco': roles: 'roles' must be an object, got None");
  });

  it("'routes' is required, not merely defaulted to [] like artifacts/guard/templates", () => {
    // Caught by review: an earlier draft of DescriptorSchema gave 'routes' the SAME `.default([])`
    // treatment as artifacts/guard/templates below, but the Python original's own required-key list
    // is schema/name/vars/models/smoke/dispatch/roles/ROUTES — omitting it entirely must fail the
    // same way omitting 'vars' or 'roles' does, not silently default to an empty list. minimal()
    // always sets routes:[] explicitly, so no OTHER test exercises the fully-omitted case.
    const raw = minimal();
    delete raw['routes'];
    expectMessage(() => raw, "ecosystem descriptor 'eco': routes: 'routes' must be a list");
  });

  it('the wrong schema version is rejected', () => {
    expectMessage(() => minimal({ schema: 2 }), "ecosystem descriptor 'eco': schema: must be 1, got 2");
  });

  it('a non-string name is rejected with the same pyRepr-formatted convention every sibling field uses', () => {
    expectMessage(() => minimal({ name: 123 }), "ecosystem descriptor 'eco': name: must be a string, got 123");
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
      "ecosystem descriptor 'eco': vars.product: must be a string, got 7",
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
      "ecosystem descriptor 'eco': vars.42: must be a string, got 2; vars.zeta: must be a string, got 1",
    );
  });

  it('an unknown model tier is rejected', () => {
    // This test caught a real schema bug during review: ModelsSchema's object-level `error`
    // callback was NOT checking `issue.code`, so it swallowed the 'invalid_key' (wrong tier name)
    // case under the SAME text as 'invalid_type' (not an object at all) — this exact scenario was
    // reporting "models.turbo: 'models' must be a non-empty object" instead of naming the allowed
    // tiers, before the fix.
    expectMessage(
      () => minimal({ models: { high: null, turbo: 'x' } }),
      "ecosystem descriptor 'eco': models.turbo: must be one of ['high', 'low', 'medium'], got 'turbo'",
    );
  });

  it('an unknown dispatch value is rejected', () => {
    expectMessage(
      () => minimal({ dispatch: 'magic' }),
      "ecosystem descriptor 'eco': dispatch: must be one of ['frontmatter', 'path'], got 'magic'",
    );
  });

  it('roles must define exactly the four role names', () => {
    const raw = minimal();
    raw['roles'] = { agent: { mode: 'preserve' } };
    // The three MISSING roles (command/persona/default) each independently fail the SAME way a
    // present-but-empty role would — Zod reports one 'mode' issue per absent key, not a single
    // summary naming the whole missing set the way commit 4's hand-written check did.
    const missingMode = (role: string) =>
      `${role}: 'mode' must be one of ['fields', 'plain', 'preserve', 'toml_command', 'wrap'], got None`;
    expectMessage(
      () => raw,
      `ecosystem descriptor 'eco': ${missingMode('roles.command')}; ` +
        `${missingMode('roles.persona')}; ${missingMode('roles.default')}`,
    );
  });

  it('an unknown role mode names itself and a known mode', () => {
    expectMessage(
      () => withAgentRole({ mode: 'improvise' }),
      "ecosystem descriptor 'eco': roles.agent.mode: 'mode' must be one of " +
        "['fields', 'plain', 'preserve', 'toml_command', 'wrap'], got 'improvise'",
    );
  });

  it('a key outside the current mode’s vocabulary is rejected', () => {
    // `fields` is meaningless on a preserve role — the per-mode key set is closed.
    expectMessage(
      () => withAgentRole({ mode: 'preserve', fields: [] }),
      "ecosystem descriptor 'eco': roles.agent: role (mode=preserve) has unknown key(s) ['fields']",
    );
  });

  it('an unknown field generator names itself and a known one', () => {
    expectMessage(
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'x', from: 'conditional' }] }),
      "ecosystem descriptor 'eco': roles.agent.fields[0].from: 'from' must be one of " +
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
      "ecosystem descriptor 'eco': roles.persona: wrap-mode fields must all be literals (generated frontmatter)",
    );
  });

  it('toml_command requires exactly the description field', () => {
    const raw = minimal();
    (raw['roles'] as Record<string, unknown>)['command'] = {
      mode: 'toml_command', fields: [{ key: 'name', from: 'stem' }],
    };
    expectMessage(
      () => raw,
      "ecosystem descriptor 'eco': roles.command: toml_command emits exactly one field, 'description'",
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
      "ecosystem descriptor 'eco': roles.command: toml_command emits exactly one field, 'description'",
    );
  });

  it('an unknown route kind names itself and a known one', () => {
    expectMessage(
      () => minimal({ routes: [{ kind: 'regex', pattern: '.*' }] }),
      "ecosystem descriptor 'eco': routes[0].kind: 'kind' must be one of ['exact', 'omit', 'suffix_swap'], got 'regex'",
    );
  });

  it('a route dest may not escape the tree', () => {
    const routes = [{ kind: 'exact', src: 'persona.md', dest: '../evil.md' }];
    expectMessage(
      () => minimal({ routes }),
      "ecosystem descriptor 'eco': routes[0].dest: must be a relative path without '..', got '../evil.md'",
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
      "ecosystem descriptor 'eco': routes[0].to_suffix: must be a relative path without '..', got '../../../etc/x'",
    );
  });

  it('artifact content must be a JSON object', () => {
    const artifacts = [{ dest: 'plugin.json', content: 'raw text' }];
    expectMessage(
      () => minimal({ artifacts }),
      "ecosystem descriptor 'eco': artifacts[0].content: 'content' must be a JSON object",
    );
  });

  it('an unknown template value kind names itself and a known one', () => {
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { __X__: { from: 'run_code' } } }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor 'eco': templates[0].values.__X__.from: 'from' must be one of " +
        "['js_root_joins', 'js_string', 'js_string_list', 'role_entries_js'], got 'run_code'",
    );
  });

  it('a template placeholder must be upper-snake dunder', () => {
    // This test (and its two siblings below) caught a real schema bug during review: the `values`
    // record's object-level `error` callback was code-blind, so it swallowed the KEY schema's own
    // "must match __UPPER_SNAKE__" message (Zod's `invalid_key` code, for a malformed placeholder)
    // under the generic "'values' must be an object" text (meant only for `invalid_type`, values not
    // being an object at all) — the exact same bug class ModelsSchema had for an unknown model tier.
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { '{{x}}': { from: 'js_string', value: 'v' } } }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor 'eco': templates[0].values.{{x}}: placeholder '{{x}}' must match __UPPER_SNAKE__",
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
      "ecosystem descriptor 'eco': templates[0].values.X__FOO__: placeholder 'X__FOO__' must match __UPPER_SNAKE__",
    );
  });

  it('a template placeholder with extra characters AFTER a valid dunder is also rejected', () => {
    // The other anchor: a dunder-shaped substring with extra characters trailing it must not be
    // accepted because the head happens to match `^__[A-Z_]+__`.
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { '__FOO__X': { from: 'js_string', value: 'v' } } }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor 'eco': templates[0].values.__FOO__X: placeholder '__FOO__X' must match __UPPER_SNAKE__",
    );
  });

  it('a template src must be a template sibling', () => {
    const tpl = [{ src: 'plugin.js', dest: 'plugin.js', values: {} }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor 'eco': templates[0].src: 'src' must be a flat '<eco>.template.<dest>' sibling, got 'plugin.js'",
    );
  });

  it('role_entries_js requires a known role', () => {
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __E__: { from: 'role_entries_js', role: 'wizard', body_key: 'prompt' } },
    }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor 'eco': templates[0].values.__E__.role: must be one of " +
        "['agent', 'command', 'default', 'persona'], got 'wizard'",
    );
  });

  it('guard entries must be bare module filenames', () => {
    expectMessage(
      () => minimal({ guard: ['hooks/frozen_tests.py'] }),
      "ecosystem descriptor 'eco': guard[0]: entries are module filenames (no '/'), got 'hooks/frozen_tests.py'",
    );
  });

  it('smoke requires test, when cli is present', () => {
    expectMessage(
      () => minimal({ smoke: { cli: 'eco' } }),
      "ecosystem descriptor 'eco': smoke.test: must be a non-empty string, got None",
    );
  });

  it('smoke requires cli, when test is present', () => {
    // The sibling test above only ever supplies `cli` and omits `test` — caught by review: every
    // other smoke-touching test in this suite also always supplies `cli`, so nothing proved `cli`
    // itself is required rather than merely present-by-convention. Verified by live regression
    // injection (making `cli` optional in SmokeSchema) before this test existed: the full suite
    // passed undetected.
    expectMessage(
      () => minimal({ smoke: { test: 'tests/build/test_eco_smoke.py' } }),
      "ecosystem descriptor 'eco': smoke.cli: must be a non-empty string, got None",
    );
  });
});

// Moved here from descriptor.fields.spec.ts once its own growth (the it.each table below) pushed
// THAT file over the 500-line cap in turn.
describe('checkKeys is exercised with an unknown key for every distinct "what" label', () => {
  it('names the mode in a field-shape error: field (from=X)', () => {
    expectMessage(
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'k', from: 'stem', extra: 1 }] }),
      "ecosystem descriptor 'eco': roles.agent.fields[0]: field (from=stem) has unknown key(s) ['extra']",
    );
  });

  it('names the kind in a route-shape error: route (kind=X)', () => {
    expectMessage(
      () => minimal({ routes: [{ kind: 'omit', src: 'a.md', extra: 1 }] }),
      "ecosystem descriptor 'eco': routes[0]: route (kind=omit) has unknown key(s) ['extra']",
    );
  });

  it('names the protocol in a gate-shape error: gate (protocol=X)', () => {
    expectMessage(
      () => minimal({
        gate: {
          protocol: 'event_guards', allow: {}, deny: {}, user_key: 'u', agent_key: 'a', extra: 1,
        },
      }),
      "ecosystem descriptor 'eco': gate: gate (protocol=event_guards) has unknown key(s) ['extra']",
    );
  });

  it('names the placeholder and kind in a template-value-shape error', () => {
    expectMessage(
      () => minimal({
        templates: [{
          src: 'eco.template.x.js', dest: 'x.js',
          values: { __X__: { from: 'js_string', value: 'v', extra: 1 } },
        }],
      }),
      "ecosystem descriptor 'eco': templates[0].values.__X__: template value (from=js_string) has unknown key(s) ['extra']",
    );
  });

  it('names an unknown key on the artifact shape itself', () => {
    expectMessage(
      () => minimal({ artifacts: [{ dest: 'p.json', content: {}, extra: 1 }] }),
      "ecosystem descriptor 'eco': artifacts[0]: an artifact has unknown key(s) ['extra']",
    );
  });

  it('names an unknown key on the template shape itself', () => {
    expectMessage(
      () => minimal({ templates: [{ src: 'eco.template.x', dest: 'x', values: {}, extra: 1 }] }),
      "ecosystem descriptor 'eco': templates[0]: a template has unknown key(s) ['extra']",
    );
  });

  it('names an unknown key on the smoke shape itself', () => {
    expectMessage(
      () => minimal({ smoke: { cli: 'eco', test: 't', extra: 1 } }),
      "ecosystem descriptor 'eco': smoke: 'smoke' has unknown key(s) ['extra']",
    );
  });

  it('names an unknown key on the smoke.expect shape', () => {
    expectMessage(
      () => minimal({ smoke: { cli: 'eco', test: 't', expect: { version_cmd: ['x'], extra: 1 } } }),
      "ecosystem descriptor 'eco': smoke.expect: smoke 'expect' has unknown key(s) ['extra']",
    );
  });

  it('sorts multiple unknown keys alphabetically rather than by input order', () => {
    // A filter().sort() chain: dropping the sort would report ['zzz', 'another', 'surprises'] in
    // whatever order Object.keys happened to iterate, not the documented sorted allowed-set style.
    expectMessage(
      () => minimal({ zzz: 1, another: 2, surprises: 3 }),
      "ecosystem descriptor 'eco': descriptor has unknown key(s) ['another', 'surprises', 'zzz']",
    );
  });

  // Every discriminated union in descriptor.mts (field/role/route/template-value/gate) gets its OWN
  // objectError(...) call per VARIANT, so each one is a SEPARATE Stryker mutant — the tests above
  // only exercised a representative sample per union (field's 'stem', route's 'omit', one template
  // value kind, one gate protocol), leaving every OTHER variant's unknown-key wiring unproven. This
  // table covers the rest without repeating the same test body fourteen times.
  it.each([
    [
      "field (from=frontmatter)",
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'k', from: 'frontmatter', field: 'f', extra: 1 }] }),
      "roles.agent.fields[0]: field (from=frontmatter) has unknown key(s) ['extra']",
    ],
    [
      "field (from=literal)",
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'k', from: 'literal', value: 'v', extra: 1 }] }),
      "roles.agent.fields[0]: field (from=literal) has unknown key(s) ['extra']",
    ],
    [
      "field (from=primary_mode)",
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'k', from: 'primary_mode', primary: 'p', extra: 1 }] }),
      "roles.agent.fields[0]: field (from=primary_mode) has unknown key(s) ['extra']",
    ],
    [
      "field (from=flag_if_name_in)",
      () => withAgentRole({
        mode: 'fields', fields: [{ key: 'k', from: 'flag_if_name_in', names: ['n'], value: 'v', extra: 1 }],
      }),
      "roles.agent.fields[0]: field (from=flag_if_name_in) has unknown key(s) ['extra']",
    ],
    [
      "role (mode=fields)",
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'k', from: 'stem' }], extra: 1 }),
      "roles.agent: role (mode=fields) has unknown key(s) ['extra']",
    ],
    [
      "role (mode=wrap)",
      () => withAgentRole({ mode: 'wrap', fields: [{ key: 'k', from: 'literal', value: 'v' }], extra: 1 }),
      "roles.agent: role (mode=wrap) has unknown key(s) ['extra']",
    ],
    [
      "role (mode=plain)",
      () => withAgentRole({ mode: 'plain', extra: 1 }),
      "roles.agent: role (mode=plain) has unknown key(s) ['extra']",
    ],
    [
      "role (mode=toml_command)",
      () => withAgentRole({ mode: 'toml_command', fields: [{ key: 'description', from: 'stem' }], extra: 1 }),
      "roles.agent: role (mode=toml_command) has unknown key(s) ['extra']",
    ],
    [
      "route (kind=exact)",
      () => minimal({ routes: [{ kind: 'exact', src: 'a.md', dest: 'b.md', extra: 1 }] }),
      "routes[0]: route (kind=exact) has unknown key(s) ['extra']",
    ],
    [
      "route (kind=suffix_swap)",
      () => minimal({
        routes: [{ kind: 'suffix_swap', prefix: 'x/', from_suffix: '.md', to_suffix: '.toml', extra: 1 }],
      }),
      "routes[0]: route (kind=suffix_swap) has unknown key(s) ['extra']",
    ],
    [
      "template value (from=js_string_list)",
      () => minimal({
        templates: [{
          src: 'eco.template.x.js', dest: 'x.js',
          values: { __X__: { from: 'js_string_list', values: ['a'], extra: 1 } },
        }],
      }),
      "templates[0].values.__X__: template value (from=js_string_list) has unknown key(s) ['extra']",
    ],
    [
      "template value (from=js_root_joins)",
      () => minimal({
        templates: [{
          src: 'eco.template.x.js', dest: 'x.js',
          values: { __X__: { from: 'js_root_joins', paths: ['a'], extra: 1 } },
        }],
      }),
      "templates[0].values.__X__: template value (from=js_root_joins) has unknown key(s) ['extra']",
    ],
    [
      "template value (from=role_entries_js)",
      () => minimal({
        templates: [{
          src: 'eco.template.x.js', dest: 'x.js',
          values: { __X__: { from: 'role_entries_js', role: 'agent', body_key: 'b', extra: 1 } },
        }],
      }),
      "templates[0].values.__X__: template value (from=role_entries_js) has unknown key(s) ['extra']",
    ],
    [
      "gate (protocol=pre_tool)",
      () => minimal({
        gate: { protocol: 'pre_tool', tools: { edit: 'Edit' }, path_keys: ['p'], deny: {}, reason_key: 'r', extra: 1 },
      }),
      "gate: gate (protocol=pre_tool) has unknown key(s) ['extra']",
    ],
  ])('names the variant in an unknown-key error: %s', (_label, build, expected) => {
    expectMessage(build, `ecosystem descriptor 'eco': ${expected}`);
  });
});
