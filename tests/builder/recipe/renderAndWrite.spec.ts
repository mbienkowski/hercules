import { readFileSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

import { createTemplateEngine } from '../../../internal/builder/template-engine.mjs';
import { renderEntry } from '../../../internal/builder/render-entry.mjs';
import { assertNamespacesDisjoint, buildVariableScope } from '../../../internal/builder/variable-scope.mjs';
import { readCanonicalVersion } from '../../../internal/release/version-files.mjs';
import { writeEntry } from '../../../internal/builder/write-entry.mjs';
import { expectAsyncRefusal, expectRefusal } from '../../support/refusal';
import { recipeFixture } from '../../support/recipeWorkspace';
import { tempWorkspace } from '../../support/tempWorkspace';

/**
 * The four stages between a recipe and a file on disk: scope, engine, render, write. Two traps — a
 * `null` value renders falsy where an ABSENT key stops the build, and the STRING "false" is truthy.
 */
describe('scope, engine, render, write', () => {
  const scratch = tempWorkspace();
  afterEach(scratch.cleanup);

  describe('the scope one file is rendered with', () => {
    it('overrides the distribution\'s variables key by key, leaving the rest alone', () => {
      expect(buildVariableScope({ host: 'Cursor', ns: '/' }, { ns: '/hercules:' }))
        .toEqual({ host: 'Cursor', ns: '/hercules:' });
    });

    it('REMOVES a key an entry tombstones, rather than storing a null', () => {
      const scope = buildVariableScope({ agent_tools: 'Read, Grep' }, { agent_tools: null });
      expect(Object.hasOwn(scope, 'agent_tools')).toBe(false);
    });

    it('makes a mention of a tombstoned variable fail loudly, not silently', async () => {
      const scope = buildVariableScope({ agent_tools: 'Read' }, { agent_tools: null });
      await expectAsyncRefusal(
        () => createTemplateEngine().parseAndRender('{% if agent_tools %}x{% endif %}', scope),
        ['agent_tools'],
      );
    });

    it('drops a global that is already null, so the same rule holds at both levels', () => {
      expect(buildVariableScope({ a: null, b: 'x' })).toEqual({ b: 'x' });
    });

    it('refuses a name claimed by both namespaces, naming it and where', () => {
      expectRefusal(
        () => assertNamespacesDisjoint(['a', 'PLUGIN_ROOT'], ['PLUGIN_ROOT'], 'src/targets/ecosystem.json'),
        ['src/targets/ecosystem.json', 'PLUGIN_ROOT'],
      );
    });
  });

  describe('the engine\'s strictness, pinned so an upgrade cannot loosen it', () => {
    const engine = createTemplateEngine();

    it.each([
      ['a substitution', '{{ missing }}'],
      ['an if', '{% if missing %}x{% endif %}'],
      ['an unless', '{% unless missing %}x{% endunless %}'],
      ['a case', '{% case missing %}{% when "a" %}x{% endcase %}'],
      ['a nested path', '{{ missing.deep }}'],
    ])('refuses an undeclared variable in %s', async (_label, template) => {
      await expectAsyncRefusal(() => engine.parseAndRender(template, {}), ['missing']);
    });

    it('treats the STRING "false" as TRUE — which is why the vocabulary admits real booleans', async () => {
      expect(await engine.parseAndRender('{% if v %}on{% else %}off{% endif %}', { v: 'false' })).toBe('on');
      expect(await engine.parseAndRender('{% if v %}on{% else %}off{% endif %}', { v: false })).toBe('off');
    });

    it('refuses a filter it does not know, rather than rendering nothing where one was meant', async () => {
      // Liquid's own built-ins remain: "zero filters" is a rule about CONTENT, held by the grammar lint.
      await expectAsyncRefusal(() => engine.parseAndRender('{{ v | nosuchfilter }}', { v: 'x' }), ['nosuchfilter']);
    });

    it('leaves a host\'s own ${…} placeholder exactly as written', async () => {
      const out = await engine.parseAndRender('read ${CLAUDE_PLUGIN_ROOT}/x for {{ host }}', { host: 'Claude' });
      expect(out).toBe('read ${CLAUDE_PLUGIN_ROOT}/x for Claude');
    });

    it('does not re-scan a substituted value for variables of its own', async () => {
      // One pass by construction: a variable whose VALUE holds a token ships that token verbatim.
      const out = await engine.parseAndRender('{{ plugin_root }}p.md', { plugin_root: '${CURSOR_PLUGIN_ROOT}/' });
      expect(out).toBe('${CURSOR_PLUGIN_ROOT}/p.md');
    });
  });

  const ctx = { config: 'src/targets/ecosystem.json', dest: 'agents/a.md', declared: ['host'] };

  describe('rendering one entry', () => {
    const resolve = (root: string) => (source: string) => join(root, source);

    it('joins its sources in the order the entry lists them', async () => {
      const f = recipeFixture(scratch.make('hercules-render-'));
      f.file('a.md', 'first\n');
      f.file('b.md', 'second\n');
      const out = await renderEntry(createTemplateEngine(), ['a.md', 'b.md'], {}, resolve(f.root), ctx);
      expect(out).toBe('first\n\nsecond\n');
    });

    it('names the configuration, the entry, the source AND the variable when one is missing', async () => {
      const f = recipeFixture(scratch.make('hercules-render-'));
      f.file('a.md', 'hello {{ agent_tools }}\n');
      const message = await expectAsyncRefusal(
        () => renderEntry(createTemplateEngine(), ['a.md'], { host: 'X' }, resolve(f.root), ctx),
        ['src/targets/ecosystem.json', 'agents/a.md', 'a.md', 'agent_tools'],
      );
      expect(message).toContain('not set in context for this ecosystem');
      expect(message).toContain('Declared here: host');
    });

    it('says which source could not be read, rather than failing with a bare path', async () => {
      const f = recipeFixture(scratch.make('hercules-render-'));
      await expectAsyncRefusal(
        () => renderEntry(createTemplateEngine(), ['gone.md'], {}, resolve(f.root), ctx),
        ['src/targets/ecosystem.json', 'agents/a.md', 'gone.md'],
      );
    });
  });

  describe('reading a source', () => {
    // A strict decode refuses a corrupted source; a kept byte-order mark leaves a source's first byte
    // alone. `fatal` and `ignoreBOM` are the two flags nothing else in the suite would miss.

    it('refuses a source that is not valid UTF-8 instead of shipping replacement characters', async () => {
      const f = recipeFixture(scratch.make('hercules-bytes-'));
      // 0xFF is not legal UTF-8; Node's default decode turns it into U+FFFD and ships the corruption.
      writeFileSync(join(f.root, 'bad.md'), Buffer.from([0x68, 0x69, 0xff, 0x0a]));
      await expectAsyncRefusal(
        () => renderEntry(createTemplateEngine(), ['bad.md'], {}, (s) => join(f.root, s), ctx),
        ['bad.md', 'not valid UTF-8'],
      );
    });

    it('keeps a byte-order mark rather than silently rewriting the first byte', async () => {
      const f = recipeFixture(scratch.make('hercules-bytes-'));
      writeFileSync(join(f.root, 'bom.md'), Buffer.from([0xef, 0xbb, 0xbf, 0x68, 0x69, 0x0a]));
      const out = await renderEntry(createTemplateEngine(), ['bom.md'], {}, (s) => join(f.root, s), ctx);
      expect(out.charCodeAt(0), 'the mark was stripped — the shipped file no longer starts as authored')
        .toBe(0xfeff);
    });

    it('accepts a source that legitimately CONTAINS a replacement character', async () => {
      // U+FFFD is itself valid UTF-8: a strict decode refuses malformed BYTES, not this glyph.
      const f = recipeFixture(scratch.make('hercules-bytes-'));
      f.file('ok.md', 'shows \uFFFD on purpose\n');
      const out = await renderEntry(createTemplateEngine(), ['ok.md'], {}, (s) => join(f.root, s), ctx);
      expect(out).toBe('shows \uFFFD on purpose\n');
    });
  });

  describe('writing the rendered file', () => {
    it('gives a file 644 when its entry asks for nothing', () => {
      const root = scratch.make('hercules-write-');
      const path = join(root, 'deep/nested/x.md');
      writeEntry(path, 'body\n');
      expect(readFileSync(path, 'utf-8')).toBe('body\n');
      // eslint-disable-next-line no-bitwise -- the permission bits are the assertion
      expect((statSync(path).mode & 0o777).toString(8)).toBe('644');
    });

    it('gives a file exactly the mode its entry asked for', () => {
      const root = scratch.make('hercules-write-');
      const path = join(root, 'hooks/gate.py');
      writeEntry(path, '#!/usr/bin/env python3\n', '755');
      // eslint-disable-next-line no-bitwise -- the permission bits are the assertion
      expect((statSync(path).mode & 0o777).toString(8)).toBe('755');
    });

    it('forces the mode even over a file that already exists with another one', () => {
      const root = scratch.make('hercules-write-');
      const path = join(root, 'x.md');
      writeFileSync(path, 'old', { mode: 0o600 });
      writeEntry(path, 'new\n');
      // eslint-disable-next-line no-bitwise -- the permission bits are the assertion
      expect((statSync(path).mode & 0o777).toString(8)).toBe('644');
    });
  });

  describe('the version stage', () => {
    it('reads the release version from the canonical files, not from a tag or a branch', () => {
      const f = recipeFixture(scratch.make('hercules-version-'));
      expect(readCanonicalVersion(f.root)).toBe('9.9.9');
    });

    it('refuses a checkout with no canonical version to read, instead of rendering an empty one', () => {
      const f = recipeFixture(scratch.make('hercules-version-'));
      f.file('package.json', `${JSON.stringify({ name: 'fixture' }, null, 2)}\n`);
      expectRefusal(() => readCanonicalVersion(f.root), ['package.json']);
    });
  });
});
