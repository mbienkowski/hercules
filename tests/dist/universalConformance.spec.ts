import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { buildDistribution, loadAllRecipes } from '../../internal/builder/build.mjs';
import { findDifferences } from '../../internal/builder/dist-diff.mjs';
import { listRecipeNames, type Recipe } from '../../internal/builder/recipe-loader.mjs';
import { readCanonicalVersion } from '../../internal/release/version-files.mjs';
import { filesUnder, frontmatterKeys, isFile, srcStems, topLevelEntries } from '../support/buildTree';
import { repoRoot } from '../support/repo';
import { tempWorkspace } from '../support/tempWorkspace';

// Conformance for every registered distribution against CONFORMANCE_EXPECTATIONS: a hand-authored,
// fail-closed table never derived from the recipes, so a wrong recipe edit fails HERE, not silently.

const SRC_CONTENT = join(repoRoot, 'src', 'content');
/** The one name a user installs, every marketplace lists, and every manifest must agree on. */
const PLUGIN = 'hercules';
const CLAUDE_ISM = /CLAUDE\.md|E(?:nter|xit)PlanMode|\bClaude\b/;
const PLAN_IDIOMS = ['(`auto`)', 'EnterPlanMode', 'ExitPlanMode'];

/**
 * The `${NAME}` mentions in a shipped file that are PROSE about another host, not tokens. Keyed by
 * destination and spelled out by name — never a wildcard — so no new leak hides inside an exclusion.
 */
const PROSE_PLACEHOLDERS: Readonly<Record<string, readonly string[]>> = {
  'hooks/frozen_tests.py': ['CLAUDE_PLUGIN_ROOT'],
  'CAPABILITIES.md': ['CLAUDE_PLUGIN_ROOT', 'CURSOR_PLUGIN_ROOT'],
  'plugin.js': ['CLAUDE_PLUGIN_ROOT'],
};

interface Expectation {
  commandMarkerBanned: boolean;
  personaDest: string;
  agentDest: (stem: string) => string;
  commandDest: (stem: string) => string;
  commandFormat: 'frontmatter' | 'toml';
  /** Some hosts invoke a command by its `name:`, the rest by filename; missing that key makes the command absent, not broken. */
  commandKeysRequired: readonly string[];
  agentKeysRequired: readonly string[];
  agentKeysForbidden: readonly string[];
  orchestratorPrefix: string;
  neutralityPattern: RegExp | null;
  neutralityExempt: readonly string[];
  planIdiomsBanned: boolean;
  topLevel: ReadonlySet<string>;
  pins: ReadonlyArray<readonly [string, string]>;
  antiPins: ReadonlyArray<readonly [string, string]>;
}

