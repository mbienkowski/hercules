import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { discover, parseDescriptor } from '../../descriptor.mjs';
import {
  computeFields, dest, DescriptorSerializer, SerializeError, tomlBasic, tomlCommand, tomlMultiline,
} from '../../genSerialize.mjs';
import { ECOSYSTEMS } from '../../../commons/support/descriptorFixtures';
import { repoRoot } from '../../../commons/support/repo';

// Exact-output pins for every mode, field generator, dispatcher, and route kind, ported 1:1 from
// tests/build/test_generic_serialize.py — carrying the same mutation-killing power onto the TS
// engine. Specs come from the SHIPPED descriptors (so the pins also freeze the real ecosystems'
// data) plus a synthetic descriptor for a branch no shipped ecosystem exercises.

const DESCRIPTORS = discover(ECOSYSTEMS);

const AGENT_SRC = '---\nname: backend-engineer\ndescription: Implements \${product} backends\n' +
  'model_tier: high\ntools: Read, Edit\n---\n\nDo the work for \${product}.\n';

const COMMAND_SRC = '---\ndescription: Build the thing\ndisable-model-invocation: true\n---\n\n' +
  'Run the build on \${product}.\n';

function tokens(entries: Record<string, string>): Map<string, string> {
  return new Map(Object.entries(entries));
}

function meta(entries: Record<string, string>): Map<string, string> {
  return new Map(Object.entries(entries));
}

function ser(name: string): DescriptorSerializer {
  return new DescriptorSerializer(DESCRIPTORS[name] as NonNullable<(typeof DESCRIPTORS)[string]>);
}

describe('preserve mode', () => {
  it('swaps model_tier in-slot for the resolved model', () => {
    // claude-code: model_tier becomes model: in the SAME slot; every other key and the key order
    // survive; body tokens render.
    const out = ser('claude-code').serializeFile(AGENT_SRC, tokens({ product: 'Claude Code' }), null, 'agents/backend-engineer.md');
    expect(out).toBe(
      '---\nname: backend-engineer\ndescription: Implements ${product} backends\n' +
        'model: opus\ntools: Read, Edit\n---\n\nDo the work for Claude Code.\n',
    );
  });

  it('drops the model line entirely on a null tier', () => {
    // grok-build maps every tier to null — the model_tier line vanishes with no residue.
    const out = ser('grok-build').serializeFile(AGENT_SRC, tokens({ product: 'Grok Build' }), null, 'agents/backend-engineer.md');
    expect(out).toBe(
      '---\nname: backend-engineer\ndescription: Implements ${product} backends\n' +
        'tools: Read, Edit\n---\n\nDo the work for Grok Build.\n',
    );
  });

  it('passes raw frontmatter through when there is no model_tier', () => {
    // A command's frontmatter has no model_tier — raw bytes, never re-rendered, never joined with
    // an extra blank line (the block ends ---\n and the body starts \n).
    const out = ser('claude-code').serializeFile(COMMAND_SRC, tokens({ product: 'Claude Code' }), null, 'commands/build.md');
    expect(out).toBe(
      '---\ndescription: Build the thing\ndisable-model-invocation: true\n---\n\n' +
        'Run the build on Claude Code.\n',
    );
  });

  it('never token-renders frontmatter values', () => {
    // The claude description ships RAW (${product} intact) — only the body renders.
    const out = ser('claude-code').serializeFile(AGENT_SRC, tokens({ product: 'Claude Code' }), null, 'agents/x.md');
    expect(out).toContain('description: Implements ${product} backends');
  });

  it('fails loud when a required field is missing', () => {
    const src = '---\ndescription: An agent with no name\nmodel_tier: high\ntools: Read\n---\n\nBody.\n';
    expect(() => ser('claude-code').serializeFile(src, tokens({}), null, 'agents/anon.md')).toThrow(SerializeError);
    expect(() => ser('claude-code').serializeFile(src, tokens({}), null, 'agents/anon.md')).toThrow(/"name"/);
  });
});

