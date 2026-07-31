import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { filesUnder, isFile } from '../../../commons/support/buildTree';
import { repoRoot } from '../../../commons/support/repo';
import {
  ALL_COMMANDS,
  BUILD,
  DESIGN,
  DISCOVER,
  PROJECT_RESET,
  SHIP,
  WORKFLOW,
  readFile,
  readPersona,
  section,
} from './support';

// Machine-local settings schema, spec-lifecycle wording, wizard invocation, bundled-path
// resolution, and the CLAUDE.md<->commands state-field sync guard.

describe('machine-local settings and spec-lifecycle contracts', () => {
  it('no doc mentions the removed local context file', () => {
    const targets = [
      ...ALL_COMMANDS,
      'dist/claude-code/CLAUDE.md',
      'dist/claude-code/skills/write-test-scenarios/SKILL.md',
      'README.md',
    ];
    for (const path of targets) {
      const text = readFile(path);
      expect(text).not.toContain('docs/.context');
      expect(text.toLowerCase()).not.toContain('gitignored, never committed');
    }
  });

  it('the machine-local settings layout is fully documented', () => {
    const md = readPersona();
    expect(md).toContain('config.json');
    expect(md.includes('state/') || md.includes('state_file')).toBe(true);
    expect(md).toContain('projects');
    expect(md).toContain('directory');
    expect(md).toContain('repositories');
    expect(md).toContain('frozen_override');
    expect(md).toContain('frozen_hook');
    expect((md.match(/\/\/ Example — illustrative values/g) ?? []).length).toBeGreaterThanOrEqual(2);
    expect(md).toContain('real state omits fields that');
  });

  it('the fixed project rules are written down in one place', () => {
    const md = readPersona();
    expect(md).toContain('Development principles');
    expect(md.toLowerCase()).toContain('hercules');
    expect(md).toContain('business-requirements');
    expect(md.toLowerCase().includes('temporary') || md.toLowerCase().includes('deleted')).toBe(true);
  });

  it('every phase value that can arm or disarm a safety hook is documented', () => {
    const md = readPersona();
    const prose = md.slice(md.indexOf('Session object (in the state file):'));
    expect(prose).toContain('`current_phase`');
    for (const v of ['"discover"', '"design"', '"build"', '"shipped"']) {
      expect(prose).toContain(v);
    }
  });

  it('the option to keep specs instead of deleting them is documented', () => {
    const md = readPersona();
    expect(md).toContain('keep_specs');
    const principles = md.slice(md.indexOf('## Development principles'), md.indexOf('## Persona'));
    expect(principles.toLowerCase()).toContain('keep');
    expect(principles.toLowerCase()).toContain('code-of-conduct');
  });

  it('a kept spec does not carry a contradictory delete instruction', () => {
    const md = readFile(DESIGN);
    let note = md.slice(md.indexOf('## Deletion note'));
    note = note.slice(0, note.indexOf('```'));
    expect(note).toContain('git rm');
    expect(note).toContain('code-of-conduct');
  });

  it('the spec template has a known-violations section', () => {
    const md = readFile(DESIGN);
    const templateStart = md.indexOf('## Acceptance criteria');
    const templateEnd = md.indexOf('```', templateStart + '## Acceptance criteria'.length);
    const template = md.slice(templateStart, templateEnd);
    expect(template).toContain('## Known violations');
    expect(template.toLowerCase().includes('architecture') || template.toLowerCase().includes('dependency')).toBe(
      true,
    );
  });

  it('the close-out rule accounts for specs that are kept, not deleted', () => {
    const md = readPersona();
    const principles = md.slice(md.indexOf('## Development principles'), md.indexOf('## Persona'));
    const p8 = principles.split('\n').find((line) => line.startsWith('8.'));
    expect(p8).toContain('retired');
  });

  it('wizard commands can only be started by explicit invocation', () => {
    for (const rel of [DISCOVER, DESIGN, BUILD, SHIP, WORKFLOW, PROJECT_RESET]) {
      const md = readFile(rel);
      expect(md.startsWith('---\n')).toBe(true);
      const head = md.slice(0, md.indexOf('\n---', 3));
      expect(head).toContain('description:');
      expect(head).toContain('disable-model-invocation: true');
    }
  });

  it('commands find bundled reference files without a fragile path', () => {
    for (const rel of ALL_COMMANDS) {
      expect(readFile(rel)).toContain("this plugin's directory");
    }
  });

  it('bundled files are referenced with the documented path placeholder', () => {
    const files = filesUnder(join(repoRoot, 'dist', 'claude-code'));
    const mdFiles = Object.entries(files).filter(
      ([rel]) =>
        /^commands\/[^/]+\.md$/.test(rel) || /^agents\/[^/]+\.md$/.test(rel) || /^skills\/[^/]+\/SKILL\.md$/.test(rel),
    );
    let sawPluginRoot = false;
    for (const [, text] of mdFiles) {
      expect(text).not.toContain('${CLAUDE_SKILL_DIR}');
      if (text.includes('${CLAUDE_PLUGIN_ROOT}')) sawPluginRoot = true;
    }
    expect(sawPluginRoot).toBe(true);
  });

  it('every file path a command tells the agent to read actually exists', () => {
    const plugin = join(repoRoot, 'dist', 'claude-code');
    const mustExist = [
      'CLAUDE.md',
      '.claude-plugin/plugin.json',
      'protocols/a2a-communication-protocol.md',
      'protocols/workflow-protocol.md',
      'commands/discover.md',
      'commands/design.md',
      'commands/build.md',
      'commands/ship.md',
      'commands/workflow.md',
      'commands/project-reset.md',
    ];
    for (const rel of mustExist) {
      expect(isFile(plugin, rel), `cited plugin path missing: plugin/${rel}`).toBe(true);
    }
  });
});

/**
 * (documented set, referenced set, commands text) for the CLAUDE.md<->commands schema guard.
 * snake_case only — a loose pattern drags in backticked value literals (`false`); the two
 * single-word fields (tier, cadence) are named explicitly so they stay guarded.
 */
function documentedAndReferencedStateFields(): { documented: Set<string>; referenced: Set<string>; commands: string } {
  const md = readPersona();
  const prose =
    section(md, 'Session object (in the state file):', '\n\n') + section(md, 'Registry entry:', '\n\n');
  const fieldRe = /`([a-z]+(?:_[a-z]+)+)`/g;
  const documented = new Set([...prose.matchAll(fieldRe)].map((m) => m[1] as string));
  for (const f of ['tier', 'cadence']) if (prose.includes(`\`${f}\``)) documented.add(f);
  const commands = ALL_COMMANDS.map((f) => readFile(f)).join('');
  const referenced = new Set([...commands.matchAll(fieldRe)].map((m) => m[1] as string));
  return { documented, referenced, commands };
}

describe('CLAUDE.md <-> commands state-field sync', () => {
  it('a documented state field that no command ever uses is flagged', () => {
    const { documented, commands } = documentedAndReferencedStateFields();
    const orphanDocs = [...documented].filter((f) => !commands.includes(`\`${f}\``));
    expect(orphanDocs).toEqual([]);
  });

  it('a state field a command invents without documenting it is flagged', () => {
    const { documented, referenced } = documentedAndReferencedStateFields();
    const allowedFileLevel = new Set(['active_session', 'schema_version']);
    const undocumented = [...referenced].filter((f) => !documented.has(f) && !allowedFileLevel.has(f));
    expect(undocumented).toEqual([]);
  });
});
