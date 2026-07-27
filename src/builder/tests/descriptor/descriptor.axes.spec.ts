import { describe, expect, it } from 'vitest';

import { parseDescriptor } from '../../descriptor.mjs';
import { expectMessage, minimal, withAgentRole } from '../../../commons/support/descriptorFixtures';

// One rejection per closed-vocabulary enum/shape axis, each asserting the exact message naming the
// offending value and, where the schema enumerates it, the allowed set.

describe('one rejection per closed-vocabulary axis, with a message naming the allowed set', () => {
  it('an unknown top-level key names itself and the allowed set', () => {
    expectMessage(
      () => minimal({ surprises: [] }),
      "ecosystem descriptor \"eco\": descriptor has unknown key(s) [\"surprises\"]",
    );
  });

  it('a missing required key is named', () => {
    const raw = minimal();
    delete raw['roles'];
    expectMessage(() => raw, "ecosystem descriptor \"eco\": roles: 'roles' must be an object, got undefined");
  });

  it("'routes' is required, not merely defaulted to [] like artifacts/guard/templates", () => {
    // 'routes' is required, unlike artifacts/guard/templates which default to []. minimal() always
    // sets routes:[] explicitly, so no OTHER test exercises the fully-omitted case.
    const raw = minimal();
    delete raw['routes'];
    expectMessage(() => raw, "ecosystem descriptor \"eco\": routes: 'routes' must be a list");
  });

  it('the wrong schema version is rejected', () => {
    expectMessage(() => minimal({ schema: 2 }), "ecosystem descriptor \"eco\": schema: must be 1, got 2");
  });

  it('a non-string name is rejected with the same show()/JSON-formatted convention every sibling field uses', () => {
    expectMessage(() => minimal({ name: 123 }), "ecosystem descriptor \"eco\": name: must be a string, got 123");
  });

  it('name must equal the filename stem', () => {
    let message = '<did not throw>';
    try {
      parseDescriptor('other', minimal());
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe("ecosystem descriptor \"other\": 'name' must equal the filename stem, got \"eco\"");
  });

  it('a non-string var is rejected, naming the offending key and value', () => {
    expectMessage(
      () => minimal({ vars: { product: 7 } }),
      "ecosystem descriptor \"eco\": vars.product: must be a string, got 7",
    );
  });

  it('pins the CURRENT key-reporting order for vars with multiple bad entries', () => {
    // `Object.entries()` reorders integer-LIKE string keys ('42') ahead of the rest regardless of
    // source order, so '42' is reported first — a divergence noted at the top of descriptor.mts.
    expectMessage(
      () => minimal({ vars: { zeta: 1, '42': 2 } }),
      "ecosystem descriptor \"eco\": vars.42: must be a string, got 2; vars.zeta: must be a string, got 1",
    );
  });

  it('an unknown model tier is rejected', () => {
    // ModelsSchema's object-level `error` callback must branch on `issue.code`, or an unknown tier
    // ('invalid_key') collapses into the not-an-object text meant for 'invalid_type'.
    expectMessage(
      () => minimal({ models: { high: null, turbo: 'x' } }),
      "ecosystem descriptor \"eco\": models.turbo: must be one of [\"high\",\"low\",\"medium\"], got \"turbo\"",
    );
  });

  it('an unknown dispatch value is rejected', () => {
    expectMessage(
      () => minimal({ dispatch: 'magic' }),
      "ecosystem descriptor \"eco\": dispatch: must be one of [\"frontmatter\",\"path\"], got \"magic\"",
    );
  });

  it('roles must define exactly the four role names', () => {
    const raw = minimal();
    raw['roles'] = { agent: { mode: 'preserve' } };
    // The three MISSING roles (command/persona/default) each fail the SAME way a present-but-empty
    // role would: Zod reports one 'mode' issue per absent key, not one summary naming the whole set.
    const missingMode = (role: string) =>
      `${role}: 'mode' must be one of ["fields","plain","preserve","toml_command","wrap"], got undefined`;
    expectMessage(
      () => raw,
      `ecosystem descriptor "eco": ${missingMode('roles.command')}; ` +
        `${missingMode('roles.persona')}; ${missingMode('roles.default')}`,
    );
  });

  it('an unknown role mode names itself and a known mode', () => {
    expectMessage(
      () => withAgentRole({ mode: 'improvise' }),
      "ecosystem descriptor \"eco\": roles.agent.mode: 'mode' must be one of " +
        "[\"fields\",\"plain\",\"preserve\",\"toml_command\",\"wrap\"], got \"improvise\"",
    );
  });

  it('a key outside the current mode’s vocabulary is rejected', () => {
    // `fields` is meaningless on a preserve role — the per-mode key set is closed.
    expectMessage(
      () => withAgentRole({ mode: 'preserve', fields: [] }),
      "ecosystem descriptor \"eco\": roles.agent: role (mode=preserve) has unknown key(s) [\"fields\"]",
    );
  });

  it('an unknown field generator names itself and a known one', () => {
    expectMessage(
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'x', from: 'conditional' }] }),
      "ecosystem descriptor \"eco\": roles.agent.fields[0].from: 'from' must be one of " +
        "[\"flag_if_name_in\",\"frontmatter\",\"literal\",\"primary_mode\",\"stem\"], got \"conditional\"",
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
      "ecosystem descriptor \"eco\": roles.persona: wrap-mode fields must all be literals (generated frontmatter)",
    );
  });

  it('toml_command requires exactly the description field', () => {
    const raw = minimal();
    (raw['roles'] as Record<string, unknown>)['command'] = {
      mode: 'toml_command', fields: [{ key: 'name', from: 'stem' }],
    };
    expectMessage(
      () => raw,
      "ecosystem descriptor \"eco\": roles.command: toml_command emits exactly one field, 'description'",
    );
  });

  it('toml_command rejects a SECOND field even when the first is description', () => {
    // `keys.length !== 1 || keys[0] !== 'description'` — the test above exercises the RIGHT clause
    // (wrong single field); this exercises the LEFT one: the right field name, but a wrong COUNT.
    const raw = minimal();
    (raw['roles'] as Record<string, unknown>)['command'] = {
      mode: 'toml_command',
      fields: [{ key: 'description', from: 'stem' }, { key: 'extra', from: 'stem' }],
    };
    expectMessage(
      () => raw,
      "ecosystem descriptor \"eco\": roles.command: toml_command emits exactly one field, 'description'",
    );
  });

  it("toml_command rejects a 'description' sourced from flag_if_name_in (it may omit its key)", () => {
    // A conditional generator leaves the mandatory single `description` unset when the name
    // doesn't match, which renders as `description = "undefined"`. The check forbids it up front.
    const raw = minimal();
    (raw['roles'] as Record<string, unknown>)['command'] = {
      mode: 'toml_command',
      fields: [{ key: 'description', from: 'flag_if_name_in', value: 'x', names: ['a'] }],
    };
    expectMessage(
      () => raw,
      "ecosystem descriptor \"eco\": roles.command: toml_command's 'description' must use a generator that always emits (not flag_if_name_in)",
    );
  });

  it('an unknown route kind names itself and a known one', () => {
    expectMessage(
      () => minimal({ routes: [{ kind: 'regex', pattern: '.*' }] }),
      "ecosystem descriptor \"eco\": routes[0].kind: 'kind' must be one of [\"exact\",\"omit\",\"suffix_swap\"], got \"regex\"",
    );
  });

  it('a route dest may not escape the tree', () => {
    const routes = [{ kind: 'exact', src: 'persona.md', dest: '../evil.md' }];
    expectMessage(
      () => minimal({ routes }),
      "ecosystem descriptor \"eco\": routes[0].dest: must be a relative path without '..', got \"../evil.md\"",
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
      "ecosystem descriptor \"eco\": routes[0].to_suffix: must be a relative path without '..', got \"../../../etc/x\"",
    );
  });

  it('artifact content must be a JSON object', () => {
    const artifacts = [{ dest: 'plugin.json', content: 'raw text' }];
    expectMessage(
      () => minimal({ artifacts }),
      "ecosystem descriptor \"eco\": artifacts[0].content: 'content' must be a JSON object",
    );
  });

  it('an unknown template value kind names itself and a known one', () => {
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { __X__: { from: 'run_code' } } }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor \"eco\": templates[0].values.__X__.from: 'from' must be one of " +
        "[\"js_root_joins\",\"js_string\",\"js_string_list\",\"role_entries_js\"], got \"run_code\"",
    );
  });

  it('a template placeholder must be upper-snake dunder', () => {
    // The `values` record's `error` callback must branch on `issue.code`, so a malformed
    // placeholder keeps the KEY schema's message instead of the generic not-an-object text.
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { '{{x}}': { from: 'js_string', value: 'v' } } }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor \"eco\": templates[0].values.{{x}}: placeholder \"{{x}}\" must match __UPPER_SNAKE__",
    );
  });

  it('a template placeholder must match the WHOLE string, not just contain a valid dunder', () => {
    // PLACEHOLDER is /^__[A-Z_]+__$/ — anchored at both ends. This pins the leading anchor: extra
    // characters BEFORE a dunder-shaped substring must still be rejected.
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { 'X__FOO__': { from: 'js_string', value: 'v' } } }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor \"eco\": templates[0].values.X__FOO__: placeholder \"X__FOO__\" must match __UPPER_SNAKE__",
    );
  });

  it('a template placeholder with extra characters AFTER a valid dunder is also rejected', () => {
    // The trailing anchor: extra characters AFTER a dunder-shaped substring must also be rejected.
    const tpl = [{ src: 'eco.template.x.js', dest: 'x.js', values: { '__FOO__X': { from: 'js_string', value: 'v' } } }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor \"eco\": templates[0].values.__FOO__X: placeholder \"__FOO__X\" must match __UPPER_SNAKE__",
    );
  });

  it('a template src must be a template sibling', () => {
    const tpl = [{ src: 'plugin.js', dest: 'plugin.js', values: {} }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor \"eco\": templates[0].src: 'src' must be a flat '<eco>.template.<dest>' sibling, got \"plugin.js\"",
    );
  });

  it('role_entries_js requires a known role', () => {
    const tpl = [{
      src: 'eco.template.x.js', dest: 'x.js',
      values: { __E__: { from: 'role_entries_js', role: 'wizard', body_key: 'prompt' } },
    }];
    expectMessage(
      () => minimal({ templates: tpl }),
      "ecosystem descriptor \"eco\": templates[0].values.__E__.role: must be one of " +
        "[\"agent\",\"command\",\"default\",\"persona\"], got \"wizard\"",
    );
  });

  it('guard entries must be bare module filenames', () => {
    expectMessage(
      () => minimal({ guard: ['hooks/frozen_tests.py'] }),
      "ecosystem descriptor \"eco\": guard[0]: entries are module filenames (no '/'), got \"hooks/frozen_tests.py\"",
    );
  });

  it('smoke requires test, when cli is present', () => {
    expectMessage(
      () => minimal({ smoke: { cli: 'eco' } }),
      "ecosystem descriptor \"eco\": smoke.test: must be a non-empty string, got undefined",
    );
  });

  it('smoke requires cli, when test is present', () => {
    // Every other smoke-touching test in this suite supplies `cli`, so this is the only proof that
    // SmokeSchema requires it rather than it merely being present by convention.
    expectMessage(
      () => minimal({ smoke: { test: 'builder/tests/smoke/ecoSmoke.spec.ts' } }),
      "ecosystem descriptor \"eco\": smoke.cli: must be a non-empty string, got undefined",
    );
  });
});