describe('fields mode', () => {
  it('rebuilds frontmatter and renders flagged values', () => {
    // opencode agent: name raw, description token-rendered, mode computed; the join is
    // fm + blank line + body (the body's own leading newline preserved — two blank lines total).
    const out = ser('opencode').serializeFile(AGENT_SRC, tokens({ product: 'OpenCode' }));
    expect(out).toBe(
      '---\nname: backend-engineer\ndescription: Implements OpenCode backends\n' +
        'mode: subagent\n---\n\n\nDo the work for OpenCode.\n',
    );
  });

  it('marks the primary agent via the primary_mode generator', () => {
    const src = AGENT_SRC.replace('backend-engineer', 'hercules');
    const out = ser('opencode').serializeFile(src, tokens({ product: 'OpenCode' }));
    expect(out).toContain('\nmode: primary\n');
  });

  it("the lstrip_newlines body policy removes only leading newlines", () => {
    // opencode command: the body's leading blank lines go, the trailing newline stays.
    const out = ser('opencode').serializeFile(COMMAND_SRC, tokens({ product: 'OpenCode' }));
    expect(out).toBe(
      '---\ndescription: Build the thing\nagent: hercules\n---\n\n' +
        'Run the build on OpenCode.\n',
    );
  });

  it('flag_if_name_in emits its value only for the named roles', () => {
    const s = ser('cursor');
    const locked = s.serializeFile(
      AGENT_SRC.replace('backend-engineer', 'cynical-reviewer'), tokens({ product: 'Cursor' }),
      null, 'agents/cynical-reviewer.md',
    );
    const open = s.serializeFile(AGENT_SRC, tokens({ product: 'Cursor' }), null, 'agents/backend-engineer.md');
    expect(locked).toContain('\nreadonly: true\n');
    expect(open).not.toContain('readonly');
  });

  it("the stem generator names a cursor command from its source rel", () => {
    const out = ser('cursor').serializeFile(COMMAND_SRC, tokens({ product: 'Cursor' }), null, 'commands/build.md');
    expect(out.startsWith('---\nname: build\ndescription: Build the thing\n---\n\n')).toBe(true);
  });

  it('fails loud when the stem generator has no source stem', () => {
    expect(() => ser('cursor').serializeCommand(meta({ description: 'x' }), 'Body.', tokens({})))
      .toThrow(/stem/);
  });
});

describe('wrap and plain modes', () => {
  it('wraps the persona as an always-applied rule', () => {
    const out = ser('cursor').serializeFile('Persona for ${product}.\n', tokens({ product: 'Cursor' }), null, 'persona.md');
    expect(out).toBe(
      '---\ndescription: Hercules — the spec-first delivery methodology ' +
        '(Discover → Design → Build → Ship). Always-on persona and project instructions.\n' +
        'alwaysApply: true\n---\n\nPersona for Cursor.\n',
    );
  });

  it('renders the whole text verbatim in plain mode', () => {
    const out = ser('gemini-cli').serializeFile('\nPersona for ${product}.\n\n', tokens({ product: 'Gemini CLI' }), null, 'persona.md');
    expect(out).toBe('\nPersona for Gemini CLI.\n\n');
  });
});

describe('toml_command mode', () => {
  it('emits the exact gemini layout', () => {
    const out = ser('gemini-cli').serializeFile(COMMAND_SRC, tokens({ product: 'Gemini CLI' }), null, 'commands/build.md');
    expect(out).toBe('description = "Build the thing"\n\nprompt = """\nRun the build on Gemini CLI.\n"""\n');
  });

  it('handles backslashes and triple-quote runs in the escapers', () => {
    // Direct pins for the escapers (mutation-gated): basic escapes backslash then quote;
    // multiline doubles backslashes and breaks a 3-quote run by escaping exactly its third quote.
    expect(tomlBasic('a"b\\c')).toBe('"a\\"b\\\\c"');
    expect(tomlMultiline('plain')).toBe('plain');
    expect(tomlMultiline('a\\b')).toBe('a\\\\b');
    expect(tomlMultiline('a""b')).toBe('a""b');
    expect(tomlMultiline('x"""y')).toBe('x""\\"y');
    expect(tomlMultiline('""""')).toBe('""\\""');
  });

  it('escapes both slots of the toml_command helper', () => {
    const out = tomlCommand('He said "go"', 'a\\b');
    expect(out).toBe('description = "He said \\"go\\""\n\nprompt = """\na\\\\b\n"""\n');
  });
});