// ecosystem-tax:start — one entry per host, so this block grows with every tool we support.
// Measured and capped by tests/budgets/ecosystemTax.spec.ts.
const CONFORMANCE_EXPECTATIONS: Record<string, Expectation> = {
  'claude-code': {
    commandMarkerBanned: false,
    personaDest: 'CLAUDE.md',
    agentDest: (s) => `agents/${s}.md`,
    commandDest: (s) => `commands/${s}.md`,
    commandFormat: 'frontmatter',
    commandKeysRequired: ['description'],
    agentKeysRequired: ['name', 'description', 'model'],
    agentKeysForbidden: ['model_tier'],
    orchestratorPrefix: '---\nname: hercules\ndescription: ',
    neutralityPattern: null,
    neutralityExempt: [],
    planIdiomsBanned: false,
    topLevel: new Set(['.claude-plugin', 'CLAUDE.md', 'agents', 'commands', 'hooks', 'protocols', 'settings.json', 'skills', 'tools']),
    pins: [
      ['agents/hercules.md', '\nmodel: opus\n'],
      ['hooks/hooks.json', '${CLAUDE_PLUGIN_ROOT}/hooks/frozen_tests.py'],
    ],
    antiPins: [['agents/hercules.md', 'model_tier']],
  },
  opencode: {
    commandMarkerBanned: true,
    personaDest: 'instructions.md',
    agentDest: (s) => `agents/${s}.md`,
    commandDest: (s) => `commands/${s}.md`,
    commandFormat: 'frontmatter',
    commandKeysRequired: ['description', 'agent'],
    agentKeysRequired: ['name', 'description', 'mode'],
    agentKeysForbidden: ['model', 'model_tier', 'tools'],
    orchestratorPrefix: '---\nname: hercules\ndescription: ',
    neutralityPattern: CLAUDE_ISM,
    neutralityExempt: ['plugin.js', 'CAPABILITIES.md', 'hooks/'],
    planIdiomsBanned: true,
    topLevel: new Set(['CAPABILITIES.md', 'agents', 'commands', 'hooks', 'instructions.md', 'opencode.json', 'plugin.js', 'protocols', 'read-file.js', 'skills', 'tools']),
    pins: [
      ['agents/hercules.md', '\nmode: primary\n'],
      ['agents/challenger.md', '\nmode: subagent\n'],
      ['commands/build.md', '\nagent: hercules\n'],
    ],
    antiPins: [['agents/hercules.md', '\nmodel:']],
  },
  cursor: {
    commandMarkerBanned: true,
    personaDest: 'rules/hercules-persona.mdc',
    agentDest: (s) => `agents/${s}.md`,
    commandDest: (s) => `commands/${s}.md`,
    commandFormat: 'frontmatter',
    commandKeysRequired: ['name', 'description'],
    agentKeysRequired: ['name', 'description'],
    agentKeysForbidden: ['model', 'model_tier', 'tools'],
    orchestratorPrefix: '---\nname: hercules\ndescription: ',
    neutralityPattern: CLAUDE_ISM,
    neutralityExempt: ['CAPABILITIES.md', 'hooks/'],
    planIdiomsBanned: true,
    topLevel: new Set(['.cursor-plugin', 'CAPABILITIES.md', 'README.md', 'agents', 'commands', 'hooks', 'logo.svg', 'protocols', 'rules', 'skills', 'tools']),
    pins: [
      ['agents/cynical-reviewer.md', '\nreadonly: true\n'],
      // The closing fence is in the needle: it proves `alwaysApply` is FRONTMATTER, not body prose.
      ['rules/hercules-persona.mdc', '\nalwaysApply: true\n---\n'],
      // Cursor cannot block a tool call the way a PreToolUse hook can, so the persona asks first.
      ['rules/hercules-persona.mdc', 'ask-before-applying-edits'],
      ['hooks/hooks.json', '${CURSOR_PLUGIN_ROOT}/hooks/hercules_gate.py shell'],
      // Cursor forces no subagent spawn, so design/build carry a handshake-or-HALT branch no other host has.
      ['commands/design.md', 'HALT and tell the user'],
      ['commands/build.md', 'HALT and tell the user'],
    ],
    antiPins: [['agents/backend-engineer.md', 'readonly']],
  },
  'grok-build': {
    commandMarkerBanned: false,
    personaDest: 'CLAUDE.md',
    agentDest: (s) => `agents/${s}.md`,
    commandDest: (s) => `commands/${s}.md`,
    commandFormat: 'frontmatter',
    commandKeysRequired: ['description'],
    agentKeysRequired: ['name', 'description'],
    agentKeysForbidden: ['model', 'model_tier'],
    orchestratorPrefix: '---\nname: hercules\ndescription: ',
    neutralityPattern: null,
    neutralityExempt: [],
    planIdiomsBanned: true,
    topLevel: new Set(['.grok-plugin', 'CAPABILITIES.md', 'CLAUDE.md', 'agents', 'commands', 'hooks', 'protocols', 'settings.json', 'skills', 'tools']),
    pins: [['hooks/hooks.json', '${GROK_PLUGIN_ROOT}/hooks/frozen_tests.py']],
    antiPins: [
      ['hooks/hooks.json', 'CLAUDE_PLUGIN_ROOT'],
      ['agents/hercules.md', '\nmodel:'],
    ],
  },
  'gemini-cli': {
    commandMarkerBanned: true,
    personaDest: 'GEMINI.md',
    agentDest: (s) => `agents/${s}.md`,
    commandDest: (s) => `commands/${s}.toml`,
    commandFormat: 'toml',
    commandKeysRequired: [],
    agentKeysRequired: ['name', 'description'],
    agentKeysForbidden: ['model', 'model_tier', 'tools'],
    orchestratorPrefix: '---\nname: hercules\ndescription: ',
    neutralityPattern: CLAUDE_ISM,
    neutralityExempt: ['CAPABILITIES.md', 'hooks/'],
    planIdiomsBanned: true,
    topLevel: new Set(['CAPABILITIES.md', 'GEMINI.md', 'agents', 'commands', 'gemini-extension.json', 'hooks', 'protocols', 'skills', 'tools']),
    pins: [
      ['hooks/hooks.json', '${extensionPath}/hooks/hercules_gate.py'],
      ['gemini-extension.json', '"contextFileName": "GEMINI.md"'],
      ['commands/build.toml', 'plan mode'],
    ],
    antiPins: [['agents/hercules.md', '\nmodel:']],
  },
  'copilot-cli': {
    commandMarkerBanned: true,
    personaDest: 'AGENTS.md',
    agentDest: (s) => `agents/${s}.agent.md`,
    commandDest: (s) => `commands/${s}.prompt.md`,
    commandFormat: 'frontmatter',
    commandKeysRequired: ['description'],
    agentKeysRequired: ['name', 'description'],
    agentKeysForbidden: ['model', 'model_tier', 'tools'],
    orchestratorPrefix: '---\nname: hercules\ndescription: ',
    neutralityPattern: CLAUDE_ISM,
    neutralityExempt: ['CAPABILITIES.md', 'hooks/'],
    planIdiomsBanned: true,
    topLevel: new Set(['.github', 'AGENTS.md', 'CAPABILITIES.md', 'agents', 'commands', 'hooks', 'plugin.json', 'protocols', 'skills', 'tools']),
    pins: [
      ['hooks/hooks.json', '"matcher": "create|edit|str_replace_editor|apply_patch|write|Write|Edit|MultiEdit|NotebookEdit"'],
      ['hooks/hooks.json', 'python3 \\"$PLUGIN_ROOT/hooks/hercules_gate.py\\" preToolUse || exit 0'],
      ['.github/plugin/marketplace.json', '"name": "hercules"'],
      ['commands/build.prompt.md', 'plan mode'],
    ],
    antiPins: [['agents/hercules.agent.md', '\nmodel:']],
  },
  codex: {
    commandMarkerBanned: true,
    personaDest: 'AGENTS.md',
    agentDest: (s) => `skills/hercules-advisor-${s}/SKILL.md`,
    commandDest: (s) => `skills/hercules-${s}/SKILL.md`,
    commandFormat: 'frontmatter',
    commandKeysRequired: ['name', 'description'],
    agentKeysRequired: ['name', 'description'],
    agentKeysForbidden: ['model', 'model_tier', 'tools'],
    orchestratorPrefix: '---\nname: hercules-advisor-hercules\ndescription: ',
    neutralityPattern: CLAUDE_ISM,
    neutralityExempt: ['CAPABILITIES.md', 'hooks/'],
    planIdiomsBanned: true,
    topLevel: new Set(['.codex-plugin', 'AGENTS.md', 'CAPABILITIES.md', 'hooks', 'protocols', 'skills', 'tools']),
    pins: [
      ['.codex-plugin/plugin.json', '"skills": "./skills/"'],
      ['.codex-plugin/plugin.json', '"hooks": "./hooks/hooks.json"'],
      ['hooks/hooks.json', '"matcher": "apply_patch|Bash"'],
      ['hooks/hooks.json', 'codex_pre_tool'],
      ['skills/hercules-workflow/SKILL.md', '$hercules-discover'],
    ],
    antiPins: [['skills/hercules-advisor-hercules/SKILL.md', '\nmodel:']],
  },
};
// ecosystem-tax:end

