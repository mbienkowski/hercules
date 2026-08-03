import { afterEach, describe, expect, it } from 'vitest';

import {
  checkWriteGate, findDuplicateKeys, loadRecipe, parseRecipeText, listRecipeNames,
} from '../../../internal/builder/recipe-loader.mjs';
import { expectRefusal } from '../../support/refusal';
import { readRepoFile } from '../../support/repo';
import { minimalRecipe, recipeFixture } from '../../support/recipeWorkspace';
import { tempWorkspace } from '../../support/tempWorkspace';

/**
 * Loading a recipe, and the four ways it is refused before it can lie. `JSON.parse` keeps the LAST of
 * two identical keys and reports nothing, so the duplicate scan runs on the bytes, before parsing.
 */
describe('loading a recipe', () => {
  const scratch = tempWorkspace();
  afterEach(scratch.cleanup);

  function fixture() {
    return recipeFixture(scratch.make('hercules-recipe-'));
  }

  describe('a duplicated key, caught on the bytes', () => {
    it('names the key and the line, where JSON.parse would have said nothing', () => {
      const text = `{
  "name": "ecosystem",
  "variables": {},
  "runtime_variables": [],
  "targets": {
    "agents/a.md": { "sources": ["src/content/a.md"] },
    "agents/a.md": { "sources": ["src/content/b.md"] }
  }
}
`;
      // Proof the loss is real and silent without this check: the parsed object holds ONE entry.
      expect(Object.keys((JSON.parse(text) as { targets: object }).targets)).toHaveLength(1);

      expectRefusal(
        () => parseRecipeText(text, 'src/targets/ecosystem.json'),
        ['src/targets/ecosystem.json', 'duplicate key', "'agents/a.md'", 'line 7'],
      );
    });

    it('reports a duplicate nested anywhere, not only at the top level', () => {
      const found = findDuplicateKeys('{"a": {"b": {"c": 1, "c": 2}}}');
      expect(found).toEqual([{ path: '(root)/a/b', key: 'c', line: 1 }]);
    });

    it('says nothing about repeated keys that live in DIFFERENT objects', () => {
      // A scanner tracking key names globally rather than per object refuses every real recipe.
      expect(findDuplicateKeys('{"x": {"sources": 1}, "y": {"sources": 2}}')).toEqual([]);
    });

    it('is not fooled by a key name appearing inside a string VALUE', () => {
      expect(findDuplicateKeys('{"a": "b", "c": "\\"a\\": 1"}')).toEqual([]);
    });
  });

  describe('the published vocabulary', () => {
    it('refuses a key the schema does not describe, and names it', () => {
      const message = expectRefusal(
        () => parseRecipeText(
          JSON.stringify(minimalRecipe('ecosystem', { description: 'a friendly note' })),
          'src/targets/ecosystem.json',
        ),
        ['src/targets/ecosystem.json', 'recipe.schema.json', 'description'],
      );
      expect(message).toContain('additional properties');
    });

    it('refuses permissions that are not octal, and points at the entry', () => {
      expectRefusal(
        () => parseRecipeText(
          JSON.stringify(minimalRecipe('ecosystem', {
            targets: { 'hooks/x.py': { sources: ['src/content/a.md'], permissions: '0o755' } },
          })),
          'src/targets/ecosystem.json',
        ),
        ['/targets/hooks~1x.py/permissions', 'pattern'],
      );
    });

    it('refuses an entry with no sources at all — an empty recipe line means nothing', () => {
      expectRefusal(
        () => parseRecipeText(
          JSON.stringify(minimalRecipe('ecosystem', { targets: { 'a.md': { sources: [] } } })),
          'src/targets/ecosystem.json',
        ),
        ['/targets/a.md/sources'],
      );
    });

    it('refuses a variable value that is neither text nor a real boolean', () => {
      expectRefusal(
        () => parseRecipeText(
          JSON.stringify(minimalRecipe('ecosystem', { variables: { tier: 3 } })),
          'src/targets/ecosystem.json',
        ),
        ['/variables/tier'],
      );
    });

    it('accepts `null` as an entry — an explicit "this tool ships no such file"', () => {
      const recipe = parseRecipeText(
        JSON.stringify(minimalRecipe('ecosystem', { targets: { 'a.md': null } })),
        'src/targets/ecosystem.json',
      );
      expect(recipe.targets['a.md']).toBeNull();
    });
  });

  describe('the rules a schema cannot state', () => {
    it('refuses a recipe whose name disagrees with its filename', () => {
      const f = fixture();
      f.file('src/content/readme.md', 'hi\n');
      f.recipe('cursor', minimalRecipe('claude-code'));
      expectRefusal(
        () => loadRecipe('src/targets/cursor.json', f.root),
        ['claude-code', 'cursor.json'],
      );
    });

    it('refuses a source that does not exist, naming the entry that wanted it', () => {
      const f = fixture();
      f.recipe('ecosystem', minimalRecipe('ecosystem'));
      expectRefusal(
        () => loadRecipe('src/targets/ecosystem.json', f.root),
        ['README.md', 'src/content/readme.md', 'do not exist'],
      );
    });

    it('refuses a name that is both ours to substitute and the host\'s to resolve', () => {
      const f = fixture();
      f.file('src/content/readme.md', 'hi\n');
      f.recipe('ecosystem', minimalRecipe('ecosystem', {
        variables: { PLUGIN_ROOT: 'x' },
        runtime_variables: ['PLUGIN_ROOT'],
      }));
      expectRefusal(
        () => loadRecipe('src/targets/ecosystem.json', f.root),
        ['PLUGIN_ROOT', 'runtime_variables'],
      );
    });

    it('catches the same collision when the clash is introduced by ONE entry', () => {
      const f = fixture();
      f.file('src/content/readme.md', 'hi\n');
      f.recipe('ecosystem', minimalRecipe('ecosystem', {
        runtime_variables: ['HOST_ROOT'],
        targets: { 'README.md': { sources: ['src/content/readme.md'], variables: { HOST_ROOT: 'x' } } },
      }));
      expectRefusal(() => loadRecipe('src/targets/ecosystem.json', f.root), ['HOST_ROOT', 'README.md']);
    });
  });

  describe('which distributions exist', () => {
    it('is the directory, and never counts the schemas that live beside them', () => {
      const f = fixture();
      f.file('src/targets/recipe.schema.json', '{}');
      f.file('src/targets/cursor.json', '{}');
      f.file('src/targets/codex.json', '{}');
      expect(listRecipeNames(`${f.root}/src/targets`)).toEqual(['codex', 'cursor']);
    });
  });

  describe('the vocabulary has exactly one description', () => {
    it('the schema on disk describes the keys the loader reads, and no others', () => {
      // Four keys wide, so generated types would be more machinery than they describe. Both ends are
      // pinned instead: this list is what `Recipe`/`RecipeEntry` declare, and it must equal the schema.
      const schema = JSON.parse(readRepoFile('src', 'targets', 'recipe.schema.json')) as {
        properties: Record<string, unknown>;
        required: string[];
        $defs: { entry: { properties: Record<string, unknown>; required: string[] } };
      };
      expect(Object.keys(schema.properties).sort())
        .toEqual(['$schema', 'name', 'runtime_variables', 'targets', 'variables']);
      expect(schema.required.sort()).toEqual(['name', 'runtime_variables', 'targets', 'variables']);
      expect(Object.keys(schema.$defs.entry.properties).sort())
        .toEqual(['permissions', 'sources', 'variables']);
      expect(schema.$defs.entry.required).toEqual(['sources']);
    });

    it('every configuration on disk points an editor at that same description', () => {
      for (const name of listRecipeNames()) {
        const config = JSON.parse(readRepoFile('src', 'targets', `${name}.json`)) as { $schema?: string };
        expect(config.$schema, `${name}.json must carry a $schema line`).toBeDefined();
      }
    });
  });

  describe('the write gate keeps its own schema', () => {
    it('accepts the shape the gate adapter really reads', () => {
      expect(() => checkWriteGate(
        JSON.stringify({
          when: 'after_write',
          allow: { permission: 'allow' },
          deny: { permission: 'deny' },
          user_key: 'userMessage',
          agent_key: 'agentMessage',
        }),
        'fixture',
      )).not.toThrow();
    });

    it('refuses a gate that asks BEFORE a write yet declares nothing that could refuse one', () => {
      // A `before_write` gate with no `deny`/`reason_at` ships a hook that structurally cannot say no.
      expectRefusal(
        () => checkWriteGate(JSON.stringify({ when: 'before_write' }), 'src/targets/codex.json'),
        ['src/targets/codex.json', 'recipe.schema.json#/$defs/writeGate', 'deny'],
      );
    });

    it('refuses a misspelled key rather than shipping a gate with no reason to give', () => {
      expectRefusal(
        () => checkWriteGate(
          JSON.stringify({ when: 'after_write', reasonAt: ['reason'] }),
          'fixture',
        ),
        ['reasonAt'],
      );
    });
  });
});