describe('dispatch and routing', () => {
  it('passes frontmatterless files through every non-persona role', () => {
    // A protocol (fm-less, default role) renders verbatim on a fields-mode ecosystem too.
    const out = ser('copilot-cli').serializeFile('A protocol for ${product}.\n', tokens({ product: 'GitHub Copilot CLI' }), null, 'protocols/a2a.md');
    expect(out).toBe('A protocol for GitHub Copilot CLI.\n');
  });

  it('the exact route relocates and identity falls through', () => {
    const d = DESCRIPTORS['gemini-cli'] as NonNullable<(typeof DESCRIPTORS)['gemini-cli']>;
    expect(dest(d, 'persona.md')).toBe('GEMINI.md');
    expect(dest(d, 'protocols/a2a.md')).toBe('protocols/a2a.md');
  });

  it('suffix_swap requires both a matching prefix and suffix', () => {
    const d = DESCRIPTORS['gemini-cli'] as NonNullable<(typeof DESCRIPTORS)['gemini-cli']>;
    expect(dest(d, 'commands/build.md')).toBe('commands/build.toml');
    expect(dest(d, 'protocols/x.md')).toBe('protocols/x.md'); // prefix mismatch
    expect(dest(d, 'commands/notes.txt')).toBe('commands/notes.txt'); // suffix mismatch
  });

  it('copilot routes swap agent and prompt extensions', () => {
    const d = DESCRIPTORS['copilot-cli'] as NonNullable<(typeof DESCRIPTORS)['copilot-cli']>;
    expect(dest(d, 'agents/maintainer.md')).toBe('agents/maintainer.agent.md');
    expect(dest(d, 'commands/ship.md')).toBe('commands/ship.prompt.md');
    expect(dest(d, 'persona.md')).toBe('AGENTS.md');
  });

  it('cursor relocates only the persona — every other component keeps its source path', () => {
    // Ported from tests/build/test_cursor_serialize.py's test_cursor_dest_relocates_only_the_persona:
    // pinned against the REAL cursor descriptor's routes, since Cursor's agents/commands/skills
    // dirs match content exactly and only persona.md's .md -> .mdc + relocation is special.
    const d = DESCRIPTORS['cursor'] as NonNullable<(typeof DESCRIPTORS)['cursor']>;
    expect(dest(d, 'persona.md')).toBe('rules/hercules-persona.mdc');
    expect(dest(d, 'agents/cynical-reviewer.md')).toBe('agents/cynical-reviewer.md');
    expect(dest(d, 'commands/workflow.md')).toBe('commands/workflow.md');
    expect(dest(d, 'skills/hercules-reference/SKILL.md')).toBe('skills/hercules-reference/SKILL.md');
    expect(dest(d, 'protocols/workflow-protocol.md')).toBe('protocols/workflow-protocol.md');
  });
});

describe('cursor: the readonly field is exactly the gate-verdict roles (descriptor-level pin)', () => {
  it('pins the exact read-locked membership, not just that members get readonly:true', () => {
    // Ported from test_cursor_serialize.py's test_readonly_set_is_exactly_the_gate_verdict_roles.
    // The set is descriptor DATA now; this pin is the reader-end guard on that data — a wrong
    // membership (a verdict-giver dropped, or a name typo'd) must not ship silently.
    const cursor = DESCRIPTORS['cursor'] as NonNullable<(typeof DESCRIPTORS)['cursor']>;
    const fields = cursor.roles['agent']?.fields ?? [];
    const readonlyField = fields.find((f) => f.key === 'readonly');
    if (readonlyField === undefined) throw new Error('cursor agent role has no readonly field');
    expect(new Set(readonlyField.names)).toEqual(new Set([
      'cynical-reviewer', 'security-expert', 'source-checker', 'senior-qa-engineer', 'maintainer',
    ]));
    expect(readonlyField.value).toBe('true');
  });
});