const workspace = tempWorkspace();
const RECIPES = new Map(loadAllRecipes(repoRoot).map((named) => [named.recipe.name, named]));
const built: Record<string, string> = {};

/** Every name any recipe substitutes — plus `version`, which the build supplies to every render. */
const BUILD_VARIABLES = new Set<string>(['version']);
for (const { recipe } of RECIPES.values()) Object.keys(recipe.variables).forEach((n) => BUILD_VARIABLES.add(n));

function recipeOf(target: string): { file: string; recipe: Recipe } {
  const named = RECIPES.get(target);
  if (named === undefined) throw new Error(`${target} recipe missing`);
  return named;
}

async function render(target: string, prefix: string): Promise<string> {
  const { file, recipe } = recipeOf(target);
  const out = join(workspace.make(prefix), target);
  await buildDistribution(recipe, file, out, repoRoot);
  return out;
}

beforeAll(async () => {
  // Build every registered distribution once for the whole module, to keep wall-clock time down.
  for (const target of RECIPES.keys()) built[target] = await render(target, `hercules-universal-${target}-`);
});

afterAll(workspace.cleanup);

describe('universal conformance', () => {
  it('every registered distribution declares its conformance shape (fail-closed)', () => {
    expect(new Set(RECIPES.keys())).toEqual(new Set(Object.keys(CONFORMANCE_EXPECTATIONS)));
  });

  it('some distribution ships a manifest that names the plugin', () => {
    // Guards the per-target check below: with no manifest naming itself, all seven pass vacuously.
    const naming = [...RECIPES.keys()].filter((target) => jsonDests(target)
      .some((dest) => 'name' in (JSON.parse(readFileSync(join(built[target] as string, dest), 'utf-8')) as object)));
    expect(naming.length, 'no distribution ships a manifest naming the plugin').toBeGreaterThan(0);
  });

  it('some distribution ships a version-bearing manifest', () => {
    // Guards the per-target check below: with no source asking for the version, all seven pass vacuously.
    const versioned = [...RECIPES.keys()].filter((target) => versionedDests(target).length > 0);
    expect(versioned.length, 'no distribution ships a manifest carrying the release version').toBeGreaterThan(0);
  });

  for (const target of Object.keys(CONFORMANCE_EXPECTATIONS).sort()) {
    const exp = CONFORMANCE_EXPECTATIONS[target] as Expectation;

    describe(target, () => {
      it('build is deterministic', async () => {
        const a = await render(target, `hercules-det-a-${target}-`);
        const b = await render(target, `hercules-det-b-${target}-`);
        expect(filesUnder(a)).toEqual(filesUnder(b));
        expect(findDifferences(a, b), 'two renders of one recipe differ in bytes or permissions').toEqual([]);
      });

      it('every source component lands at its declared dest', () => {
        const out = built[target] as string;
        expect(isFile(out, ...exp.personaDest.split('/'))).toBe(true);
        expect(isFile(out, 'persona.md')).toBe(false);
        for (const stem of srcStems(SRC_CONTENT, 'agents')) {
          expect(isFile(out, ...exp.agentDest(stem).split('/')), `agent ${stem} missing`).toBe(true);
        }
        for (const stem of srcStems(SRC_CONTENT, 'commands')) {
          expect(isFile(out, ...exp.commandDest(stem).split('/')), `command ${stem} missing`).toBe(true);
        }
      });

      it('the top-level tree is exactly the declared set', () => {
        expect(topLevelEntries(built[target] as string)).toEqual(exp.topLevel);
      });

      it('agents carry exactly the declared frontmatter shape', () => {
        const out = built[target] as string;
        const files = filesUnder(out);
        for (const stem of srcStems(SRC_CONTENT, 'agents')) {
          const keys = frontmatterKeys(files[exp.agentDest(stem)] as string);
          for (const key of exp.agentKeysRequired) expect(keys, `${stem} missing ${key}`).toContain(key);
          for (const key of exp.agentKeysForbidden) expect(keys, `${stem} carries forbidden ${key}`).not.toContain(key);
        }
        const herc = files[exp.agentDest('hercules')] as string;
        expect(herc.startsWith(exp.orchestratorPrefix)).toBe(true);
      });

      it('commands carry the declared frontmatter shape and drop the Claude marker (where banned)', () => {
        const out = built[target] as string;
        const files = filesUnder(out);
        for (const stem of srcStems(SRC_CONTENT, 'commands')) {
          const text = files[exp.commandDest(stem)] as string;
          if (exp.commandFormat === 'frontmatter') {
            const keys = frontmatterKeys(text);
            expect(exp.commandKeysRequired.length, `${target} declares no required command key`).toBeGreaterThan(0);
            for (const key of exp.commandKeysRequired) expect(keys, `${stem} missing ${key}`).toContain(key);
          } else {
            expect(text).toMatch(/^description = ".+"$/m);
          }
          if (exp.commandMarkerBanned) expect(text).not.toContain('disable-model-invocation');
        }
      });

      it('every command carries its plan-mode instruction', () => {
        const files = filesUnder(built[target] as string);
        for (const stem of srcStems(SRC_CONTENT, 'commands')) {
          const text = files[exp.commandDest(stem)] as string;
          expect(text.toLowerCase(), `${stem}: missing plan-mode instruction`).toContain('plan mode');
        }
      });

      it('nothing unrendered and no build variable of ours survives into the distribution', () => {
        // A surviving `{{` or `{%` is a template the engine never ran; a surviving `${name}` of ours
        // shipped raw and inert. Any other `${NAME}` is the host's, so it must be declared or prose.
        const { recipe } = recipeOf(target);
        const runtime = new Set(recipe.runtime_variables);
        for (const [relativePath, text] of Object.entries(filesUnder(built[target] as string))) {
          expect(text, `${relativePath}: unrendered Liquid output tag`).not.toContain('{{');
          expect(text, `${relativePath}: unrendered Liquid block tag`).not.toContain('{%');
          for (const name of BUILD_VARIABLES) {
            expect(text, `${relativePath}: unsubstituted build variable \${${name}}`).not.toContain(`\${${name}}`);
          }
          const allowed = PROSE_PLACEHOLDERS[relativePath] ?? [];
          for (const match of text.matchAll(/\$\{([A-Za-z][A-Za-z0-9_]*)\}/g)) {
            const name = match[1] as string;
            expect(
              runtime.has(name) || allowed.includes(name),
              `${relativePath}: \${${name}} is neither declared in ${target}'s runtime_variables nor a named prose mention`,
            ).toBe(true);
          }
        }
      });

      it('no foreign host idiom leaks', () => {
        const files = filesUnder(built[target] as string);
        for (const [relativePath, text] of Object.entries(files)) {
          const exempt = exp.neutralityExempt.some((e) => (e.endsWith('/') ? relativePath.startsWith(e) : relativePath === e));
          if (exp.neutralityPattern && !exempt) {
            expect(exp.neutralityPattern.test(text), `${relativePath}: foreign host idiom leaked`).toBe(false);
          }
          if (exp.planIdiomsBanned && relativePath.endsWith('.md') && !exempt) {
            for (const idiom of PLAN_IDIOMS) expect(text, `${relativePath}: ${idiom} leaked`).not.toContain(idiom);
          }
        }
      });

      it('every cited protocols/<file> is actually shipped', () => {
        const files = filesUnder(built[target] as string);
        const cited = new Set<string>();
        for (const text of Object.values(files)) {
          for (const m of text.matchAll(/protocols\/([A-Za-z0-9-]+\.md)/g)) cited.add(m[1] as string);
        }
        expect(cited.size).toBeGreaterThan(0);
        for (const fname of cited) expect(files[`protocols/${fname}`]).toBeDefined();
      });

      it('every shipped JSON parses, and names the plugin wherever it names itself', () => {
        // A manifest that will not parse installs as an ABSENT plugin, with no error naming it; a
        // drifted `name` installs fine under a name no marketplace entry or `/hercules:` command uses.
        const out = built[target] as string;
        const shipped = jsonDests(target);
        expect(shipped.length, `${target} ships no JSON at all — nothing was parsed`).toBeGreaterThan(0);
        for (const dest of shipped) {
          const parsed = JSON.parse(readFileSync(join(out, dest), 'utf-8')) as Record<string, unknown>;
          if ('name' in parsed) expect(parsed['name'], `${dest}: not the plugin's name`).toBe(PLUGIN);
        }
      });

      it('every versioned manifest carries the canonical version, and nothing else moved', () => {
        // "Versioned" is a fact about the SOURCE: it asks for `{{ version }}`. The version arrives as
        // an ordinary variable, so injecting it must change the manifest in exactly one place.
        const out = built[target] as string;
        const { recipe } = recipeOf(target);
        const canonical = readCanonicalVersion(repoRoot);
        for (const dest of versionedDests(target)) {
          const shipped = JSON.parse(readFileSync(join(out, dest), 'utf-8')) as Record<string, unknown>;
          expect(shipped['version'], `${dest}: not the canonical version`).toBe(canonical);
          const sources = (recipe.targets[dest] as { sources: readonly string[] }).sources;
          expect(sources, `${dest}: a manifest is one source, joined with nothing`).toHaveLength(1);
          const source = readFileSync(join(repoRoot, sources[0] as string), 'utf-8');
          expect(source, `${dest}: must carry the variable, not a literal version`).toContain('"version": "{{ version }}"');
          expect(shipped, `${dest}: injecting the version changed something else`).toEqual(
            JSON.parse(source.replaceAll('{{ version }}', canonical)),
          );
        }
      });

      it('declared pins hold and anti-pins stay absent', () => {
        const files = filesUnder(built[target] as string);
        for (const [relativePath, needle] of exp.pins) {
          expect(files[relativePath], `${relativePath}: expected pin ${needle}`).toContain(needle);
        }
        for (const [relativePath, needle] of exp.antiPins) {
          expect(files[relativePath], `${relativePath}: forbidden content ${needle}`).not.toContain(needle);
        }
      });

      it('shipped guard modules are byte-identical to the shared source', () => {
        // The Python guards are the one thing every host runs as code, from shared source: a
        // distribution rendering its own variant would be a gate behaving differently per tool.
        const out = built[target] as string;
        const { recipe } = recipeOf(target);
        const guards = Object.entries(recipe.targets)
          .filter(([dest, entry]) => entry !== null && dest.startsWith('hooks/') && dest.endsWith('.py'));
        expect(guards.length, `${target} ships no guard module`).toBeGreaterThan(0);
        for (const [dest, entry] of guards) {
          const sources = (entry as { sources: readonly string[] }).sources;
          expect(sources, `${dest}: a guard is one shared file, joined with nothing`).toHaveLength(1);
          expect(sources[0], `${dest}: not taken from the shared guard source`)
            .toBe(`src/scripts/hooks/${dest.slice('hooks/'.length)}`);
          expect(readFileSync(join(out, dest))).toEqual(readFileSync(join(repoRoot, sources[0] as string)));
        }
      });

      it('the shipped gate config is the declared gate verbatim', () => {
        // The one emitted file the build parses and validates: the gate adapter reads these keys to
        // decide whether a host's write may be refused, so nothing may render into or out of it.
        const out = built[target] as string;
        const { recipe } = recipeOf(target);
        const entry = recipe.targets['hooks/write_gate.json'];
        if (entry === undefined || entry === null) {
          expect(isFile(out, 'hooks', 'write_gate.json'), `${target} ships a gate it never declared`).toBe(false);
          return;
        }
        const declared = entry.sources.map((source) => JSON.parse(readFileSync(join(repoRoot, source), 'utf-8')));
        expect(declared).toHaveLength(1);
        expect(JSON.parse(readFileSync(join(out, 'hooks', 'write_gate.json'), 'utf-8'))).toEqual(declared[0]);
      });
    });
  }
});