describe('checkKeys is exercised with an unknown key for every distinct "what" label', () => {
  it('names the mode in a field-shape error: field (from=X)', () => {
    expectMessage(
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'k', from: 'stem', extra: 1 }] }),
      "ecosystem descriptor \"eco\": roles.agent.fields[0]: field (from=stem) has unknown key(s) [\"extra\"]",
    );
  });

  it('names the kind in a route-shape error: route (kind=X)', () => {
    expectMessage(
      () => minimal({ routes: [{ kind: 'omit', src: 'a.md', extra: 1 }] }),
      "ecosystem descriptor \"eco\": routes[0]: route (kind=omit) has unknown key(s) [\"extra\"]",
    );
  });

  it('names the protocol in a gate-shape error: gate (protocol=X)', () => {
    expectMessage(
      () => minimal({
        gate: {
          protocol: 'event_guards', allow: {}, deny: {}, user_key: 'u', agent_key: 'a', extra: 1,
        },
      }),
      "ecosystem descriptor \"eco\": gate: gate (protocol=event_guards) has unknown key(s) [\"extra\"]",
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
      "ecosystem descriptor \"eco\": templates[0].values.__X__: template value (from=js_string) has unknown key(s) [\"extra\"]",
    );
  });

  it('names an unknown key on the artifact shape itself', () => {
    expectMessage(
      () => minimal({ artifacts: [{ dest: 'p.json', content: {}, extra: 1 }] }),
      "ecosystem descriptor \"eco\": artifacts[0]: an artifact has unknown key(s) [\"extra\"]",
    );
  });

  it('names an unknown key on the template shape itself', () => {
    expectMessage(
      () => minimal({ templates: [{ src: 'eco.template.x', dest: 'x', values: {}, extra: 1 }] }),
      "ecosystem descriptor \"eco\": templates[0]: a template has unknown key(s) [\"extra\"]",
    );
  });

  it('names an unknown key on the smoke shape itself', () => {
    expectMessage(
      () => minimal({ smoke: { cli: 'eco', test: 't', extra: 1 } }),
      "ecosystem descriptor \"eco\": smoke: 'smoke' has unknown key(s) [\"extra\"]",
    );
  });

  it('names an unknown key on the smoke.expect shape', () => {
    expectMessage(
      () => minimal({ smoke: { cli: 'eco', test: 't', expect: { version_cmd: ['x'], extra: 1 } } }),
      "ecosystem descriptor \"eco\": smoke.expect: smoke 'expect' has unknown key(s) [\"extra\"]",
    );
  });

  it('sorts multiple unknown keys alphabetically rather than by input order', () => {
    // A filter().sort() chain: dropping the sort would report ['zzz', 'another', 'surprises'] in
    // whatever order Object.keys happened to iterate, not the documented sorted allowed-set style.
    expectMessage(
      () => minimal({ zzz: 1, another: 2, surprises: 3 }),
      "ecosystem descriptor \"eco\": descriptor has unknown key(s) [\"another\",\"surprises\",\"zzz\"]",
    );
  });

  // Each union VARIANT in descriptor.mts has its own objectError(...) call, so each is a separate
  // mutant. The tests above cover one variant per union; this table covers the remaining fourteen.
  it.each([
    [
      "field (from=frontmatter)",
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'k', from: 'frontmatter', field: 'f', extra: 1 }] }),
      "roles.agent.fields[0]: field (from=frontmatter) has unknown key(s) [\"extra\"]",
    ],
    [
      "field (from=literal)",
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'k', from: 'literal', value: 'v', extra: 1 }] }),
      "roles.agent.fields[0]: field (from=literal) has unknown key(s) [\"extra\"]",
    ],
    [
      "field (from=primary_mode)",
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'k', from: 'primary_mode', primary: 'p', extra: 1 }] }),
      "roles.agent.fields[0]: field (from=primary_mode) has unknown key(s) [\"extra\"]",
    ],
    [
      "field (from=flag_if_name_in)",
      () => withAgentRole({
        mode: 'fields', fields: [{ key: 'k', from: 'flag_if_name_in', names: ['n'], value: 'v', extra: 1 }],
      }),
      "roles.agent.fields[0]: field (from=flag_if_name_in) has unknown key(s) [\"extra\"]",
    ],
    [
      "role (mode=fields)",
      () => withAgentRole({ mode: 'fields', fields: [{ key: 'k', from: 'stem' }], extra: 1 }),
      "roles.agent: role (mode=fields) has unknown key(s) [\"extra\"]",
    ],
    [
      "role (mode=wrap)",
      () => withAgentRole({ mode: 'wrap', fields: [{ key: 'k', from: 'literal', value: 'v' }], extra: 1 }),
      "roles.agent: role (mode=wrap) has unknown key(s) [\"extra\"]",
    ],
    [
      "role (mode=plain)",
      () => withAgentRole({ mode: 'plain', extra: 1 }),
      "roles.agent: role (mode=plain) has unknown key(s) [\"extra\"]",
    ],
    [
      "role (mode=toml_command)",
      () => withAgentRole({ mode: 'toml_command', fields: [{ key: 'description', from: 'stem' }], extra: 1 }),
      "roles.agent: role (mode=toml_command) has unknown key(s) [\"extra\"]",
    ],
    [
      "route (kind=exact)",
      () => minimal({ routes: [{ kind: 'exact', src: 'a.md', dest: 'b.md', extra: 1 }] }),
      "routes[0]: route (kind=exact) has unknown key(s) [\"extra\"]",
    ],
    [
      "route (kind=suffix_swap)",
      () => minimal({
        routes: [{ kind: 'suffix_swap', prefix: 'x/', from_suffix: '.md', to_suffix: '.toml', extra: 1 }],
      }),
      "routes[0]: route (kind=suffix_swap) has unknown key(s) [\"extra\"]",
    ],
    [
      "template value (from=js_string_list)",
      () => minimal({
        templates: [{
          src: 'eco.template.x.js', dest: 'x.js',
          values: { __X__: { from: 'js_string_list', values: ['a'], extra: 1 } },
        }],
      }),
      "templates[0].values.__X__: template value (from=js_string_list) has unknown key(s) [\"extra\"]",
    ],
    [
      "template value (from=js_root_joins)",
      () => minimal({
        templates: [{
          src: 'eco.template.x.js', dest: 'x.js',
          values: { __X__: { from: 'js_root_joins', paths: ['a'], extra: 1 } },
        }],
      }),
      "templates[0].values.__X__: template value (from=js_root_joins) has unknown key(s) [\"extra\"]",
    ],
    [
      "template value (from=role_entries_js)",
      () => minimal({
        templates: [{
          src: 'eco.template.x.js', dest: 'x.js',
          values: { __X__: { from: 'role_entries_js', role: 'agent', body_key: 'b', extra: 1 } },
        }],
      }),
      "templates[0].values.__X__: template value (from=role_entries_js) has unknown key(s) [\"extra\"]",
    ],
    [
      "gate (protocol=pre_tool)",
      () => minimal({
        gate: { protocol: 'pre_tool', tools: { edit: 'Edit' }, path_keys: ['p'], deny: {}, reason_key: 'r', extra: 1 },
      }),
      "gate: gate (protocol=pre_tool) has unknown key(s) [\"extra\"]",
    ],
  ])('names the variant in an unknown-key error: %s', (_label, build, expected) => {
    expectMessage(build, `ecosystem descriptor "eco": ${expected}`);
  });
});