describe('role-direct sugar', () => {
  it('serializeAgent matches the file-path output', () => {
    const s = ser('claude-code');
    const m = meta({
      name: 'backend-engineer', description: 'Implements ${product} backends',
      model_tier: 'high', tools: 'Read, Edit',
    });
    const out = s.serializeAgent(m, 'Do the work for ${product}.', tokens({ product: 'Claude Code' }));
    expect(out).toBe(
      '---\nname: backend-engineer\ndescription: Implements ${product} backends\n' +
        'model: opus\ntools: Read, Edit\n---\n\nDo the work for Claude Code.',
    );
  });

  it('serializeCommand takes an explicit stem', () => {
    const out = ser('cursor').serializeCommand(meta({ description: 'Build the thing' }), '\nBody.\n', tokens({}), 'build');
    expect(out).toBe('---\nname: build\ndescription: Build the thing\n---\n\nBody.\n');
  });

  it('cursor serializeAgent drops model and tools — a subagent carries only name+description', () => {
    // Ported from test_cursor_serialize.py's test_agent_frontmatter_drops_model_and_tools: the
    // Claude model_tier and tools are dropped (Cursor subagents inherit the user's model).
    const s = ser('cursor');
    const m = meta({
      name: 'backend-engineer', description: 'Implements server code.',
      model_tier: 'high', tools: 'Read, Write',
    });
    const out = s.serializeAgent(m, 'Body here.', tokens({}));
    expect(out).toBe('---\nname: backend-engineer\ndescription: Implements server code.\n---\n\nBody here.');
  });

  it('cursor serializeAgent read-locks a reviewer role with an exact field order', () => {
    // Ported from test_cursor_serialize.py's test_reviewer_agent_is_read_locked: review/audit
    // roles ship readonly:true so an isolated reviewer can never become an author.
    const s = ser('cursor');
    const m = meta({ name: 'cynical-reviewer', description: 'Finds problems.', model_tier: 'high' });
    const out = s.serializeAgent(m, 'Body.', tokens({}));
    expect(out.startsWith('---\nname: cynical-reviewer\ndescription: Finds problems.\nreadonly: true\n---')).toBe(true);
    expect(out).toContain('readonly: true');
  });

  it('cursor serializeCommand drops the disable-model-invocation marker', () => {
    // Ported from test_cursor_serialize.py's test_command_gets_stem_name_and_drops_claude_marker:
    // commands need name (the file stem) + description for the official validator; Claude's
    // disable-model-invocation marker must not leak through.
    const s = ser('cursor');
    const m = meta({ description: 'Guided delivery.', 'disable-model-invocation': 'true' });
    const out = s.serializeCommand(m, 'Do the thing.', tokens({}), 'workflow');
    expect(out).toBe('---\nname: workflow\ndescription: Guided delivery.\n---\n\nDo the thing.');
  });

  it('cursor serializeAgent selects the cursor switch branch and renders tokens', () => {
    // Ported from test_cursor_serialize.py's test_switch_and_token_rendering_selects_the_cursor_branch:
    // the body is rendered for the cursor target — switch branches select cursor, and ${var}
    // tokens substitute — end to end through the serializeAgent sugar.
    const body = '${target:opencode}\nOC\n${target:cursor}\nCUR\n${target:end}\nrun ${ns}design';
    const m = meta({ name: 'hercules', description: 'd', model_tier: 'high' });
    const out = ser('cursor').serializeAgent(m, body, tokens({ ns: '/' }));
    expect(out).toContain('CUR');
    expect(out).not.toContain('OC');
    expect(out).toContain('run /design');
  });

  it('serializePersona wraps or renders per mode', () => {
    expect(ser('copilot-cli').serializePersona('P for ${product}.\n', tokens({ product: 'GitHub Copilot CLI' })))
      .toBe('P for GitHub Copilot CLI.\n');
    expect(ser('cursor').serializePersona('P.\n', tokens({})).startsWith('---\ndescription: Hercules')).toBe(true);
  });

  it('an explicitly passed models map overrides the descriptor row', () => {
    // The tiering override contract: a models map naming the target wins over descriptor data.
    const s = ser('claude-code');
    const out = s.serializeAgent(
      meta({ name: 'x', description: 'd', model_tier: 'high' }), 'B.', tokens({}),
      { 'claude-code': { high: 'sonnet', medium: null, low: null } },
    );
    expect(out).toContain('\nmodel: sonnet\n');
  });
});

