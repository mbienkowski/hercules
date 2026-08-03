import { readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { buildDistribution } from '../../internal/builder/build.mjs';
import { loadRecipe, listRecipeNames } from '../../internal/builder/recipe-loader.mjs';
import { expectAsyncRefusal } from '../support/refusal';
import { recipeFixture, type RecipeFixture } from '../support/recipeWorkspace';
import { tempWorkspace } from '../support/tempWorkspace';

/**
 * A synthetic eighth distribution, hand-composed in a throwaway repository to exercise every choice
 * the recipe vocabulary allows at least once — so the ENGINE is proved apart from any real recipe.
 */

const NAME = 'synthetic-ci';

/** The synthetic tool's recipe, as it would be written by hand into `src/targets/synthetic-ci.json`. */
const SYNTHETIC = {
  name: NAME,
  variables: {
    product: 'Synthetic CI',
    host: 'Synthetic',
    // Liquid treats the STRING "false" as true, so a condition that must be off needs a real false.
    agent_tools: false,
    plan_mode: 'prose',
    // The host's own placeholder inside one of our values; nothing rescans a value, so it ships as written.
    plugin_root: '${SYNTHETIC_PLUGIN_ROOT}/',
    banner: 'shared',
  },
  runtime_variables: ['SYNTHETIC_PLUGIN_ROOT'],
  targets: {
    'AGENTS.md': { sources: ['src/content/persona.md'] },
    // Two sources joined in the order the entry lists them, one variable overridden for this file.
    'agents/deep/lead.md': {
      sources: ['src/content/head.md', 'src/content/agents/lead.md'],
      variables: { banner: 'lead-only' },
    },
    // The same source as `commands/prose.md`, sent down the other branch because this entry says so.
    'commands/tools.md': {
      sources: ['src/content/switch.md'],
      variables: { agent_tools: true, plan_mode: 'tool' },
    },
    'commands/prose.md': { sources: ['src/content/switch.md'] },
    'hooks/gate.py': { sources: ['src/scripts/hooks/gate.py'], permissions: '755' },
    'manifest.json': { sources: ['src/content/manifest.json'] },
    // An explicit decline — deliberately absent, which reads differently from silence.
    'settings.json': null,
  },
} as const;

const SOURCES: Readonly<Record<string, string>> = {
  'src/content/persona.md': [
    'You are the {{ product }} lead, running inside {{ host }}.',
    '',
    'Read {{ plugin_root }}protocols/workflow-protocol.md before you start.',
    'The host resolves ${SYNTHETIC_PLUGIN_ROOT} itself; we never do.',
    '',
    'Banner: {{ banner }}',
    '',
    '{% raw %}',
    '```liquid',
    'This is how a condition is written: {% if agent_tools %}…{% endif %}',
    '```',
    '{% endraw %}',
    '',
  ].join('\n'),
  'src/content/head.md': 'Banner: {{ banner }}\n',
  'src/content/agents/lead.md': '---\nname: lead\n---\n\nThe {{ host }} lead.\n',
  'src/content/switch.md': [
    'before',
    '{% if plan_mode == "tool" -%}',
    'Enter plan mode with the tool.',
    '{%- elsif plan_mode == "prose" -%}',
    'Say you are planning.',
    '{%- else -%}',
    'Nothing to say.',
    '{%- endif %}',
    '{% if agent_tools %}',
    'You may hand a subagent its own tools.',
    '{% endif %}',
    'after',
    '',
  ].join('\n'),
  'src/content/manifest.json': '{\n  "name": "hercules",\n  "version": "{{ version }}"\n}\n',
  'src/scripts/hooks/gate.py': '#!/usr/bin/env python3\nprint("gate")\n',
};

const workspace = tempWorkspace();
let fixture: RecipeFixture;
let outRoot: string;
let written: string[];

/** Write the synthetic repository, with `recipe` as `src/targets/synthetic-ci.json`. */
function seed(prefix: string, recipe: unknown): { f: RecipeFixture; file: string } {
  const f = recipeFixture(workspace.make(prefix));
  for (const [relativePath, text] of Object.entries(SOURCES)) f.file(relativePath, text);
  return { f, file: f.recipe(NAME, recipe) };
}

const read = (relativePath: string): string => readFileSync(join(outRoot, relativePath), 'utf-8');
// eslint-disable-next-line no-bitwise -- the permission bits are the assertion
const mode = (relativePath: string): string => (statSync(join(outRoot, relativePath)).mode & 0o777).toString(8);

beforeAll(async () => {
  const seeded = seed('hercules-synthetic-', SYNTHETIC);
  fixture = seeded.f;
  outRoot = join(fixture.root, 'out');
  written = await buildDistribution(loadRecipe(seeded.file, fixture.root), seeded.file, outRoot, fixture.root);
});

afterAll(workspace.cleanup);

describe('a synthetic eighth tool, built from the recipe vocabulary alone', () => {
  it('is one configuration file and zero lines of TypeScript', () => {
    // Every destination the recipe names is written, in the nested directories it asks for.
    expect(written).toEqual([
      'AGENTS.md', 'agents/deep/lead.md', 'commands/prose.md', 'commands/tools.md',
      'hooks/gate.py', 'manifest.json',
    ]);
    expect(read('AGENTS.md')).toContain('You are the Synthetic CI lead, running inside Synthetic.');
    expect(read('agents/deep/lead.md')).toContain('The Synthetic lead.');
  });

  it('an explicitly declined destination ships nothing', () => {
    expect(written, "a `null` entry says 'deliberately absent'").not.toContain('settings.json');
    expect(() => read('settings.json')).toThrow();
  });

  it('several sources become one file, in the order the entry lists them', () => {
    expect(read('agents/deep/lead.md')).toBe('Banner: lead-only\n\n---\nname: lead\n---\n\nThe Synthetic lead.\n');
  });

  it('a per-entry variable overrides the distribution\'s, for that file only', () => {
    expect(read('agents/deep/lead.md'), 'the entry said so').toContain('Banner: lead-only');
    expect(read('AGENTS.md'), 'everybody else keeps the shared value').toContain('Banner: shared');
  });

  it('every branch form selects: `if`, `elsif`, and a boolean that is really false', () => {
    // One source, two files, two branches — how a tool differs from its neighbour without a copy.
    expect(read('commands/tools.md')).toBe(
      'before\nEnter plan mode with the tool.\n\nYou may hand a subagent its own tools.\n\nafter\n',
    );
    // `agent_tools` is a real `false`; the STRING "false" would have taken the branch instead.
    expect(read('commands/prose.md')).toBe('before\nSay you are planning.\n\nafter\n');
  });

  it('a `${RUNTIME}` placeholder survives verbatim, from a value and from the source alike', () => {
    const text = read('AGENTS.md');
    expect(text, 'substituted from a variable whose VALUE holds the placeholder')
      .toContain('Read ${SYNTHETIC_PLUGIN_ROOT}/protocols/workflow-protocol.md');
    expect(text, 'written straight into the source').toContain('The host resolves ${SYNTHETIC_PLUGIN_ROOT} itself');
  });

  it('`{% raw %}` ships template syntax as the example it is', () => {
    expect(read('AGENTS.md')).toContain('This is how a condition is written: {% if agent_tools %}…{% endif %}');
  });

  it('the release version arrives as an ordinary variable — no dedicated mechanism', () => {
    const manifest = JSON.parse(read('manifest.json')) as Record<string, unknown>;
    expect(manifest['version']).toBe('9.9.9');
  });

  it('an entry gets the mode it asked for, and everything else 644', () => {
    expect(mode('hooks/gate.py')).toBe('755');
    expect(mode('AGENTS.md')).toBe('644');
  });

  it('a `null` tombstone REMOVES a variable, so the file that lost it fails loudly', async () => {
    // A key present with `null` would render falsy and silent, so a tombstone DELETES — turning the
    // same mistake into a refusal that names the file, the entry and the variable.
    const seeded = seed('hercules-synthetic-tombstone-', {
      ...SYNTHETIC,
      targets: {
        ...SYNTHETIC.targets,
        'commands/prose.md': { sources: ['src/content/switch.md'], variables: { agent_tools: null } },
      },
    });
    await expectAsyncRefusal(
      () => buildDistribution(
        loadRecipe(seeded.file, seeded.f.root), seeded.file, join(seeded.f.root, 'out'), seeded.f.root,
      ),
      ['commands/prose.md', 'src/content/switch.md', 'agent_tools'],
    );
  });

  it('never registers itself as a real tool', () => {
    // No `src/targets/synthetic-ci.json` exists in this checkout, so the directory scan never sees it.
    expect(listRecipeNames()).not.toContain(NAME);
  });
});
