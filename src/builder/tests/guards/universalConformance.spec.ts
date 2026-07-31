import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { discover } from '../../descriptor.mjs';
import { readCanonicalVersion } from '../../versionTargets.mjs';
import { buildTarget, targets } from '../../bin/cli.mjs';
import { filesUnder, frontmatterKeys, isFile, srcStems, topLevelEntries } from '../../../commons/support/buildTree';
import { ECOSYSTEMS } from '../../../commons/support/descriptorFixtures';
import { repoRoot } from '../../../commons/support/repo';

// The universal conformance suite: every test runs over all registered targets against CONFORMANCE_EXPECTATIONS,
// a hand-authored, fail-closed table of flat literals. It is never derived from the descriptors, so a wrong
// descriptor edit fails HERE instead of updating the expectation in the same keystroke.

const SRC_CONTENT = join(repoRoot, 'src', 'content');
const HERCULES_TOKENS = [
  '${product}', '${host}', '${ns}', '${instructions_file}', '${agent_ns}',
  '${plan_enter}', '${plan_exit}', '${version}',
];
const CLAUDE_ISM = /CLAUDE\.md|E(?:nter|xit)PlanMode|\bClaude\b/;
const PLAN_IDIOMS = ['(`auto`)', 'EnterPlanMode', 'ExitPlanMode'];