describe('dispatchers directly', () => {
  it('roleByFrontmatter sniffs agent/command/persona/default', () => {
    const s = ser('opencode') as unknown as {
      // Private in the class; accessed here the same way the Python tests reach the
      // underscore-prefixed method directly — dispatcher logic is worth pinning on its own.
      roleByFrontmatter(text: string): string;
    };
    expect(s.roleByFrontmatter(AGENT_SRC)).toBe('agent');
    expect(s.roleByFrontmatter(COMMAND_SRC)).toBe('command');
    expect(s.roleByFrontmatter('No frontmatter at all.\n')).toBe('persona');
    expect(s.roleByFrontmatter('---\nname: skill\ndescription: d\n---\n\nBody.\n')).toBe('default');
  });

  it('roleByPath routes by source location', () => {
    const s = ser('claude-code') as unknown as { roleByPath(rel: string | null): string };
    expect(s.roleByPath('persona.md')).toBe('persona');
    expect(s.roleByPath('agents/x.md')).toBe('agent');
    expect(s.roleByPath('commands/x.md')).toBe('command');
    expect(s.roleByPath('skills/s/SKILL.md')).toBe('default');
    expect(s.roleByPath(null)).toBe('default');
  });
});

describe('computeFields', () => {
  it('orders output by spec order', () => {
    const fields = (DESCRIPTORS['opencode'] as NonNullable<(typeof DESCRIPTORS)['opencode']>).roles['agent']?.fields ?? [];
    const out = computeFields(fields, meta({ name: 'hercules', description: 'd' }), 'opencode', tokens({}));
    expect([...out.keys()]).toEqual(['name', 'description', 'mode']);
    expect(out.get('mode')).toBe('primary');
  });
});

function repoMarkdownFiles(): string[] {
  const root = join(repoRoot, 'src', 'content');
  // `.parentPath` is available on Node >=20.1 (this project targets >=22 — see package.json's
  // `engines`), so no fallback to the deprecated `.path` is needed.
  return readdirSync(root, { recursive: true, withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith('.md'))
    .map((e) => join(e.parentPath, e.name))
    .map((p) => p.slice(root.length + 1).split('\\').join('/'));
}

describe('corpus guards (freeze the facts that make dispatch equivalent)', () => {
  it('model_tier appears only under agents/', () => {
    // Freezes the corpus fact that makes path- and frontmatter-dispatch equivalent: model_tier
    // (the agent sniff marker) never appears outside agents/. If a non-agent source ever gains it,
    // opencode's frontmatter sniff and every path dispatcher would diverge — this fails FIRST.
    for (const rel of repoMarkdownFiles()) {
      if (!rel.startsWith('agents/')) {
        const text = readRepoContentFile(rel);
        expect(text, `${rel}: model_tier outside agents/ breaks dispatch equivalence`).not.toContain('model_tier:');
      }
    }
  });

  it('the command marker appears only under commands/', () => {
    // The companion guard: disable-model-invocation (the command sniff marker) never appears
    // outside commands/ — same dispatch-equivalence freeze as the model_tier guard.
    for (const rel of repoMarkdownFiles()) {
      if (!rel.startsWith('commands/')) {
        const text = readRepoContentFile(rel);
        expect(text, `${rel}: command marker outside commands/ breaks dispatch equivalence`).not.toContain('disable-model-invocation');
      }
    }
  });
});

function readRepoContentFile(rel: string): string {
  return readFileSync(join(repoRoot, 'src', 'content', rel), 'utf-8');
}

describe('a synthetic preserve role without resolve_model_tier', () => {
  it('leaves model_tier untouched — a pure byte passthrough', () => {
    const raw = {
      schema: 1, name: 'eco', vars: { product: 'Eco' },
      models: { high: null, medium: null, low: null },
      smoke: { cli: 'eco', test: 't.py' }, dispatch: 'path',
      roles: {
        agent: { mode: 'preserve' }, command: { mode: 'preserve' },
        persona: { mode: 'plain' }, default: { mode: 'preserve' },
      },
      routes: [],
    };
    const s = new DescriptorSerializer(parseDescriptor('eco', raw));
    const out = s.serializeFile(AGENT_SRC, tokens({ product: 'Eco' }), null, 'agents/x.md');
    expect(out).toContain('model_tier: high');
    expect(out).not.toContain('\nmodel:');
  });
});
