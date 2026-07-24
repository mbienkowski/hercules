import { readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { discover } from '../../scripts-ts/build/descriptor.mjs';
import { ECOSYSTEMS } from '../support/descriptorFixtures';
import { repoRoot } from '../support/repo';

// Ported from tests/build/test_roster_sync.py — Spec 02: the Claude-only settings.json roster
// stays in sync with src/content/agents/. settings.json is authored as an inline artifact in the
// claude-code descriptor (emitted verbatim); this sync test is the reader-end pin so a new agent
// can't ship without being registered. Frozen for spec-02-claude-code-target.

const AGENTS = join(repoRoot, 'src', 'content', 'agents');

function settings(): Record<string, unknown> {
  const claudeCode = discover(ECOSYSTEMS)['claude-code'];
  if (claudeCode === undefined) throw new Error('claude-code descriptor missing');
  const artifact = claudeCode.artifacts.find((a) => a.dest === 'settings.json');
  if (artifact === undefined) throw new Error('settings.json artifact missing');
  return artifact.content;
}

describe('registered agent roster matches the agents that actually exist', () => {
  it('the default agent plus every advisor exactly matches src/content/agents/', () => {
    // Catches a new agent added but never registered, or a removed agent whose registration was
    // left behind, before either ships to users.
    const s = settings();
    const roster = new Set(readdirSync(AGENTS).filter((n) => n.endsWith('.md')).map((n) => n.slice(0, -3)));
    const listed = new Set([s['agent'] as string, ...(s['advisors'] as string[])]);
    expect(listed).toEqual(roster);
  });
});

describe('hercules is the default agent', () => {
  it('out of the box, with no explicit agent choice made, Claude Code defaults to hercules', () => {
    expect(settings()['agent']).toBe('hercules');
  });
});