interface Descriptor {
  name?: string;
  owner?: { name?: string };
  interface?: { displayName?: string };
  plugins?: ReadonlyArray<{ name?: string; description?: string; source?: string | { source?: string; path?: string } }>;
}

/** The tracked root `marketplace.json` files — not `src/` input, not `dist/` output — read from git, so an eighth ecosystem needs only the file. */
function rootDescriptors(): string[] {
  return execFileSync('git', ['ls-files', '*marketplace.json'], { cwd: repoRoot, encoding: 'utf-8' })
    .split('\n')
    .filter((relativePath) => relativePath.length > 0 && !relativePath.startsWith('dist/') && !relativePath.startsWith('src/'));
}

/** Where a listing points: most hosts spell it as a path, Codex as a `{ source, path }` object. */
function sourcePath(entry: { source?: string | { path?: string } }): string {
  return typeof entry.source === 'string' ? entry.source : entry.source?.path ?? '';
}

describe('every marketplace descriptor publishes a distribution we build', () => {
  // A descriptor is read before anything is installed, so a source pointing at a missing tree fails
  // on the user's machine as a bare "not found". validatePackage's glob misses Codex's and Copilot's.
  const descriptors = rootDescriptors();
  const distributions = new Set(listRecipeNames());

  it('there are descriptors and distributions to check', () => {
    // Guards the guard: a `git ls-files` matching nothing makes every case below vacuous.
    expect(descriptors.length, 'no tracked marketplace descriptor outside dist/').toBeGreaterThan(1);
    expect(distributions.size, 'no distributions were found').toBeGreaterThan(0);
  });

  for (const relativePath of descriptors) {
    it(`${relativePath} points at a distribution that is really published`, () => {
      const mk = JSON.parse(readFileSync(join(repoRoot, relativePath), 'utf-8')) as Descriptor;
      expect(mk.name, `${relativePath}: the marketplace needs a name`).toBeTruthy();
      // Codex carries the publisher under `interface.displayName`, where the others use `owner`.
      expect(mk.owner?.name ?? mk.interface?.displayName, `${relativePath}: names no publisher`).toBeTruthy();

      const entry = (mk.plugins ?? []).find((plugin) => plugin.name === PLUGIN);
      expect(entry, `${relativePath}: lists no plugin named ${PLUGIN}`).toBeDefined();
      const listing = entry as NonNullable<typeof entry>;

      // A path into this checkout is only meaningful as a `local` source; any other kind sends the
      // host elsewhere entirely while the path still looks right.
      if (typeof listing.source === 'object' && listing.source !== null) {
        expect(listing.source.source, `${relativePath}: a path in this checkout is a 'local' source`).toBe('local');
      }
      const source = sourcePath(listing);
      const target = source.replace(/^\.\//, '').replace(/^dist\//, '');
      expect(distributions.has(target), `${relativePath}: source '${source}' names no distribution we build`).toBe(true);
      // A manifest the host reads at install time, missing from the published tree, is fatal here.
      for (const dest of jsonDests(target)) {
        expect(isFile(repoRoot, 'dist', target, ...dest.split('/')), `${relativePath}: ${source}/${dest} is not published`).toBe(true);
      }
      // The sentence a user reads before installing is the one the plugin ships, not a drifted copy.
      const describing = jsonDests(target)
        .map((dest) => JSON.parse(readFileSync(join(repoRoot, 'dist', target, dest), 'utf-8')) as Record<string, unknown>)
        .filter((manifest) => manifest['name'] === PLUGIN && typeof manifest['description'] === 'string');
      expect(describing.length, `${relativePath}: ${target} ships no manifest describing the plugin`).toBeGreaterThan(0);
      for (const manifest of describing) {
        expect(listing.description, `${relativePath}: the listing describes ${PLUGIN} differently from ${target} itself`)
          .toBe(manifest['description']);
      }
    });
  }
});

/** The JSON destinations `target` declares — every manifest, config and hook file it ships. */
function jsonDests(target: string): string[] {
  const { recipe } = recipeOf(target);
  return Object.entries(recipe.targets)
    .filter(([dest, entry]) => entry !== null && dest.endsWith('.json'))
    .map(([dest]) => dest)
    .sort();
}

/** The destinations of `target` whose sources ask for `{{ version }}` — its versioned manifests. */
function versionedDests(target: string): string[] {
  const { recipe } = recipeOf(target);
  return Object.entries(recipe.targets)
    .filter(([, entry]) => entry !== null
      && entry.sources.some((source) => readFileSync(join(repoRoot, source), 'utf-8').includes('{{ version }}')))
    .map(([dest]) => dest)
    .sort();
}
