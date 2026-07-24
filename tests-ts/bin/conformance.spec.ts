import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { names } from '../../scripts-ts/build/descriptor.mjs';
import { buildTarget } from '../../scripts-ts/bin/cli.mjs';
import { filesUnder, isFile } from '../support/buildTree';
import { ECOSYSTEMS } from '../support/descriptorFixtures';

// Ported from tests/build/test_conformance.py: ecosystem-conformance hardening — doc-grounded
// runtime fixes from two ecosystem-specialist audits, each pinned here so it can't regress.

const dirs: string[] = [];

function build(target: string): string {
  const root = mkdtempSync(join(tmpdir(), `hercules-conformance-${target}-`));
  dirs.push(root);
  const out = join(root, target);
  buildTarget(target, out);
  return out;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('fix 1: agent-spawn namespace', () => {
  it('opencode tells agents to spawn the reviewer by its plain name', () => {
    const out = build('opencode');
    const text = filesUnder(out)['commands/build.md'] as string;
    expect(text).toContain('Spawn `cynical-reviewer`');
    expect(text).not.toContain('hercules:cynical-reviewer');
  });

  it('claude-code tells agents to spawn the reviewer by its scoped name', () => {
    const out = build('claude-code');
    expect(filesUnder(out)['commands/build.md']).toContain('hercules:cynical-reviewer');
  });
});

describe('fix 2: operational sections live in an auto-loaded reference skill', () => {
  const SECTIONS = [
    'Artifact root resolution', 'Machine-local state', 'Agent scaling',
    'Code-of-conduct resolution', 'Sub-agent consent', 'Debate protocol', 'Independent review',
  ];

  it('every target ships all operational guidance in its reference skill', () => {
    for (const tgt of ['claude-code', 'opencode', 'cursor', 'grok-build', 'gemini-cli', 'copilot-cli']) {
      const out = build(tgt);
      expect(isFile(out, 'skills', 'hercules-reference', 'SKILL.md'), `${tgt}: skill missing`).toBe(true);
      const body = filesUnder(out)['skills/hercules-reference/SKILL.md'] as string;
      for (const sec of SECTIONS) expect(body, `${tgt}: '${sec}' missing`).toContain(sec);
    }
  });

  it('operational guidance never cites a file the agent never loads', () => {
    const oc = build('opencode');
    const cc = build('claude-code');
    const cur = build('cursor');
    for (const tree of [oc, cur]) {
      for (const [rel, text] of Object.entries(filesUnder(tree))) {
        expect(text, `${rel} cites AGENTS.md §`).not.toContain('AGENTS.md §');
      }
    }
    for (const [rel, text] of Object.entries(filesUnder(cc))) {
      expect(text, `${rel} cites CLAUDE.md §`).not.toContain('CLAUDE.md §');
    }
  });
});

describe('fix 3: protocol references resolve/load', () => {
  it('claude-code protocol links resolve from the plugin root', () => {
    const out = build('claude-code');
    const joined = Object.values(filesUnder(out)).join('\n');
    expect(joined).toContain('${CLAUDE_PLUGIN_ROOT}/protocols/a2a-communication-protocol.md');
    expect(joined).not.toContain('`protocols/a2a-communication-protocol.md`');
  });

  it('cursor protocol links resolve from the plugin root', () => {
    const out = build('cursor');
    const joined = Object.values(filesUnder(out)).join('\n');
    expect(joined).toContain('${CURSOR_PLUGIN_ROOT}/protocols/a2a-communication-protocol.md');
  });
});

describe('fix 4: plan-mode prose is behavioral on OpenCode/Cursor', () => {
  it('opencode has no leftover Claude-only wording', () => {
    const out = build('opencode');
    const joined = Object.values(filesUnder(out)).join('\n');
    expect(joined).not.toContain('(`auto`)');
    expect(joined).not.toMatch(/call\s+`plan mode`/i);
    expect(joined).not.toContain('`approval`');
  });

  it('cursor has no leftover Claude-only wording', () => {
    const out = build('cursor');
    const joined = Object.values(filesUnder(out)).join('\n');
    expect(joined).not.toContain('(`auto`)');
    expect(joined).not.toMatch(/call\s+`plan mode`/i);
    expect(joined).not.toContain('`approval`');
  });

  it('claude-code keeps its own plan-mode tool names', () => {
    const out = build('claude-code');
    const joined = Object.values(filesUnder(out)).join('\n');
    expect(joined).toContain('EnterPlanMode');
    expect(joined).toContain('ExitPlanMode');
  });
});

describe('fix 5: write-gate disclosure lands in a loaded surface', () => {
  it('opencode users are warned about the edit-approval prompt in instructions.md', () => {
    const out = build('opencode');
    expect(filesUnder(out)['instructions.md']).toContain('edit: "ask"');
  });
});

describe('fix 6: no target renders a plan-mode/CoC triad empty', () => {
  it('every registered target renders the plan-mode instruction in every command, with no unresolved switch', () => {
    for (const tgt of names(ECOSYSTEMS)) {
      const out = build(tgt);
      const files = filesUnder(out);
      const commandFiles = Object.keys(files).filter((rel) => rel.startsWith('commands/'));
      expect(commandFiles.length, `${tgt}: no command files built`).toBeGreaterThan(0);
      for (const rel of commandFiles) {
        expect(files[rel], `${tgt}: ${rel} plan-mode switch rendered empty`).toContain('Plan mode — required');
      }
      expect(Object.values(files).join('\n'), `${tgt}: unresolved target switch left`).not.toContain('${target:');
    }
  });
});