interface Expectation {
  commandMarkerBanned: boolean;
  personaDest: string;
  agentDest: (stem: string) => string;
  commandDest: (stem: string) => string;
  commandFormat: 'frontmatter' | 'toml';
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

const CONFORMANCE_EXPECTATIONS: Record<string, Expectation> = {
  'claude-code': {
    commandMarkerBanned: false,
    personaDest: 'CLAUDE.md',
    agentDest: (s) => `agents/${s}.md`,
    commandDest: (s) => `commands/${s}.md`,
    commandFormat: 'frontmatter',
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
    agentKeysRequired: ['name', 'description', 'mode'],
    agentKeysForbidden: ['model', 'model_tier', 'tools'],
    orchestratorPrefix: '---\nname: hercules\ndescription: ',
    neutralityPattern: CLAUDE_ISM,
    neutralityExempt: ['plugin.js', 'CAPABILITIES.md', 'hooks/'],
    planIdiomsBanned: true,
    topLevel: new Set(['CAPABILITIES.md', 'agents', 'commands', 'hooks', 'instructions.md', 'opencode.json', 'plugin.js', 'protocols', 'skills', 'tools']),
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
    agentKeysRequired: ['name', 'description'],
    agentKeysForbidden: ['model', 'model_tier', 'tools'],
    orchestratorPrefix: '---\nname: hercules\ndescription: ',
    neutralityPattern: CLAUDE_ISM,
    neutralityExempt: ['CAPABILITIES.md', 'hooks/'],
    planIdiomsBanned: true,
    topLevel: new Set(['.cursor-plugin', 'CAPABILITIES.md', 'README.md', 'agents', 'commands', 'hooks', 'logo.svg', 'protocols', 'rules', 'skills', 'tools']),
    pins: [
      ['agents/cynical-reviewer.md', '\nreadonly: true\n'],
      ['rules/hercules-persona.mdc', 'alwaysApply: true'],
      // Cursor-specific: the persona's own write-gate note (Cursor cannot block a tool call the way
      // Claude Code's PreToolUse hook can, so the persona tells the model to ask first instead).
      ['rules/hercules-persona.mdc', 'ask-before-applying-edits'],
      ['hooks/hooks.json', '${CURSOR_PLUGIN_ROOT}/hooks/hercules_gate.py shell'],
      // Cursor-specific: it exposes no orchestrator-forced subagent spawn, so design/build carry a
      // handshake-or-HALT branch no other host renders.
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
};

const dirs: string[] = [];
const built: Record<string, string> = {};

beforeAll(() => {
  // Build every registered target once for the whole module, to keep wall-clock time down.
  for (const target of targets()) {
    const root = mkdtempSync(join(tmpdir(), `hercules-universal-${target}-`));
    dirs.push(root);
    const out = join(root, target);
    buildTarget(target, out);
    built[target] = out;
  }
});

afterAll(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('universal conformance', () => {
  it('every registered target declares its conformance shape (fail-closed)', () => {
    expect(new Set(targets())).toEqual(new Set(Object.keys(CONFORMANCE_EXPECTATIONS)));
  });

  for (const target of Object.keys(CONFORMANCE_EXPECTATIONS).sort()) {
    const exp = CONFORMANCE_EXPECTATIONS[target] as Expectation;

    describe(target, () => {
      it('build is deterministic', () => {
        const a = mkdtempSync(join(tmpdir(), `hercules-det-a-${target}-`));
        const b = mkdtempSync(join(tmpdir(), `hercules-det-b-${target}-`));
        dirs.push(a, b);
        buildTarget(target, join(a, target));
        buildTarget(target, join(b, target));
        expect(filesUnder(join(a, target))).toEqual(filesUnder(join(b, target)));
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

      it('commands drop the Claude marker (where banned) and keep a description', () => {
        const out = built[target] as string;
        const files = filesUnder(out);
        for (const stem of srcStems(SRC_CONTENT, 'commands')) {
          const text = files[exp.commandDest(stem)] as string;
          if (exp.commandFormat === 'frontmatter') {
            expect(frontmatterKeys(text)).toContain('description');
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

      it('no Hercules token or unresolved switch survives rendering', () => {
        const files = filesUnder(built[target] as string);
        for (const [rel, text] of Object.entries(files)) {
          expect(text, `${rel}: unrendered switch`).not.toContain('${target:');
          if (rel.startsWith('hooks/')) continue;
          for (const token of HERCULES_TOKENS) expect(text, `${rel}: unrendered ${token}`).not.toContain(token);
        }
      });

      it('no foreign host idiom leaks', () => {
        const files = filesUnder(built[target] as string);
        for (const [rel, text] of Object.entries(files)) {
          const exempt = exp.neutralityExempt.some((e) => (e.endsWith('/') ? rel.startsWith(e) : rel === e));
          if (exp.neutralityPattern && !exempt) {
            expect(exp.neutralityPattern.test(text), `${rel}: foreign host idiom leaked`).toBe(false);
          }
          if (exp.planIdiomsBanned && rel.endsWith('.md') && !exempt) {
            for (const idiom of PLAN_IDIOMS) expect(text, `${rel}: ${idiom} leaked`).not.toContain(idiom);
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

      it('every versioned manifest carries the canonical version, no ${version} token anywhere', () => {
        const out = built[target] as string;
        const canonical = readCanonicalVersion(repoRoot);
        const desc = discover(ECOSYSTEMS)[target];
        if (desc === undefined) throw new Error(`${target} descriptor missing`);
        for (const artifact of desc.artifacts) {
          if (!artifact.versioned) continue;
          const shipped = JSON.parse(readFileSync(join(out, artifact.dest), 'utf-8')) as Record<string, unknown>;
          expect(shipped['version']).toBe(canonical);
        }
        for (const [rel, text] of Object.entries(filesUnder(out))) {
          expect(text, `${rel}: unresolved version token`).not.toContain('${version}');
        }
      });

      it('declared pins hold and anti-pins stay absent', () => {
        const files = filesUnder(built[target] as string);
        for (const [rel, needle] of exp.pins) {
          expect(files[rel], `${rel}: expected pin ${needle}`).toContain(needle);
        }
        for (const [rel, needle] of exp.antiPins) {
          expect(files[rel], `${rel}: forbidden content ${needle}`).not.toContain(needle);
        }
      });

      it('shipped guard modules are byte-identical to the shared source', () => {
        const out = built[target] as string;
        const desc = discover(ECOSYSTEMS)[target];
        if (desc === undefined) throw new Error(`${target} descriptor missing`);
        expect(desc.guard.length).toBeGreaterThan(0);
        const shared = join(repoRoot, 'src', 'hooks');
        for (const name of desc.guard) {
          expect(readFileSync(join(out, 'hooks', name))).toEqual(readFileSync(join(shared, name)));
        }
      });

      it('the shipped gate config is the descriptor gate verbatim', () => {
        const out = built[target] as string;
        const desc = discover(ECOSYSTEMS)[target];
        if (desc === undefined) throw new Error(`${target} descriptor missing`);
        const shippedPath = join(out, 'hooks', 'gate.json');
        if (desc.gate === null) {
          expect(isFile(shippedPath)).toBe(false);
          return;
        }
        expect(JSON.parse(readFileSync(shippedPath, 'utf-8'))).toEqual(desc.gate);
      });
    });
  }
});
