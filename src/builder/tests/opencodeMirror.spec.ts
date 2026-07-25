import { describe, expect, it } from 'vitest';

import { discover } from '../descriptor.mjs';
import { readSource } from '../emit.mjs';
import { roleEntries } from '../genExtras.mjs';
import { splitDocument, parseFrontmatter } from '../parse.mjs';
import { buildRegistry } from '../serialize.mjs';
import { ECOSYSTEMS } from '../../tests/support/descriptorFixtures';
import { repoRoot } from '../../tests/support/repo';
import { join } from 'node:path';

// Ported from tests/build/test_opencode_mirror.py: OpenCode loads agents/commands at runtime from
// the inlined cfg.agent/cfg.command maps in plugin.js (built by genExtras.roleEntries through the
// generic template) — NOT from the standalone dist/opencode/{agents,commands}/*.md files, which are
// a human-readable, diff-friendly mirror. Both paths are driven by the SAME descriptor role fields,
// so this is the wiring guard that the shared source stays actually shared.

const SRC_CONTENT = join(repoRoot, 'src', 'content');

function standaloneFields(
  kind: string, name: string, tokens: ReadonlyMap<string, string>,
  models: Record<string, Record<string, string | null>>,
): { meta: Map<string, string>; body: string } {
  const registry = buildRegistry(Object.values(discover(ECOSYSTEMS)));
  const src = join(SRC_CONTENT, kind, `${name}.md`);
  const out = registry.serializeFile('opencode', readSource(src), tokens, models);
  const { block, body: rawBody } = splitDocument(out);
  const { metadata: meta } = parseFrontmatter(block as string);
  return { meta, body: rawBody.trim() };
}

describe('OpenCode standalone mirror files match the inlined plugin.js entries', () => {
  const opencode = discover(ECOSYSTEMS)['opencode'];
  if (opencode === undefined) throw new Error('opencode descriptor missing');
  const tokens = new Map(Object.entries(opencode.vars));
  const models: Record<string, Record<string, string | null>> = {};
  for (const [name, d] of Object.entries(discover(ECOSYSTEMS))) models[name] = d.models;

  it('every agent matches its human-readable reference copy', () => {
    const agents = roleEntries(opencode, SRC_CONTENT, tokens, 'agent');
    expect(agents.length).toBeGreaterThan(0);
    for (const { stem, fields, body } of agents) {
      const standalone = standaloneFields('agents', stem, tokens, models);
      expect(standalone.meta.get('description')).toBe(fields.get('description'));
      expect(standalone.meta.get('mode')).toBe(fields.get('mode'));
      expect(standalone.body).toBe(body);
    }
  });

  it('every command matches its human-readable reference copy', () => {
    const commands = roleEntries(opencode, SRC_CONTENT, tokens, 'command');
    expect(commands.length).toBeGreaterThan(0);
    for (const { stem, fields, body } of commands) {
      const standalone = standaloneFields('commands', stem, tokens, models);
      expect(standalone.meta.get('description')).toBe(fields.get('description'));
      expect(standalone.meta.get('agent')).toBe(fields.get('agent'));
      expect(standalone.body).toBe(body);
    }
  });

  it('every inline command entry has a real description and clean prompt text', () => {
    // Ported from test_opencode_commands.py's test_opencode_commands_have_real_descriptions_...:
    // the one path that used to skip the target-aware serializer — commands embedded raw YAML
    // frontmatter with an empty description in plugin.js, and lost the agent binding.
    const commands = roleEntries(opencode, SRC_CONTENT, tokens, 'command');
    expect(commands.length).toBeGreaterThan(0);
    for (const { stem, fields, body } of commands) {
      expect(fields.get('description'), `${stem}: empty command description reaches the UI`).toBeTruthy();
      expect(fields.get('agent'), `${stem}: command not bound to the hercules agent`).toBe('hercules');
      expect(body.trimStart().startsWith('---'), `${stem}: template still embeds YAML frontmatter`).toBe(false);
      expect(body, `${stem}: Claude key leaked into template`).not.toContain('disable-model-invocation');
    }
  });
});
