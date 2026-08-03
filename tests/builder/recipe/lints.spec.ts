import { afterEach, describe, expect, it } from 'vitest';

import { parseTemplateStructure, lintRecipes, type NamedRecipe } from '../../../internal/builder/recipe-lints.mjs';
import type { Recipe } from '../../../internal/builder/recipe-loader.mjs';
import { expectRefusal } from '../../support/refusal';
import { recipeFixture } from '../../support/recipeWorkspace';
import { tempWorkspace } from '../../support/tempWorkspace';

/**
 * The lints that make a silent build impossible. `strictVariables` stops a mistyped variable one at a
 * time from inside a template; these name the file, the line and every configuration that differs.
 */
describe('the recipe lints', () => {
  const scratch = tempWorkspace();
  afterEach(scratch.cleanup);

  /** One source rendered by `count` configurations, each declaring `variables`. */
  function world(source: string, configs: ReadonlyArray<Record<string, string | boolean>>) {
    const f = recipeFixture(scratch.make('hercules-lint-'));
    f.file('src/content/a.md', source);
    const recipes: NamedRecipe[] = configs.map((variables, index) => ({
      file: `src/targets/ecosystem${index}.json`,
      recipe: {
        name: `ecosystem${index}`,
        variables,
        runtime_variables: [],
        targets: { 'a.md': { sources: ['src/content/a.md'] } },
      } as unknown as Recipe,
    }));
    return { root: f.root, recipes };
  }

  function lint(source: string, configs: ReadonlyArray<Record<string, string | boolean>>): void {
    const { root, recipes } = world(source, configs);
    lintRecipes(recipes, root);
  }

  describe('the grammar: equality, and nothing else', () => {
    it.each([
      ['unless', '{% unless a %}x{% endunless %}\n'],
      ['a conjunction', '{% if a and b %}x{% endif %}\n'],
      ['a disjunction', '{% if a or b %}x{% endif %}\n'],
      ['an inequality', '{% if a != "x" %}x{% endif %}\n'],
      ['case', '{% case a %}{% when "x" %}y{% endcase %}\n'],
      ['a for loop', '{% for x in a %}y{% endfor %}\n'],
      ['an assignment', '{% assign a = "x" %}\n'],
    ])('refuses %s, naming the file and the line', (_label, source) => {
      expectRefusal(() => lint(source, [{ a: 'x', b: 'y' }]), ['src/content/a.md:1']);
    });

    it('refuses a filter in a substitution — a configuration stays data, so nothing transforms', () => {
      expectRefusal(() => lint('{{ a | upcase }}\n', [{ a: 'x' }]), ['src/content/a.md:1', 'upcase']);
    });

    it('refuses a dotted path, which would smuggle structure into a flat vocabulary', () => {
      expectRefusal(() => lint('{{ a.b }}\n', [{ a: 'x' }]), ['src/content/a.md:1', 'a.b']);
    });

    it('accepts the two permitted conditions and the one permitted substitution', () => {
      expect(() => lint(
        '{{ host }}\n{% if flag %}\non\n{% elsif mode == "quiet" %}\nq\n{% else %}\noff\n{% endif %}\n',
        [
          { host: 'A', flag: true, mode: 'loud' },
          { host: 'B', flag: false, mode: 'quiet' },
          { host: 'C', flag: false, mode: 'loud' },
        ],
      )).not.toThrow();
    });

    it('refuses a block that is never closed', () => {
      expectRefusal(() => lint('{% if a %}\nx\n', [{ a: 'x' }]), ['never closed']);
    });

    it('refuses an `endif` with nothing open', () => {
      expectRefusal(() => lint('{% endif %}\n', [{}]), ['no open']);
    });

    it('refuses `{{ … %}` rather than guessing which end was meant', () => {
      expectRefusal(() => parseTemplateStructure('{{ a %}\n', 'x.md'), ['mismatched delimiters']);
    });
  });

  describe('a variable mentioned but not declared', () => {
    it('names the configuration, the entry, the source and what WAS declared', () => {
      const message = expectRefusal(
        () => lint('hello {{ host }}\n', [{ product: 'Cursor' }]),
        ['src/targets/ecosystem0.json', "'a.md'", 'src/content/a.md', "'host'"],
      );
      expect(message).toContain('not set in context for this ecosystem');
      expect(message).toContain('Declared here: product, version');
    });

    it('reports EVERY problem at once, not the first of seven runs in a row', () => {
      const message = expectRefusal(() => lint('{{ host }} {{ ns }}\n', [{}, {}]));
      expect(message).toContain('4 problem(s) found');
    });
  });

  describe('a conditional variable is declared by every configuration that renders the source', () => {
    it('refuses the exact shape the old descriptors were in — declared in some, absent in others', () => {
      const message = expectRefusal(
        () => lint('{% if version_manifest %}\nx\n{% endif %}\n', [{ version_manifest: 'plugin_folder' }, {}]),
        ['src/targets/ecosystem1.json', 'version_manifest'],
      );
      expect(message).toContain('with `false` when the branch is not wanted, never by omission');
    });

    it('is satisfied by declaring it false — the branch is off, not missing', () => {
      expect(() => lint(
        '{% if version_manifest %}\nx\n{% endif %}\n',
        [{ version_manifest: 'plugin_folder' }, { version_manifest: false }],
      )).not.toThrow();
    });
  });

  describe('a branch label nobody assigns', () => {
    it('refuses a typo in a compared value, and lists the legal ones', () => {
      const message = expectRefusal(
        () => lint(
          '{% if mode == "quiett" %}\nx\n{% else %}\ny\n{% endif %}\n',
          [{ mode: 'quiet' }, { mode: 'loud' }],
        ),
        ['src/content/a.md:1', 'quiett'],
      );
      expect(message).toContain('"loud", "quiet"');
    });
  });

  describe('a branch that ships to nobody', () => {
    it('refuses a branch no configuration selects, so dead guidance cannot hide', () => {
      expectRefusal(
        () => lint(
          '{% if mode == "quiet" %}\nq\n{% elsif mode == "loud" %}\nl\n{% endif %}\n',
          [{ mode: 'quiet' }, { mode: 'quiet' }],
        ),
        ['ships to nobody', 'mode == "loud"'],
      );
    });

    it('allows a branch that one configuration selects and the others do not', () => {
      expect(() => lint(
        '{% if mode == "quiet" %}\nq\n{% else %}\nl\n{% endif %}\n',
        [{ mode: 'quiet' }, { mode: 'loud' }],
      )).not.toThrow();
    });

    it('treats an unreachable `else` as dead too — every configuration already matched', () => {
      expectRefusal(
        () => lint('{% if flag %}\nx\n{% else %}\ny\n{% endif %}\n', [{ flag: true }, { flag: 'yes' }]),
        ['ships to nobody', "'else'"],
      );
    });
  });

  describe('trim marks, which decide whether a blank line survives', () => {
    it('refuses a block tag that shares its line with other text', () => {
      expectRefusal(() => lint('before {% if a %}x{% endif %}\n', [{ a: true }]), ['stands alone on its line']);
    });

    it('refuses a trim mark next to a BLANK line, which it would silently swallow', () => {
      const message = expectRefusal(
        () => lint('head\n{% if a -%}\n\nx\n{% endif %}\n', [{ a: true }]),
        ['swallow the blank line'],
      );
      expect(message).toContain('right trim mark');
    });

    it('refuses the same on the closing side', () => {
      expectRefusal(
        () => lint('head\n{% if a %}\nx\n\n{%- endif %}\n', [{ a: true }]),
        ['left trim mark', 'swallow the blank line'],
      );
    });

    it('accepts the two forms that are unambiguous: a trim mark against real text, or none at all', () => {
      expect(() => lint('head\n{% if a -%}\nx\n{%- endif %}\ntail\n', [{ a: true }])).not.toThrow();
      expect(() => lint('head\n{% if a %}\nx\n\ny\n{% endif %}\ntail\n', [{ a: true }])).not.toThrow();
    });
  });

  describe('template syntax quoted in prose', () => {
    it('refuses an un-escaped tag inside a fenced code block, and explains why', () => {
      const source = 'See:\n\n```yaml\nrun: echo ${{ github.sha }}\n```\n';
      const message = expectRefusal(() => lint(source, [{}]), ['src/content/a.md:4']);
      expect(message).toContain('{% raw %}');
    });

    it('accepts the same example once it is wrapped in raw', () => {
      const source = 'See:\n\n{% raw %}\n```yaml\nrun: echo ${{ github.sha }}\n```\n{% endraw %}\n';
      expect(() => lint(source, [{}])).not.toThrow();
    });
  });

  describe('what counts as a fenced code block', () => {
    // The four cases `fencedRanges`/`inRanges` gets wrong unwatched: tilde fences dropped, an
    // unterminated fence truncated to nothing, the boundary off by one, capitals in a name.

    it('treats a tilde fence exactly like a backtick fence', () => {
      // Markdown allows both. A tag quoted inside `~~~` is just as much a quotation.
      const source = 'See:\n\n~~~\n{% if flag %}\nx\n{% endif %}\n~~~\n';
      expectRefusal(() => lint(source, [{ flag: true }]), ['fenced code block', '{% raw %}']);
    });

    it('treats an unterminated fence as running to the end of the file', () => {
      // An unclosed fence swallows the document; reading it as empty lets every later tag through.
      const source = 'See:\n\n```\nnot closed\n\n{% if flag %}\nx\n{% endif %}\n';
      expectRefusal(() => lint(source, [{ flag: true }]), ['fenced code block']);
    });

    it('does not swallow a tag that starts exactly where the fence ends', () => {
      // Half-open on purpose: one character of slack classifies a live conditional after a fence as quoted.
      const source = 'a\n\n```\nquoted\n```\n{% if flag %}\nlive\n{% endif %}\ntail\n';
      expect(() => lint(source, [{ flag: true }, { flag: false }])).not.toThrow();
    });

    it('refuses a variable name with capitals, which belongs to the host, not to us', () => {
      // `${NAME}` is the HOST's and passes through verbatim; `{{ name }}` is ours — never blur the two.
      expectRefusal(() => lint('{{ PLUGIN_ROOT }}\n', [{ PLUGIN_ROOT: 'x' }]), ['not a permitted substitution']);
    });
  });

  describe('guard-the-guard', () => {
    it('refuses to report a clean bill of health with no recipes to inspect', () => {
      expectRefusal(() => lintRecipes([], scratch.make('hercules-lint-')), ['no recipes']);
    });

    it('refuses when the recipes exist but declare no rendered source at all', () => {
      const f = recipeFixture(scratch.make('hercules-lint-'));
      const recipes = [{
        file: 'src/targets/ecosystem.json',
        recipe: { name: 'ecosystem', variables: {}, runtime_variables: [], targets: { 'a.md': null } } as unknown as Recipe,
      }];
      expectRefusal(() => lintRecipes(recipes, f.root), ['no source is rendered']);
    });
  });
});
