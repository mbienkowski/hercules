import { readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

import { buildDistribution, loadAllRecipes, main, parseCommandLine } from '../../../internal/builder/build.mjs';
import { checkWriteGate, loadRecipe, listRecipeNames } from '../../../internal/builder/recipe-loader.mjs';
import { expectAsyncRefusal, expectRefusal } from '../../support/refusal';
import { recipeFixture } from '../../support/recipeWorkspace';
import { repoRoot } from '../../support/repo';
import { tempWorkspace } from '../../support/tempWorkspace';

/**
 * The whole build end to end on a scratch repository, and the trim rule everything rests on: a block
 * tag carries a trim mark toward the branch body when that edge contributes NO blank line, and none
 * when it contributes exactly ONE. Two real blocks need the second form, twenty-five the first.
 */
describe('the recipe build, end to end', () => {
  const scratch = tempWorkspace();
  afterEach(scratch.cleanup);

  function fixture() {
    return recipeFixture(scratch.make('hercules-build-'));
  }

  async function render(
    f: ReturnType<typeof recipeFixture>,
    name: string,
    recipe: unknown,
  ): Promise<(relativePath: string) => string> {
    const file = f.recipe(name, recipe);
    const out = join(f.root, 'out');
    await buildDistribution(loadRecipe(file, f.root), file, out, f.root);
    return (relativePath: string) => readFileSync(join(out, relativePath), 'utf-8');
  }

  describe('the trim rule that reproduces the old line-based switch', () => {
    const CONFIGS = [
      { plan_mode: 'tool', plan_enter: 'plan mode' },
      { plan_mode: 'prose', plan_enter: 'prose' },
    ];

    it('a trim mark on both edges contributes no blank line of its own', async () => {
      const f = fixture();
      f.file('src/content/a.md', [
        'before',
        '{% if plan_mode == "tool" -%}',
        'opened with `{{ plan_enter }}`,',
        '{%- else -%}',
        'plan mode,',
        '{%- endif %}',
        'after',
        '',
      ].join('\n'));
      const read = await render(f, 'tool', {
        name: 'tool',
        variables: CONFIGS[0],
        runtime_variables: [],
        targets: { 'a.md': { sources: ['src/content/a.md'] } },
      });
      expect(read('a.md')).toBe('before\nopened with `plan mode`,\nafter\n');
    });

    it('the same block, on the tool that takes the other branch', async () => {
      const f = fixture();
      f.file('src/content/a.md', [
        'before',
        '{% if plan_mode == "tool" -%}',
        'tool',
        '{%- else -%}',
        'prose',
        '{%- endif %}',
        'after',
        '',
      ].join('\n'));
      const read = await render(f, 'prose', {
        name: 'prose',
        variables: CONFIGS[1],
        runtime_variables: [],
        targets: { 'a.md': { sources: ['src/content/a.md'] } },
      });
      expect(read('a.md')).toBe('before\nprose\nafter\n');
    });

    it('a block nobody matches leaves exactly the one blank line the old build left', async () => {
      const f = fixture();
      f.file('src/content/a.md', [
        'before',
        '{% if backstop == "settable" -%}',
        'settable',
        '{%- elsif backstop == "notify" -%}',
        'notify',
        '{%- endif %}',
        'after',
        '',
      ].join('\n'));
      const read = await render(f, 'neither', {
        name: 'neither',
        variables: { backstop: 'none' },
        runtime_variables: [],
        targets: { 'a.md': { sources: ['src/content/a.md'] } },
      });
      expect(read('a.md')).toBe('before\n\nafter\n');
    });

    it('NO trim mark contributes exactly one blank line at that edge', async () => {
      // The form the two real blocks in `commands/build.md` and `commands/design.md` need: greedy
      // trimming eats the blank line either side and the shipped file loses two paragraph breaks.
      const f = fixture();
      f.file('src/content/a.md', [
        'before',
        '{% if forced == "no" %}',
        'first paragraph',
        '',
        'second paragraph',
        '{% endif %}',
        'after',
        '',
      ].join('\n'));
      const on = await render(f, 'on', {
        name: 'on',
        variables: { forced: 'no' },
        runtime_variables: [],
        targets: { 'a.md': { sources: ['src/content/a.md'] } },
      });
      expect(on('a.md')).toBe('before\n\nfirst paragraph\n\nsecond paragraph\n\nafter\n');

      const g = fixture();
      g.file('src/content/a.md', readFileSync(join(f.root, 'src/content/a.md'), 'utf-8'));
      const off = await render(g, 'off', {
        name: 'off',
        variables: { forced: 'yes' },
        runtime_variables: [],
        targets: { 'a.md': { sources: ['src/content/a.md'] } },
      });
      expect(off('a.md')).toBe('before\n\nafter\n');
    });
  });

  describe('what the build must never touch', () => {
    it('leaves a host runtime placeholder exactly as written, including inside a variable\'s value', async () => {
      const f = fixture();
      f.file('src/content/a.md', 'Read {{ plugin_root }}protocols/x.md via ${CURSOR_PLUGIN_ROOT}\n');
      const read = await render(f, 'ecosystem', {
        name: 'ecosystem',
        variables: { plugin_root: '${CURSOR_PLUGIN_ROOT}/' },
        runtime_variables: ['CURSOR_PLUGIN_ROOT'],
        targets: { 'a.md': { sources: ['src/content/a.md'] } },
      });
      expect(read('a.md')).toBe('Read ${CURSOR_PLUGIN_ROOT}/protocols/x.md via ${CURSOR_PLUGIN_ROOT}\n');
    });

    it('passes a run of quotes and a trailing backslash into a TOML body untouched', async () => {
      // Zero filters means zero transformation; what makes that safe is that the result still decodes.
      const f = fixture();
      f.file('src/content/toml.md', [
        'description = "{{ title }}"',
        'prompt = """',
        'a run of quotes: \'\'\' and a trailing backslash: \\',
        'still the same paragraph',
        '"""',
        '',
      ].join('\n'));
      const read = await render(f, 'gem', {
        name: 'gem',
        variables: { title: 'Design the solution' },
        runtime_variables: [],
        targets: { 'command.toml': { sources: ['src/content/toml.md'] } },
      });
      const out = read('command.toml');
      expect(out).toContain('description = "Design the solution"');
      expect(out).toContain('a trailing backslash: \\');
      expect(out).toContain("''' ");
    });
  });

  describe('the shape of the tree it writes', () => {
    it('writes every declared file, in nested directories, and skips every declined one', async () => {
      const f = fixture();
      f.file('src/content/a.md', 'a\n');
      const read = await render(f, 'ecosystem', {
        name: 'ecosystem',
        variables: {},
        runtime_variables: [],
        targets: {
          'agents/deep/a.md': { sources: ['src/content/a.md'] },
          'agents/b.md': null,
        },
      });
      expect(read('agents/deep/a.md')).toBe('a\n');
      expect(() => read('agents/b.md')).toThrow();
    });

    it('joins several sources into one file, in the order the entry lists them', async () => {
      const f = fixture();
      f.file('src/content/head.md', 'head\n');
      f.file('src/content/tail.md', 'tail\n');
      const read = await render(f, 'ecosystem', {
        name: 'ecosystem',
        variables: {},
        runtime_variables: [],
        targets: { 'x.md': { sources: ['src/content/tail.md', 'src/content/head.md'] } },
      });
      expect(read('x.md')).toBe('tail\n\nhead\n');
    });

    it('gives a hook the mode its entry asked for, and everything else 644', async () => {
      const f = fixture();
      f.file('src/scripts/hooks/gate.py', 'print(1)\n');
      f.file('src/content/a.md', 'a\n');
      const file = f.recipe('ecosystem', {
        name: 'ecosystem',
        variables: {},
        runtime_variables: [],
        targets: {
          'hooks/gate.py': { sources: ['src/scripts/hooks/gate.py'], permissions: '755' },
          'a.md': { sources: ['src/content/a.md'] },
        },
      });
      const out = join(f.root, 'out');
      await buildDistribution(loadRecipe(file, f.root), file, out, f.root);
      // eslint-disable-next-line no-bitwise -- the permission bits are the assertion
      const mode = (relativePath: string) => (statSync(join(out, relativePath)).mode & 0o777).toString(8);
      expect(mode('hooks/gate.py')).toBe('755');
      expect(mode('a.md')).toBe('644');
    });

    it('hands every render the release version, without any dedicated version mechanism', async () => {
      const f = fixture();
      f.file('src/content/manifest.json', '{ "version": "{{ version }}" }\n');
      const read = await render(f, 'ecosystem', {
        name: 'ecosystem',
        variables: {},
        runtime_variables: [],
        targets: { 'plugin.json': { sources: ['src/content/manifest.json'] } },
      });
      expect(read('plugin.json')).toBe('{ "version": "9.9.9" }\n');
    });

    it('checks a rendered write gate against its own schema, because that one is security', async () => {
      const f = fixture();
      f.file('src/content/gate.json', '{ "when": "before_write" }\n');
      const file = f.recipe('ecosystem', {
        name: 'ecosystem',
        variables: {},
        runtime_variables: [],
        targets: { 'hooks/write_gate.json': { sources: ['src/content/gate.json'] } },
      });
      await expectAsyncRefusal(
        () => buildDistribution(loadRecipe(file, f.root), file, join(f.root, 'out'), f.root),
        ['hooks/write_gate.json', 'recipe.schema.json#/$defs/writeGate'],
      );
    });
  });

  describe('against the real repository', () => {
    it('every real write gate still answers to its own schema', () => {
      // The write gate is a security surface: the shipped adapter reads these keys to decide whether
      // a host may refuse an edit, so a `reason_at` typo ships a gate with no reason to give.
      const gates = listRecipeNames()
        .map((name) => loadRecipe(`src/targets/${name}.json`, repoRoot))
        .flatMap((recipe) => Object.entries(recipe.targets)
          .filter(([dest, entry]) => dest.endsWith('hooks/write_gate.json') && entry !== null)
          .map(([, entry]) => (entry as { sources: string[] }).sources[0] as string));
      expect(gates.length, 'no write gate found — this check would pass on an empty list').toBeGreaterThan(0);
      for (const source of gates) {
        expect(() => checkWriteGate(readFileSync(join(repoRoot, source), 'utf-8'), source)).not.toThrow();
      }
    });
  });

  describe('the command-line contract', () => {
    it.each([
      [['--target', 'cursor'], { target: 'cursor', check: false }],
      [['--target=cursor'], { target: 'cursor', check: false }],
      [['--target', 'all', '--check'], { target: 'all', check: true }],
      [[], { target: 'all', check: false }],
    ])('parses %j', (argv, expected) => {
      expect(parseCommandLine(argv)).toEqual(expected);
    });

    it('refuses an argument it does not recognise instead of building the wrong thing', () => {
      // `--target=cursor` falling through unmatched defaults to `all`: a build that looks right.
      expectRefusal(() => parseCommandLine(['--targets=cursor']), ['--targets=cursor']);
      expectRefusal(() => parseCommandLine(['--target']), ['requires a value']);
    });

    it('refuses an unknown target by name, and lists the ones that exist', async () => {
      const f = fixture();
      f.file('src/content/a.md', 'a\n');
      f.recipe('cursor', { name: 'cursor', variables: {}, runtime_variables: [], targets: { 'a.md': { sources: ['src/content/a.md'] } } });
      await expectAsyncRefusal(
        () => main(['--target', 'nope'], join(f.root, 'dist'), f.root),
        ['nope', 'cursor'],
      );
    });

    it('runs the lints even when only ONE target was asked for', async () => {
      // Otherwise `--target cursor` skips "is this variable declared in all seven?", unanswerable from one.
      const f = fixture();
      f.file('src/content/a.md', '{% if flag %}\nx\n{% endif %}\n');
      const entry = { 'a.md': { sources: ['src/content/a.md'] } };
      f.recipe('cursor', { name: 'cursor', variables: { flag: true }, runtime_variables: [], targets: entry });
      f.recipe('codex', { name: 'codex', variables: {}, runtime_variables: [], targets: entry });
      await expectAsyncRefusal(
        () => main(['--target', 'cursor'], join(f.root, 'dist'), f.root),
        ['src/targets/codex.json', 'flag'],
      );
    });

    it('exits 0 when the committed tree matches, and 1 with the reason when it does not', async () => {
      const f = fixture();
      f.file('src/content/a.md', 'a\n');
      f.recipe('ecosystem', { name: 'ecosystem', variables: {}, runtime_variables: [], targets: { 'a.md': { sources: ['src/content/a.md'] } } });
      const dist = join(f.root, 'dist');
      expect(await main([], dist, f.root)).toBe(0);
      expect(await main(['--check'], dist, f.root)).toBe(0);

      f.file('src/content/a.md', 'edited\n');
      const said: string[] = [];
      const original = process.stderr.write.bind(process.stderr);
      process.stderr.write = ((chunk: string) => { said.push(String(chunk)); return true; }) as typeof process.stderr.write;
      try {
        expect(await main(['--check'], dist, f.root)).toBe(1);
      } finally {
        process.stderr.write = original;
      }
      expect(said.join('')).toContain('ecosystem/a.md — STALE content');
    });

    it('reads the list of distributions off the directory, never a list in code', async () => {
      const f = fixture();
      f.file('src/content/a.md', 'a\n');
      for (const name of ['cursor', 'codex', 'grok-build']) {
        f.recipe(name, { name, variables: {}, runtime_variables: [], targets: { 'a.md': { sources: ['src/content/a.md'] } } });
      }
      expect(loadAllRecipes(f.root).map((r) => r.recipe.name)).toEqual(['codex', 'cursor', 'grok-build']);
    });
  });
});
