import { readFileSync, readdirSync, realpathSync } from 'node:fs';
import { join } from 'node:path';
import { createRequire } from 'node:module';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { buildDistribution } from '../../../internal/builder/build.mjs';
import { loadRecipe } from '../../../internal/builder/recipe-loader.mjs';
import { repoRoot } from '../../support/repo';
import { tempWorkspace } from '../../support/tempWorkspace';

/**
 * OpenCode reads agents and commands at run time from the `agents/*.md` and `commands/*.md` files
 * beside `plugin.js`. Loads the built plugin the way OpenCode does, and reads back what it registers.
 */

const RECIPE_FILE = 'src/targets/opencode.json';
const LEAD = 'hercules';
const COMMAND_PREFIX = 'hercules:';

interface Entry { description?: string; mode?: string; agent?: string; prompt?: string; template?: string }
interface Config {
  default_agent?: string;
  instructions?: string[];
  agent?: Record<string, Entry>;
  command?: Record<string, Entry>;
  skills?: { paths?: string[] };
  subagent_depth?: number;
}

const workspace = tempWorkspace();
let out: string;
let gateConfig: Config;

/** The body of a shipped markdown file: everything after the frontmatter, trimmed. */
function body(relativePath: string): string {
  return readFileSync(join(out, relativePath), 'utf-8').replace(/^---\n[\s\S]*?\n---\n?/, '').trim();
}

function stems(dir: string): string[] {
  return readdirSync(join(out, dir)).filter((n) => n.endsWith('.md')).map((n) => n.slice(0, -3)).sort();
}

beforeAll(async () => {
  out = join(workspace.make('hercules-opencode-build-'), 'opencode');
  await buildDistribution(loadRecipe(RECIPE_FILE, repoRoot), RECIPE_FILE, out, repoRoot);
  // The plugin's own start-up preflight throws if an asset it names is missing, so this also proves
  // the tree it expects is the tree we built.
  const plugin = createRequire(import.meta.url)(join(out, 'plugin.js')) as {
    id: string;
    server: (input: { directory: string }) => Promise<{ config: (gateConfig: Config) => void }>;
  };
  expect(plugin.id, 'a path-installed OpenCode plugin must export a top-level id').toBe('hercules');
  gateConfig = {};
  (await plugin.server({ directory: out })).config(gateConfig);
});

afterAll(workspace.cleanup);

describe('the OpenCode plugin serves exactly the files shipped beside it', () => {
  it('registers every shipped agent, and nothing it did not ship', () => {
    expect(stems('agents').length, 'no agents were shipped').toBeGreaterThan(0);
    expect(Object.keys(gateConfig.agent ?? {}).sort()).toEqual(stems('agents'));
    expect(gateConfig.default_agent, 'hercules is the primary out of the box').toBe(LEAD);
  });

  it('registers every shipped command under the hercules prefix, and nothing else', () => {
    expect(stems('commands').length, 'no commands were shipped').toBeGreaterThan(0);
    expect(Object.keys(gateConfig.command ?? {}).sort()).toEqual(stems('commands').map((s) => `${COMMAND_PREFIX}${s}`));
  });

  it('every agent is served from its own shipped file, not a second copy of it', () => {
    for (const stem of stems('agents')) {
      const entry = (gateConfig.agent as Record<string, Entry>)[stem] as Entry;
      expect(entry.description, `${stem}: empty agent description reaches the UI`).toBeTruthy();
      expect(entry.mode, `${stem}: no mode, so OpenCode cannot place the agent`).toBeTruthy();
      expect(entry.prompt, `${stem}: the served prompt is not the shipped file's body`)
        .toBe(body(`agents/${stem}.md`));
    }
  });

  it('every command is served from its own shipped file, with a clean prompt', () => {
    // Each failure here is silent: an unusable UI entry, a command bound to whatever agent is
    // current, and a template opening with `---` that feeds raw YAML to the model.
    for (const stem of stems('commands')) {
      const entry = (gateConfig.command as Record<string, Entry>)[`${COMMAND_PREFIX}${stem}`] as Entry;
      expect(entry.description, `${stem}: empty command description reaches the UI`).toBeTruthy();
      expect(entry.agent, `${stem}: command not bound to the hercules agent`).toBe(LEAD);
      const template = entry.template as string;
      expect(template.trimStart().startsWith('---'), `${stem}: template still embeds YAML frontmatter`).toBe(false);
      expect(template, `${stem}: Claude key leaked into template`).not.toContain('disable-model-invocation');
      expect(template, `${stem}: the served template is not the shipped file's body`)
        .toBe(body(`commands/${stem}.md`));
    }
  });

  it('points OpenCode at the persona, the protocols and the skills it shipped', () => {
    // The plugin injects absolute paths — OpenCode has no plugin-root placeholder — so each must name
    // a file really there. Compared on real paths: plugin.js resolves its own /private-prefixed dir.
    const root = realpathSync(out);
    const instructions = gateConfig.instructions ?? [];
    expect(instructions.length).toBeGreaterThan(0);
    for (const path of instructions) {
      expect(path.startsWith(root), `${path}: not a file this distribution shipped`).toBe(true);
      expect(() => readFileSync(path, 'utf-8'), `${path}: instruction file missing`).not.toThrow();
    }
    expect(gateConfig.skills?.paths).toContain(join(root, 'skills'));
  });

  it('publishes its own directory so a shipped tool is never run from the user repository', () => {
    // OpenCode names no plugin-root variable of its own, so the plugin exports one. Without it the
    // prose would say `python3 tools/<name>.py`, resolved against the repository being worked on —
    // and a checkout carrying that path would have its own file executed with the user's authority.
    const root = realpathSync(out);
    expect(realpathSync(process.env['HERCULES_PLUGIN_ROOT'] as string)).toBe(root);
  });

  it('names that variable in the recipe, so the builder leaves it for the host to resolve', () => {
    // A variable the recipe substitutes would be baked in at build time and point at this machine.
    const recipe = loadRecipe(RECIPE_FILE, repoRoot);
    expect(recipe.runtime_variables).toContain('HERCULES_PLUGIN_ROOT');
    expect(recipe.variables['plugin_root']).toBe('${HERCULES_PLUGIN_ROOT}/');
  });

  it('anchors every invocation of a shipped program in what it actually serves', () => {
    // Read from the REGISTERED command bodies rather than the files, so this covers what an agent is
    // really handed. An unanchored call is the whole defect, not a formatting preference.
    const served = Object.values(gateConfig.command ?? {}).map((entry) => entry.template ?? '');
    expect(served.length).toBeGreaterThan(0);
    const offenders = served.flatMap((text) =>
      [...text.matchAll(/python3?\s+("?)([^\s"']+\.py)\1/g)]
        .map(([, , target]) => target ?? '')
        .filter((target) => /(?:^|\/)(tools|hooks)\//.test(target) && !target.startsWith('$')));
    expect(offenders).toEqual([]);
  });
});
